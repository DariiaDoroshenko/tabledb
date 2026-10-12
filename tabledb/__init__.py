"""tabledb — часткова реалізація системи управління табличними базами даних."""
from .errors import (  # noqa: F401
    DbError, DifferenceError, FormatError, NotFoundError, StorageError, ValidationError,
)
from .model import Database, Field, Row, Schema, Table  # noqa: F401
from .operations import TableDifference  # noqa: F401
from .service import Backend, LocalBackend  # noqa: F401
from .storage import DatabaseStorage  # noqa: F401
from .values import FieldType, Value, ValueFactory  # noqa: F401

__version__ = "2.0"
