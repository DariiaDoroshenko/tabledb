"""Клієнт віддаленого сервера: реалізація Backend через HTTP/JSON (urllib)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence
from urllib.parse import quote

from .errors import DbError, NotFoundError, StorageError
from .service import Backend


class RemoteBackend(Backend):
    is_remote = True

    def __init__(self, base_url: str, timeout: float = 5.0):
        base_url = base_url.strip().rstrip("/")
        if "://" not in base_url:
            base_url = "http://" + base_url
        self.base_url = base_url
        self.timeout = timeout

    @property
    def description(self) -> str:
        return f"Сервер {self.base_url}"

    # --- транспорт ---------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/api/" + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = _error_message(exc)
            if exc.code == 404:
                raise NotFoundError(message) from None
            raise DbError(message) from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise StorageError(f"сервер {self.base_url} недоступний") from None
        except ValueError:
            raise DbError("сервер повернув некоректну відповідь") from None

    def ping(self) -> str:
        """Перевіряє з'єднання; повертає ім'я бази на сервері."""
        return self._call("GET", "ping")["database"]

    # --- Backend -----------------------------------------------------------
    def new_database(self, name: str = "Нова база") -> None:
        self._call("POST", "database/new", {"name": name})

    def database_name(self) -> str:
        return self._call("GET", "database")["name"]

    def list_tables(self) -> list[str]:
        return self._call("GET", "tables")["tables"]

    def get_table(self, name: str) -> dict:
        return self._call("GET", "tables/" + quote(name, safe=""))

    def create_table(self, name: str, fields: Sequence[dict]) -> dict:
        return self._call("POST", "tables", {"name": name, "fields": list(fields)})

    def drop_table(self, name: str) -> None:
        self._call("DELETE", "tables/" + quote(name, safe=""))

    def add_row(self, table: str, values: Sequence[str]) -> int:
        return self._call(
            "POST", f"tables/{quote(table, safe='')}/rows", {"values": list(values)}
        )["index"]

    def update_row(self, table: str, index: int, values: Sequence[str]) -> None:
        self._call(
            "PUT", f"tables/{quote(table, safe='')}/rows/{int(index)}", {"values": list(values)}
        )

    def difference(self, a: str, b: str, result: str) -> dict:
        return self._call("POST", "difference", {"a": a, "b": b, "result": result})

    def save(self, path: str) -> None:
        self._call("POST", "database/save", {"name": path})

    def load(self, path: str) -> None:
        self._call("POST", "database/load", {"name": path})

    def list_files(self) -> list[str]:
        return self._call("GET", "database/files")["files"]


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        return json.loads(exc.read().decode("utf-8"))["error"]
    except Exception:
        return f"помилка сервера (HTTP {exc.code})"
