"""Збереження бази на диск і зчитування з диска.

Формат файлу .tdb — текстовий JSON у UTF-8:

    {"format": "tabledb", "version": 1, "name": "...",
     "tables": [{"name": "...", "fields": [{"name": "...", "type": "integer"}],
                 "rows": [["1", "текст"], ...]}]}

Значення зберігаються в канонічному текстовому поданні, а під час зчитування
кожне значення проходить через ValueFactory. Тому пошкоджений файл або
некоректні значення відхиляються без часткового завантаження.
"""
from __future__ import annotations

import json
import os
import tempfile

from .errors import DbError, FormatError, StorageError
from .model import Database, Table

FORMAT_NAME = "tabledb"
FORMAT_VERSION = 1


class DatabaseStorage:
    @staticmethod
    def to_dict(db: Database) -> dict:
        return {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "name": db.name,
            "tables": [db.get_table(n).to_dict() for n in db.table_names()],
        }

    @staticmethod
    def from_dict(data: dict) -> Database:
        if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
            raise FormatError("це не файл табличної бази даних")
        if data.get("version") != FORMAT_VERSION:
            raise FormatError(f"непідтримувана версія формату: {data.get('version')}")
        try:
            db = Database(str(data["name"]))
            for raw in data["tables"]:
                db.add_table(Table.from_dict(raw))
        except DbError as exc:
            raise FormatError(f"файл пошкоджений: {exc}") from None
        except (KeyError, TypeError):
            raise FormatError("файл пошкоджений: відсутні обов'язкові розділи") from None
        return db

    @staticmethod
    def save(db: Database, path: str) -> None:
        """Атомарний запис: спочатку у тимчасовий файл, потім заміна."""
        payload = json.dumps(DatabaseStorage.to_dict(db), ensure_ascii=False, indent=1)
        directory = os.path.dirname(os.path.abspath(path))
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, path)
            tmp_path = None
        except OSError as exc:
            raise StorageError(f"не вдалося записати файл: {exc.strerror or exc}") from None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    def load(path: str) -> Database:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise StorageError(f"файл не знайдено: {path}") from None
        except OSError as exc:
            raise StorageError(f"не вдалося прочитати файл: {exc.strerror or exc}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise FormatError("файл пошкоджений: некоректний вміст") from None
        return DatabaseStorage.from_dict(data)
