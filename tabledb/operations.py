"""Операції над таблицями. Індивідуальна операція варіанта — різниця таблиць."""
from __future__ import annotations

from .errors import DifferenceError
from .model import Table


class TableDifference:
    """R = A \\ B: рядки таблиці A, яких немає в таблиці B.

    * схеми A і B мають бути сумісні (кількість і типи полів);
    * R успадковує схему (імена полів) таблиці A;
    * порядок рядків R збігається з порядком у A; дублікати в A зберігаються;
    * таблиці A і B не змінюються;
    * рядки порівнюються за всіма полями.

    Завдяки індексу Table.contains() складність дорівнює O(n + m).
    """

    @staticmethod
    def difference(a: Table, b: Table, name: str) -> Table:
        reason = a.schema.incompatibility(b.schema)
        if reason is not None:
            raise DifferenceError(
                f"схеми таблиць «{a.name}» і «{b.name}» несумісні: {reason}"
            )
        result = Table(name, a.schema)
        for row in a.rows:
            if not b.contains(row):
                result.add_row(row.copy())
        return result
