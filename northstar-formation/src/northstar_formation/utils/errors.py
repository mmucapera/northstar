"""Custom exceptions for Northstar Formation.

This module defines the exception hierarchy for the Northstar Formation package.
All exceptions inherit from UIXTransformError for consistent error handling.
"""

from __future__ import annotations

from typing import Any


class UIXTransformError(Exception):
    """Base exception for all Northstar Formation errors.

    All custom exceptions in this package should inherit from this class
    to enable consistent error handling and filtering.

    Attributes:
        message: Human-readable error message.
        details: Additional context about the error.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.
            details: Optional dictionary with additional error context.
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ConfigurationError(UIXTransformError):
    """Raised when configuration is invalid or missing.

    Examples:
        - Invalid YAML syntax in configuration file
        - Missing required configuration keys
        - Invalid configuration values
    """


class ParsingError(UIXTransformError):
    """Raised when YAML parsing fails.

    Attributes:
        file_path: Path to the file that failed to parse.
        line: Line number where the error occurred (if available).
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        line: int | None = None,
    ) -> None:
        """Initialize the parsing error.

        Args:
            message: Human-readable error message.
            file_path: Path to the file that failed to parse.
            line: Line number where the error occurred.
        """
        details: dict[str, Any] = {}
        if file_path:
            details["file"] = file_path
        if line is not None:
            details["line"] = str(line)
        super().__init__(message, details)
        self.file_path = file_path
        self.line = line


class ModelValidationError(UIXTransformError):
    """Raised when model validation fails.

    Attributes:
        model_name: Name of the model that failed validation.
        errors: List of specific validation errors.
    """

    def __init__(
        self,
        message: str,
        model_name: str,
        errors: list[str] | None = None,
    ) -> None:
        """Initialize the model validation error.

        Args:
            message: Human-readable error message.
            model_name: Name of the model that failed validation.
            errors: List of specific validation error messages.
        """
        super().__init__(message, {"model": model_name, "errors": errors or []})
        self.model_name = model_name
        self.errors = errors or []


class ResolutionError(UIXTransformError):
    """Raised when model resolution fails.

    This includes errors during inheritance resolution, function expansion,
    or reference resolution.
    """


class CircularDependencyError(ResolutionError):
    """Raised when circular dependencies are detected in model inheritance.

    Attributes:
        cycles: List of cycles, where each cycle is a list of model names.
    """

    def __init__(self, cycles: list[list[str]]) -> None:
        """Initialize the circular dependency error.

        Args:
            cycles: List of detected cycles in the dependency graph.
        """
        if len(cycles) == 1:
            cycle_str = " -> ".join(cycles[0])
            message = f"Circular dependency detected: {cycle_str}"
        else:
            message = f"Multiple circular dependencies detected: {cycles}"
        super().__init__(message, {"cycles": cycles})
        self.cycles = cycles


class FunctionError(UIXTransformError):
    """Raised when a dynamic function is invalid or fails.

    Attributes:
        function_name: Name of the function that failed.
    """

    def __init__(
        self,
        message: str,
        function_name: str | None = None,
    ) -> None:
        """Initialize the function error.

        Args:
            message: Human-readable error message.
            function_name: Name of the function that caused the error.
        """
        details = {}
        if function_name:
            details["function"] = function_name
        super().__init__(message, details)
        self.function_name = function_name


class ValidationError(UIXTransformError):
    """Raised when general validation fails.

    This is used for validation errors that don't fit into more specific
    categories like ModelValidationError.
    """


class GenerationError(UIXTransformError):
    """Raised when SQL or notebook generation fails.

    Attributes:
        model_name: Name of the model that failed generation.
        stage: Stage of generation where the error occurred.
    """

    def __init__(
        self,
        message: str,
        model_name: str | None = None,
        stage: str | None = None,
    ) -> None:
        """Initialize the generation error.

        Args:
            message: Human-readable error message.
            model_name: Name of the model being generated.
            stage: Stage of generation (e.g., "sql", "notebook").
        """
        details = {}
        if model_name:
            details["model"] = model_name
        if stage:
            details["stage"] = stage
        super().__init__(message, details)
        self.model_name = model_name
        self.stage = stage


class TemplateError(UIXTransformError):
    """Raised when template rendering fails.

    Attributes:
        template_name: Name of the template that failed.
    """

    def __init__(
        self,
        message: str,
        template_name: str | None = None,
    ) -> None:
        """Initialize the template error.

        Args:
            message: Human-readable error message.
            template_name: Name of the template that failed.
        """
        details = {}
        if template_name:
            details["template"] = template_name
        super().__init__(message, details)
        self.template_name = template_name


class LineageError(UIXTransformError):
    """Raised when lineage analysis fails."""


class LineageExportError(LineageError):
    """Raised when lineage export fails.

    Attributes:
        format: Export format that failed (e.g., "dot", "json").
        output_path: Path where the export was attempted.
    """

    def __init__(
        self,
        message: str,
        export_format: str | None = None,
        output_path: str | None = None,
    ) -> None:
        """Initialize the lineage export error.

        Args:
            message: Human-readable error message.
            export_format: Export format that failed.
            output_path: Path where export was attempted.
        """
        details = {}
        if export_format:
            details["format"] = export_format
        if output_path:
            details["output_path"] = output_path
        super().__init__(message, details)
        self.export_format = export_format
        self.output_path = output_path


class FileNotFoundError(UIXTransformError):
    """Raised when a required file or directory is not found.

    Note: This shadows the built-in FileNotFoundError intentionally
    to provide consistent error handling within the Northstar Formation package.

    Attributes:
        path: Path that was not found.
    """

    def __init__(self, message: str, path: str | None = None) -> None:
        """Initialize the file not found error.

        Args:
            message: Human-readable error message.
            path: Path that was not found.
        """
        details = {}
        if path:
            details["path"] = path
        super().__init__(message, details)
        self.path = path
