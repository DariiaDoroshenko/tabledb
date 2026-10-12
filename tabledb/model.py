"""Модель даних: Field, Schema, Row, Table, Database.

Класи відповідають діаграмі предметної області зі специфікації (етап 1).
Інваріант системи: у таблиці не може бути значення, що не відповідає типу
свого поля. Усі зміни спочатку валідуються, а вже потім застосовуються, тому
невдала операція не змінює стан таблиці чи бази.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import NotFoundError, ValidationError
from .values import FieldType, Value, ValueFactory


def check_name(name: str, what: str) -> str:
    """Ім'я таблиці чи поля: непорожнє, без керівних символів."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"{what} не може бути порожнім")
    name = name.strip()
    if any(ord(ch) < 32 for ch in name):
        raise ValidationError(f"{what} містить недопустимі символи")
    if len(name) > 100:
        raise ValidationError(f"{what} задовге (максимум 100 символів)")
    return name


@dataclass(frozen=True)
class Field:
    name: str
    type: FieldType


class Schema:
    """Впорядкований набір полів; імена полів унікальні, полів щонайменше одне."""

    def __init__(self, fields: Sequence[Field]):
        if not fields:
            raise ValidationError("схема має містити щонайменше одне поле")
        checked: list[Field] = []
        seen: set[str] = set()
        for f in fields:
            name = check_name(f.name, "ім'я поля")
            if name in seen:
                raise ValidationError(f"ім'я поля «{name}» повторюється")
            seen.add(name)
            checked.append(Field(name, f.type))
        self._fields = tuple(checked)

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, str]]) -> "Schema":
        return cls([Field(n, FieldType.parse(t)) for n, t in pairs])

    @property
    def fields(self) -> tuple[Field, ...]:
        return self._fields

    def field_count(self) -> int:
        return len(self._fields)

    def field_at(self, index: int) -> Field:
        return self._fields[index]

    def is_compatible_with(self, other: "Schema") -> bool:
        """Сумісність: однакова кількість полів і збіг типів на позиціях."""
        return self.incompatibility(other) is None

    def incompatibility(self, other: "Schema") -> str | None:
        """Опис першої розбіжності або None, якщо схеми сумісні."""
        if len(self._fields) != len(other._fields):
            return (
                f"різна кількість полів ({len(self._fields)} і {len(other._fields)})"
            )
        for i, (a, b) in enumerate(zip(self._fields, other._fields), start=1):
            if a.type is not b.type:
                return f"тип поля {i}: {a.type.value} і {b.type.value}"
        return None

    def types(self) -> tuple[FieldType, ...]:
        return tuple(f.type for f in self._fields)

    def to_dict(self) -> list[dict]:
        return [{"name": f.name, "type": f.type.value} for f in self._fields]

    @classmethod
    def from_dict(cls, data: Sequence[dict]) -> "Schema":
        try:
            return cls([Field(d["name"], FieldType.parse(d["type"])) for d in data])
        except (KeyError, TypeError):
            raise ValidationError("некоректний опис полів схеми") from None


class Row:
    """Рядок таблиці: впорядкований набір незмінних значень."""

    def __init__(self, values: Sequence[Value]):
        if not values:
            raise ValidationError("рядок має містити щонайменше одне значення")
        self._values = tuple(values)

    @property
    def values(self) -> tuple[Value, ...]:
        return self._values

    def value_at(self, index: int) -> Value:
        return self._values[index]

    def key(self) -> tuple:
        return tuple(v.key() for v in self._values)

    def equals(self, other: "Row") -> bool:
        return self.key() == other.key()

    def copy(self) -> "Row":
        # Значення незмінні, тому достатньо скопіювати контейнер.
        return Row(self._values)

    def to_texts(self) -> list[str]:
        return [v.to_text() for v in self._values]


