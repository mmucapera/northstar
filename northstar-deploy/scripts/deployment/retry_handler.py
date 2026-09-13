#!/usr/bin/env python3
"""
Retry Handler for Fabric Deployment System
Implements REQ-019 - Sophisticated retry logic with exponential backoff
"""

import time
import sys
import os
from typing import Callable, List, Optional, Any, Dict
from functools import wraps
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger

logger = setup_logger(__name__)


class RetryableError(Exception):
    """Base exception for retriable errors"""

    pass


class NonRetryableError(Exception):
    """Exception for errors that should not be retried"""

    pass


class RetryHandler:
    """
    Handle retry logic for Fabric API operations
    Implements exponential backoff with configurable parameters
    """

    def __init__(
        self,
        max_attempts: int = 3,
        backoff_seconds: int = 30,
        max_backoff_seconds: int = 300,
        exponential_base: float = 2.0,
        retriable_errors: Optional[List[str]] = None,
        retriable_status_codes: Optional[List[int]] = None,
    ):
        """
        Initialize retry handler

        Args:
            max_attempts: Maximum number of retry attempts (default: 3)
            backoff_seconds: Initial backoff duration in seconds (default: 30)
            max_backoff_seconds: Maximum backoff duration (default: 300 = 5 minutes)
            exponential_base: Base for exponential backoff calculation (default: 2.0)
            retriable_errors: List of error message patterns to retry
            retriable_status_codes: List of HTTP status codes to retry
        """
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.exponential_base = exponential_base

        # Default retriable error patterns
        self.retriable_errors = retriable_errors or [
            "TooManyRequests",
            "ServiceUnavailable",
            "GatewayTimeout",
            "RequestTimeout",
            "InternalServerError",
            "BadGateway",
            "ServiceTemporarilyUnavailable",
            "ThrottlingException",
            "capacity.*unavailable",  # Regex pattern for capacity issues
            "temporarily.*unavailable",  # Regex pattern
            "connection.*reset",  # Regex pattern
            "operation.*timed.*out",  # Regex pattern
        ]

        # Default retriable HTTP status codes
        self.retriable_status_codes = retriable_status_codes or [
            408,  # Request Timeout
            429,  # Too Many Requests
            500,  # Internal Server Error
            502,  # Bad Gateway
            503,  # Service Unavailable
            504,  # Gateway Timeout
            507,  # Insufficient Storage
            509,  # Bandwidth Limit Exceeded
        ]

        self.retry_stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "total_backoff_time": 0,
        }

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff duration for the given attempt
        Uses exponential backoff with jitter

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Backoff duration in seconds
        """
        import random

        # Exponential backoff: backoff_seconds * (exponential_base ^ attempt)
        backoff = min(
            self.backoff_seconds * (self.exponential_base**attempt),
            self.max_backoff_seconds,
        )

        # Add jitter (random value between 0 and 20% of backoff)
        jitter = random.uniform(0, backoff * 0.2)

        return backoff + jitter

    def _is_retriable_error(self, error: Exception) -> bool:
        """
        Check if error is retriable

        Args:
            error: Exception to check

        Returns:
            True if error should be retried
        """
        import re

        # Check if explicitly marked as non-retriable
        if isinstance(error, NonRetryableError):
            return False

        # Check if explicitly marked as retriable
        if isinstance(error, RetryableError):
            return True

        # Check for HTTP errors
        if isinstance(error, requests.exceptions.HTTPError):
            if hasattr(error, "response") and error.response is not None:
                status_code = error.response.status_code
                if status_code in self.retriable_status_codes:
                    return True

        # Check error message against patterns
        error_message = str(error).lower()
        for pattern in self.retriable_errors:
            if re.search(pattern.lower(), error_message):
                return True

        # Check for specific exception types
        retriable_exception_types = (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            ConnectionResetError,
            TimeoutError,
        )

        if isinstance(error, retriable_exception_types):
            return True

        return False

    def _log_retry_attempt(
        self,
        attempt: int,
        max_attempts: int,
        error: Exception,
        backoff: float,
        context: str,
    ):
        """
        Log retry attempt details

        Args:
            attempt: Current attempt number
            max_attempts: Maximum attempts
            error: Exception that triggered retry
            backoff: Backoff duration
            context: Context description
        """
        error_type = type(error).__name__
        error_msg = str(error)

        # Extract status code if available
        status_code = None
        if isinstance(error, requests.exceptions.HTTPError):
            if hasattr(error, "response") and error.response is not None:
                status_code = error.response.status_code

        log_msg = (
            f"Retry attempt {attempt}/{max_attempts} for '{context}' after {error_type}"
        )

        if status_code:
            log_msg += f" (HTTP {status_code})"

        log_msg += f" - waiting {backoff:.1f}s before retry"

        logger.warning(log_msg)
        logger.debug(f"Error details: {error_msg}")

    def execute_with_retry(
        self, func: Callable, *args, context: Optional[str] = None, **kwargs
    ) -> Any:
        """
        Execute function with retry logic

        Args:
            func: Function to execute
            *args: Positional arguments for func
            context: Description of operation for logging
            **kwargs: Keyword arguments for func

        Returns:
            Return value from func

        Raises:
            Last exception if all retries exhausted
        """
        if context is None:
            context = func.__name__

        last_exception = None

        for attempt in range(self.max_attempts):
            self.retry_stats["total_attempts"] += 1

            try:
                # Log attempt
                if attempt > 0:
                    logger.info(
                        f"Executing '{context}' (attempt {attempt + 1}/{self.max_attempts})"
                    )
                else:
                    logger.info(f"Executing '{context}'")

                # Execute function
                result = func(*args, **kwargs)

                # Success
                if attempt > 0:
                    self.retry_stats["successful_retries"] += 1
                    logger.info(f"'{context}' succeeded after {attempt + 1} attempts")

                return result

            except Exception as e:
                last_exception = e

                # Check if error is retriable
                if not self._is_retriable_error(e):
                    logger.error(
                        f"Non-retriable error in '{context}': {type(e).__name__}: {str(e)}"
                    )
                    raise NonRetryableError(f"Non-retriable error: {str(e)}") from e

                # Check if we have more attempts
                if attempt < self.max_attempts - 1:
                    # Calculate backoff
                    backoff = self._calculate_backoff(attempt)
                    self.retry_stats["total_backoff_time"] += backoff

                    # Log retry
                    self._log_retry_attempt(
                        attempt + 1, self.max_attempts, e, backoff, context
                    )

                    # Wait before retry
                    time.sleep(backoff)
                else:
                    # No more retries
                    self.retry_stats["failed_retries"] += 1
                    logger.error(
                        f"All {self.max_attempts} attempts failed for '{context}'. "
                        f"Last error: {type(e).__name__}: {str(e)}"
                    )

        # All retries exhausted
        raise last_exception

    def execute_with_retry_async(
        self, func: Callable, *args, context: Optional[str] = None, **kwargs
    ):
        """
        Execute async function with retry logic

        Args:
            func: Async function to execute
            *args: Positional arguments
            context: Operation description
            **kwargs: Keyword arguments

        Returns:
            Coroutine that executes function with retry
        """
        import asyncio

        async def _async_retry():
            if context is None:
                operation_context = func.__name__
            else:
                operation_context = context

            last_exception = None

            for attempt in range(self.max_attempts):
                self.retry_stats["total_attempts"] += 1

                try:
                    if attempt > 0:
                        logger.info(
                            f"Executing '{operation_context}' (attempt {attempt + 1}/{self.max_attempts})"
                        )
                    else:
                        logger.info(f"Executing '{operation_context}'")

                    result = await func(*args, **kwargs)

                    if attempt > 0:
                        self.retry_stats["successful_retries"] += 1
                        logger.info(
                            f"'{operation_context}' succeeded after {attempt + 1} attempts"
                        )

                    return result

                except Exception as e:
                    last_exception = e

                    if not self._is_retriable_error(e):
                        logger.error(
                            f"Non-retriable error in '{operation_context}': {type(e).__name__}: {str(e)}"
                        )
                        raise NonRetryableError(f"Non-retriable error: {str(e)}") from e

                    if attempt < self.max_attempts - 1:
                        backoff = self._calculate_backoff(attempt)
                        self.retry_stats["total_backoff_time"] += backoff

                        self._log_retry_attempt(
                            attempt + 1,
                            self.max_attempts,
                            e,
                            backoff,
                            operation_context,
                        )

                        await asyncio.sleep(backoff)
                    else:
                        self.retry_stats["failed_retries"] += 1
                        logger.error(
                            f"All {self.max_attempts} attempts failed for '{operation_context}'. "
                            f"Last error: {type(e).__name__}: {str(e)}"
                        )

            raise last_exception

        return _async_retry()

    def retry_decorator(self, context: Optional[str] = None):
        """
        Decorator for functions that should be retried

        Args:
            context: Optional context description

        Returns:
            Decorator function

        Example:
            @retry_handler.retry_decorator(context="deploy items")
            def deploy_function():
                # ... deployment code
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return self.execute_with_retry(
                    func, *args, context=context or func.__name__, **kwargs
                )

            return wrapper

        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """
        Get retry statistics

        Returns:
            Dictionary with retry statistics
        """
        return {
            **self.retry_stats,
            "success_rate": (
                self.retry_stats["successful_retries"]
                / self.retry_stats["total_attempts"]
                if self.retry_stats["total_attempts"] > 0
                else 0
            ),
            "average_backoff": (
                self.retry_stats["total_backoff_time"]
                / (
                    self.retry_stats["successful_retries"]
                    + self.retry_stats["failed_retries"]
                )
                if (
                    self.retry_stats["successful_retries"]
                    + self.retry_stats["failed_retries"]
                )
                > 0
                else 0
            ),
        }

    def reset_stats(self):
        """Reset retry statistics"""
        self.retry_stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "total_backoff_time": 0,
        }


