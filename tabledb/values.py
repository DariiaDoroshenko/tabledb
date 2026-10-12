"""Система типів полів: значення, розбір тексту та валідація.

Відповідає діаграмі класів «система типів» зі специфікації (етап 1):
абстрактний Value, шість нащадків і ValueFactory як єдина точка створення
значень. Некоректне значення створити неможливо: фабрика кидає ValidationError.
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from datetime import date
from enum import Enum

from .errors import ValidationError

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1


class FieldType(Enum):
    """Підтримувані типи полів (чотири базові та два типи варіанта)."""

    INTEGER = "integer"
    REAL = "real"
    CHAR = "char"
    STRING = "string"
    DATE = "date"
    DATE_INVL = "dateInvl"

    @classmethod
    def parse(cls, name: str) -> "FieldType":
        for item in cls:
            if item.value == name:
                return item
        raise ValidationError(f"невідомий тип поля «{name}»")

    @property
    def hint(self) -> str:
        """Короткий опис формату для підказки в інтерфейсі."""
        return _HINTS[self]


_HINTS = {
    FieldType.INTEGER: "ціле число, напр. -15",
    FieldType.REAL: "число з крапкою, напр. 3.14",
    FieldType.CHAR: "рівно один символ",
    FieldType.STRING: "текст в один рядок",
    FieldType.DATE: "РРРР-ММ-ДД, напр. 2026-10-07",
    FieldType.DATE_INVL: "РРРР-ММ-ДД..РРРР-ММ-ДД",
}


class Value(ABC):
    """Значення поля. Об'єкти незмінні."""

    @property
    @abstractmethod
    def type(self) -> FieldType: ...

    @abstractmethod
    def to_text(self) -> str:
        """Канонічне текстове подання (використовується в GUI та файлі)."""

    @abstractmethod
    def _raw(self):
        """Порівнюване подання значення."""

    def key(self) -> tuple:
        """Хешований ключ: однакові значення мають однакові ключі."""
        return (self.type.value, self._raw())

    def equals(self, other: "Value") -> bool:
        return isinstance(other, Value) and self.key() == other.key()

    def compare_to(self, other: "Value") -> int:
        if self.type is not other.type:
            raise ValidationError("порівнювати можна лише значення однакового типу")
        a, b = self._raw(), other._raw()
        return (a > b) - (a < b)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Value) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.to_text()!r})"


