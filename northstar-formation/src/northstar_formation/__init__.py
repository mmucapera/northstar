"""Northstar Formation - YAML to Spark SQL and Fabric Notebooks.

This package provides tools for transforming YAML model definitions
into Spark SQL queries and Microsoft Fabric notebooks.

Example:
    >>> from northstar_formation.core.parser import YAMLParser
    >>> from northstar_formation.core.resolver import ModelResolver
    >>> from northstar_formation.sql.generator import SparkSQLGenerator
    >>>
    >>> parser = YAMLParser("./models")
    >>> models = parser.load_all_models(context)
    >>> resolver = ModelResolver(parser)
    >>> resolved = resolver.resolve_all(models, context)
    >>> generator = SparkSQLGenerator()
    >>> sql = generator.generate_all(resolved, context)
"""

__version__ = "1.0.0"
__all__ = [
    "__version__",
]