def create_retry_handler_from_config(config: Dict) -> RetryHandler:
    """
    Create RetryHandler from configuration dictionary

    Args:
        config: Configuration dictionary with retry settings

    Returns:
        Configured RetryHandler instance
    """
    retry_config = config.get("deployment", {}).get("retry", {})

    return RetryHandler(
        max_attempts=retry_config.get("max_attempts", 3),
        backoff_seconds=retry_config.get("backoff_seconds", 30),
        max_backoff_seconds=retry_config.get("max_backoff_seconds", 300),
        exponential_base=retry_config.get("exponential_base", 2.0),
        retriable_errors=retry_config.get("retriable_errors"),
        retriable_status_codes=retry_config.get("retriable_status_codes"),
    )


def main():
    """Test retry handler functionality"""

    print("Testing RetryHandler...")

    # Create handler with short backoff for testing
    handler = RetryHandler(max_attempts=3, backoff_seconds=2, exponential_base=2.0)

    # Test 1: Function that succeeds immediately
    print("\n=== Test 1: Immediate success ===")

    def success_func():
        print("Function executed successfully")
        return "success"

    result = handler.execute_with_retry(success_func, context="test_immediate_success")
    print(f"Result: {result}")

    # Test 2: Function that fails then succeeds
    print("\n=== Test 2: Retry then success ===")
    attempt_counter = {"count": 0}

    def retry_then_success():
        attempt_counter["count"] += 1
        if attempt_counter["count"] < 2:
            raise RetryableError("Simulated retriable error")
        print("Function succeeded after retry")
        return "success_after_retry"

    result = handler.execute_with_retry(
        retry_then_success, context="test_retry_success"
    )
    print(f"Result: {result}")

    # Test 3: Non-retriable error
    print("\n=== Test 3: Non-retriable error ===")

    def non_retriable_func():
        raise ValueError("This is a non-retriable error")

    try:
        handler.execute_with_retry(non_retriable_func, context="test_non_retriable")
    except NonRetryableError as e:
        print(f"Caught expected non-retriable error: {e}")

    # Test 4: All retries exhausted
    print("\n=== Test 4: All retries exhausted ===")

    def always_fail():
        raise RetryableError("Simulated persistent error")

    try:
        handler.execute_with_retry(always_fail, context="test_all_retries_exhausted")
    except RetryableError as e:
        print(f"All retries exhausted as expected: {e}")

    # Test 5: Using decorator
    print("\n=== Test 5: Decorator pattern ===")
    handler2 = RetryHandler(max_attempts=2, backoff_seconds=1)

    @handler2.retry_decorator(context="decorated_function")
    def decorated_func(value):
        print(f"Decorated function called with value: {value}")
        return value * 2

    result = decorated_func(21)
    print(f"Result: {result}")

    # Print statistics
    print("\n=== Retry Statistics ===")
    stats = handler.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\nRetryHandler tests completed!")


if __name__ == "__main__":
    main()