class IntegerValue(Value):
    def __init__(self, value: int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise ValidationError("число виходить за межі 64-бітного цілого")
        self._value = int(value)

    @property
    def type(self) -> FieldType:
        return FieldType.INTEGER

    def to_text(self) -> str:
        return str(self._value)

    def _raw(self):
        return self._value


class RealValue(Value):
    def __init__(self, value: float):
        value = float(value)
        if not math.isfinite(value):
            raise ValidationError("NaN та нескінченність не допускаються")
        self._value = value

    @property
    def type(self) -> FieldType:
        return FieldType.REAL

    def to_text(self) -> str:
        return repr(self._value)

    def _raw(self):
        return self._value


class CharValue(Value):
    def __init__(self, value: str):
        if len(value) != 1:
            raise ValidationError("потрібен рівно один символ")
        if value in "\r\n":
            raise ValidationError("символ переведення рядка заборонений")
        self._value = value

    @property
    def type(self) -> FieldType:
        return FieldType.CHAR

    def to_text(self) -> str:
        return self._value

    def _raw(self):
        return self._value


class StringValue(Value):
    def __init__(self, value: str):
        if "\r" in value or "\n" in value:
            raise ValidationError("символи переведення рядка заборонені")
        self._value = value

    @property
    def type(self) -> FieldType:
        return FieldType.STRING

    def to_text(self) -> str:
        return self._value

    def _raw(self):
        return self._value


class DateValue(Value):
    """Календарна дата (рік 1–9999). Формат тексту: РРРР-ММ-ДД."""

    def __init__(self, year: int, month: int, day: int):
        if not 1 <= year <= 9999:
            raise ValidationError("рік має бути в межах 1–9999")
        if not 1 <= month <= 12:
            raise ValidationError("місяць має бути в межах 1–12")
        if not 1 <= day <= self.days_in(year, month):
            raise ValidationError(
                f"дата {year:04d}-{month:02d}-{day:02d} не існує "
                f"(у цьому місяці {self.days_in(year, month)} дн.)"
            )
        self._date = date(year, month, day)

    @staticmethod
    def is_leap(year: int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    @classmethod
    def days_in(cls, year: int, month: int) -> int:
        if month == 2:
            return 29 if cls.is_leap(year) else 28
        return 30 if month in (4, 6, 9, 11) else 31

    def is_leap_year(self) -> bool:
        return self.is_leap(self._date.year)

    def days_in_month(self) -> int:
        return self.days_in(self._date.year, self._date.month)

    @property
    def type(self) -> FieldType:
        return FieldType.DATE

    def to_text(self) -> str:
        return f"{self._date.year:04d}-{self._date.month:02d}-{self._date.day:02d}"

    def _raw(self):
        return self._date.toordinal()

    @property
    def ordinal(self) -> int:
        return self._date.toordinal()


class DateInvlValue(Value):
    """Інтервал дат; межі включно. Формат: РРРР-ММ-ДД..РРРР-ММ-ДД."""

    def __init__(self, start: DateValue, end: DateValue):
        if start.ordinal > end.ordinal:
            raise ValidationError(
                f"початок інтервалу ({start.to_text()}) пізніше за кінець ({end.to_text()})"
            )
        self.start = start
        self.end = end

    def contains(self, d: DateValue) -> bool:
        return self.start.ordinal <= d.ordinal <= self.end.ordinal

    def length_in_days(self) -> int:
        return self.end.ordinal - self.start.ordinal + 1

    @property
    def type(self) -> FieldType:
        return FieldType.DATE_INVL

    def to_text(self) -> str:
        return f"{self.start.to_text()}..{self.end.to_text()}"

    def _raw(self):
        return (self.start.ordinal, self.end.ordinal)


_INT_RE = re.compile(r"[+-]?\d+", re.ASCII)
_REAL_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", re.ASCII)
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})", re.ASCII)


class ValueFactory:
    """Єдина точка створення та валідації значень за типом поля."""

    @staticmethod
    def create(ftype: FieldType, text: str, field: str | None = None) -> Value:
        """Створює значення з тексту або кидає ValidationError.

        field — ім'я поля, яке потрапить у повідомлення про помилку.
        """
        if not isinstance(text, str):
            raise ValidationError("значення має бути текстом", field)
        try:
            return ValueFactory._create(ftype, text)
        except ValidationError as exc:
            raise ValidationError(exc.reason, field) from None

    @staticmethod
    def _create(ftype: FieldType, text: str) -> Value:
        if ftype is FieldType.INTEGER:
            s = text.strip()
            if not _INT_RE.fullmatch(s):
                raise ValidationError(f"«{text}» не є цілим числом")
            return IntegerValue(int(s))
        if ftype is FieldType.REAL:
            s = text.strip()
            if not _REAL_RE.fullmatch(s):
                raise ValidationError(f"«{text}» не є дійсним числом")
            return RealValue(float(s))
        if ftype is FieldType.CHAR:
            return CharValue(text)
        if ftype is FieldType.STRING:
            return StringValue(text)
        if ftype is FieldType.DATE:
            return ValueFactory._parse_date(text.strip())
        if ftype is FieldType.DATE_INVL:
            return ValueFactory._parse_interval(text.strip())
        raise ValidationError(f"невідомий тип {ftype}")

    @staticmethod
    def _parse_date(text: str) -> DateValue:
        m = _DATE_RE.fullmatch(text)
        if not m:
            raise ValidationError(f"«{text}»: очікується формат РРРР-ММ-ДД")
        return DateValue(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    @staticmethod
    def _parse_interval(text: str) -> DateInvlValue:
        parts = text.split("..")
        if len(parts) != 2:
            raise ValidationError(
                f"«{text}»: очікується формат РРРР-ММ-ДД..РРРР-ММ-ДД"
            )
        return DateInvlValue(
            ValueFactory._parse_date(parts[0].strip()),
            ValueFactory._parse_date(parts[1].strip()),
        )