class Table:
    """Таблиця: ім'я, схема та рядки.

    Для швидкої перевірки «чи є такий рядок» підтримується індекс-лічильник
    ключів рядків (Counter), тому contains() працює за O(1).
    """

    def __init__(self, name: str, schema: Schema):
        self.name = check_name(name, "ім'я таблиці")
        self.schema = schema
        self._rows: list[Row] = []
        self._index: Counter = Counter()

    # --- читання -----------------------------------------------------------
    @property
    def rows(self) -> tuple[Row, ...]:
        return tuple(self._rows)

    def row_count(self) -> int:
        return len(self._rows)

    def get_row(self, index: int) -> Row:
        if not 0 <= index < len(self._rows):
            raise NotFoundError(f"рядка з номером {index + 1} не існує")
        return self._rows[index]

    def contains(self, row: Row) -> bool:
        return self._index[row.key()] > 0

    # --- запис -------------------------------------------------------------
    def _check_row(self, row: Row) -> None:
        if len(row.values) != self.schema.field_count():
            raise ValidationError(
                f"очікується {self.schema.field_count()} значень, отримано {len(row.values)}"
            )
        for field, value in zip(self.schema.fields, row.values):
            if value.type is not field.type:
                raise ValidationError(
                    f"очікується тип {field.type.value}, отримано {value.type.value}",
                    field.name,
                )

    def row_from_texts(self, texts: Sequence[str]) -> Row:
        """Валідує тексти за схемою таблиці; перша помилка перериває розбір."""
        if len(texts) != self.schema.field_count():
            raise ValidationError(
                f"очікується {self.schema.field_count()} значень, отримано {len(texts)}"
            )
        values = [
            ValueFactory.create(f.type, t, f.name)
            for f, t in zip(self.schema.fields, texts)
        ]
        return Row(values)

    def add_row(self, row: Row) -> None:
        self._check_row(row)
        self._rows.append(row)
        self._index[row.key()] += 1

    def add_text_row(self, texts: Sequence[str]) -> Row:
        row = self.row_from_texts(texts)
        self.add_row(row)
        return row

    def update_row(self, index: int, row: Row) -> None:
        old = self.get_row(index)
        self._check_row(row)
        self._index[old.key()] -= 1
        self._rows[index] = row
        self._index[row.key()] += 1

    def update_text_row(self, index: int, texts: Sequence[str]) -> Row:
        self.get_row(index)  # перевірка існування до розбору значень
        row = self.row_from_texts(texts)
        self.update_row(index, row)
        return row

    # --- подання -----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": self.schema.to_dict(),
            "rows": [r.to_texts() for r in self._rows],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Table":
        try:
            table = cls(data["name"], Schema.from_dict(data["fields"]))
            for i, texts in enumerate(data["rows"], start=1):
                try:
                    table.add_text_row(texts)
                except ValidationError as exc:
                    raise ValidationError(f"рядок {i}: {exc}") from None
        except (KeyError, TypeError):
            raise ValidationError("некоректний опис таблиці") from None
        return table


class Database:
    """База даних: набір таблиць з унікальними іменами (порядок створення)."""

    def __init__(self, name: str = "Нова база"):
        self.name = name
        self._tables: dict[str, Table] = {}

    def table_names(self) -> list[str]:
        return list(self._tables)

    def has_table(self, name: str) -> bool:
        return name in self._tables

    def get_table(self, name: str) -> Table:
        try:
            return self._tables[name]
        except KeyError:
            raise NotFoundError(f"таблицю «{name}» не знайдено") from None

    def create_table(self, name: str, schema: Schema) -> Table:
        table = Table(name, schema)
        self.add_table(table)
        return table

    def add_table(self, table: Table) -> None:
        if table.name in self._tables:
            raise ValidationError(f"таблиця «{table.name}» вже існує")
        self._tables[table.name] = table

    def drop_table(self, name: str) -> None:
        self.get_table(name)
        del self._tables[name]

    def check_free_name(self, name: str) -> str:
        """Валідує ім'я нової таблиці та перевіряє, що воно вільне."""
        name = check_name(name, "ім'я таблиці")
        if name in self._tables:
            raise ValidationError(f"таблиця «{name}» вже існує")
        return name
