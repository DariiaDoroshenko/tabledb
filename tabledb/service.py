"""Спільний інтерфейс доступу до бази для GUI.

GUI працює лише з Backend і не знає, де лежить база: у цьому ж процесі
(LocalBackend) чи на віддаленому сервері (RemoteBackend із client.py).
Усі методи приймають і повертають прості структури (рядки, списки, словники),
тому ті самі виклики проходять і через HTTP/JSON.

Подання таблиці:
    {"name": str, "fields": [{"name": str, "type": str}], "rows": [[str, ...]]}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .errors import ValidationError
from .model import Database, Schema
from .operations import TableDifference
from .storage import DatabaseStorage


class Backend(ABC):
    is_remote = False

    @property
    @abstractmethod
    def description(self) -> str:
        """Короткий опис для рядка стану: «Локально» або адреса сервера."""

    @abstractmethod
    def new_database(self, name: str = "Нова база") -> None: ...

    @abstractmethod
    def database_name(self) -> str: ...

    @abstractmethod
    def list_tables(self) -> list[str]: ...

    @abstractmethod
    def get_table(self, name: str) -> dict: ...

    @abstractmethod
    def create_table(self, name: str, fields: Sequence[dict]) -> dict: ...

    @abstractmethod
    def drop_table(self, name: str) -> None: ...

    @abstractmethod
    def add_row(self, table: str, values: Sequence[str]) -> int:
        """Додає рядок; повертає його індекс (з нуля)."""

    @abstractmethod
    def update_row(self, table: str, index: int, values: Sequence[str]) -> None: ...

    @abstractmethod
    def difference(self, a: str, b: str, result: str) -> dict:
        """Створює таблицю result = a \\ b, додає її до бази й повертає її."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Локально: шлях до файлу; на сервері: ім'я файлу в теці сервера."""

    @abstractmethod
    def load(self, path: str) -> None: ...

    def list_files(self) -> list[str]:
        """Імена збережених баз на сервері (для локального режиму порожньо)."""
        return []


class LocalBackend(Backend):
    """Робота з базою в оперативній пам'яті поточного процесу."""

    def __init__(self, db: Database | None = None):
        self._db = db if db is not None else Database()

    @property
    def description(self) -> str:
        return "Локально"

    @property
    def database(self) -> Database:
        return self._db

    def new_database(self, name: str = "Нова база") -> None:
        self._db = Database(name)

    def database_name(self) -> str:
        return self._db.name

    def list_tables(self) -> list[str]:
        return self._db.table_names()

    def get_table(self, name: str) -> dict:
        return self._db.get_table(name).to_dict()

    def create_table(self, name: str, fields: Sequence[dict]) -> dict:
        try:
            schema = Schema.from_pairs((f["name"], f["type"]) for f in fields)
        except (KeyError, TypeError):
            raise ValidationError("некоректний опис полів") from None
        return self._db.create_table(name, schema).to_dict()

    def drop_table(self, name: str) -> None:
        self._db.drop_table(name)

    def add_row(self, table: str, values: Sequence[str]) -> int:
        t = self._db.get_table(table)
        t.add_text_row(values)
        return t.row_count() - 1

    def update_row(self, table: str, index: int, values: Sequence[str]) -> None:
        self._db.get_table(table).update_text_row(index, values)

    def difference(self, a: str, b: str, result: str) -> dict:
        ta = self._db.get_table(a)
        tb = self._db.get_table(b)
        table = TableDifference.difference(ta, tb, result)  # перевіряє схеми й ім'я
        self._db.add_table(table)  # перевіряє, що ім'я вільне
        return table.to_dict()

    def save(self, path: str) -> None:
        DatabaseStorage.save(self._db, path)

    def load(self, path: str) -> None:
        # Нова база підміняє поточну лише після успішного зчитування всього файлу.
        self._db = DatabaseStorage.load(path)

