"""Спільні фікстури для тестів."""
from __future__ import annotations

from tabledb import Database, Schema, Table

PROJECT_FIELDS = [("№", "integer"), ("Назва", "string"), ("Період", "dateInvl")]


def project_table(name: str, rows) -> Table:
    table = Table(name, Schema.from_pairs(PROJECT_FIELDS))
    for r in rows:
        table.add_text_row(r)
    return table


# Приклад із розділу 1.5 звіту етапу 1 (таблиця 4).
ROWS_A = [
    ["1", "Проєкт «Альфа»", "2025-01-01..2025-06-30"],
    ["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
    ["3", "Проєкт «Гамма»", "2025-05-01..2025-12-31"],
]
ROWS_B = [
    ["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
    ["3", "Проєкт «Гамма»", "2025-05-01..2025-11-30"],
]


def sample_database() -> Database:
    db = Database("Тест")
    db.add_table(project_table("A", ROWS_A))
    db.add_table(project_table("B", ROWS_B))
    return db
