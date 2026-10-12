"""Єдина ієрархія помилок системи.

Усі помилки, які користувач може побачити в повідомленні, успадковують DbError.
Так GUI та сервер можуть перехоплювати один базовий клас.
"""
from __future__ import annotations


class DbError(Exception):
    """Базова помилка системи керування табличними базами даних."""


class ValidationError(DbError, ValueError):
    """Некоректне значення поля, ім'я чи схема таблиці."""

    def __init__(self, reason: str, field: str | None = None):
        super().__init__(reason if field is None else f"{field}: {reason}")
        self.reason = reason
        self.field = field


class NotFoundError(DbError):
    """Таблицю чи рядок не знайдено."""


class DifferenceError(DbError):
    """Операція «різниця таблиць» неможлива (наприклад, схеми несумісні)."""


class StorageError(DbError):
    """Помилка збереження або зчитування файлу бази."""


class FormatError(StorageError):
    """Файл бази пошкоджений або має невідомий формат."""
