"""HTTP/JSON-сервер табличної бази даних (додаткове завдання: віддалений сервер).

Сервер тримає одну спільну базу в пам'яті та віддає її через REST-подібний API:

    GET    /api/ping
    GET    /api/database                      -> {"name": ...}
    POST   /api/database/new                  {"name": ...}
    POST   /api/database/save                 {"name": "<ім'я файлу>"}
    POST   /api/database/load                 {"name": "<ім'я файлу>"}
    GET    /api/database/files                -> {"files": [...]}
    GET    /api/tables                        -> {"tables": [...]}
    POST   /api/tables                        {"name", "fields"}      -> таблиця
    GET    /api/tables/<ім'я>                 -> таблиця
    DELETE /api/tables/<ім'я>
    POST   /api/tables/<ім'я>/rows            {"values": [...]}       -> {"index": n}
    PUT    /api/tables/<ім'я>/rows/<індекс>   {"values": [...]}
    POST   /api/difference                    {"a", "b", "result"}    -> таблиця

Помилки: {"error": "повідомлення"} зі статусом 400 (некоректні дані), 404 (не
знайдено) або 500. Збереження доступне лише в теці сервера (data_dir): клієнт
передає ім'я файлу, а не шлях.

Автентифікації немає: за замовчуванням сервер слухає лише 127.0.0.1.
"""
from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .errors import DbError, NotFoundError, ValidationError
from .service import LocalBackend

MAX_BODY = 5 * 1024 * 1024
_FILE_RE = re.compile(r"[\w\-. ()]+")


def safe_filename(name: str) -> str:
    """Перетворює ім'я бази на безпечне ім'я файлу (без шляхів) із суфіксом .tdb."""
    if not isinstance(name, str):
        raise ValidationError("ім'я файлу має бути текстом")
    name = name.strip()
    if not name or len(name) > 100 or name.startswith(".") or not _FILE_RE.fullmatch(name):
        raise ValidationError(
            "недопустиме ім'я файлу (літери, цифри, пробіл, «-», «_», «.», «()»)"
        )
    return name if name.endswith(".tdb") else name + ".tdb"


class DbServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], data_dir: str, log=None):
        self.backend = LocalBackend()
        self.lock = threading.RLock()
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.log = log or (lambda msg: None)
        super().__init__(address, _Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self.shutdown()
        self.server_close()

    def file_path(self, name: str) -> str:
        return os.path.join(self.data_dir, safe_filename(name))

    def list_files(self) -> list[str]:
        return sorted(f for f in os.listdir(self.data_dir) if f.endswith(".tdb"))


class _Handler(BaseHTTPRequestHandler):
    server: DbServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # перенаправляємо журнал у server.log
        self.server.log("%s %s" % (self.address_string(), fmt % args))

    # --- допоміжне ---------------------------------------------------------
    def _send(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValidationError("запит завеликий")
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("тіло запиту не є коректним JSON") from None
        if not isinstance(data, dict):
            raise ValidationError("тіло запиту має бути JSON-об'єктом")
        return data

    def _handle(self, method: str) -> None:
        try:
            parts = [unquote(p) for p in urlsplit(self.path).path.strip("/").split("/")]
            if not parts or parts[0] != "api":
                raise NotFoundError("невідомий адрес")
            body = self._read_json() if method in ("POST", "PUT") else {}
            with self.server.lock:
                status, payload = self._route(method, parts[1:], body)
            self._send(status, payload)
        except NotFoundError as exc:
            self._send(404, {"error": str(exc)})
        except DbError as exc:
            self._send(400, {"error": str(exc)})
        except (KeyError, TypeError, ValueError):
            self._send(400, {"error": "некоректний запит"})
        except Exception as exc:  # непередбачена помилка не повинна ламати сервер
            self.server.log(f"ПОМИЛКА: {exc!r}")
            self._send(500, {"error": "внутрішня помилка сервера"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    # --- маршрути ----------------------------------------------------------
    def _route(self, method: str, p: list[str], body: dict):
        be = self.server.backend
        if p == ["ping"] and method == "GET":
            return 200, {"status": "ok", "database": be.database_name()}
        if p == ["database"] and method == "GET":
            return 200, {"name": be.database_name()}
        if p == ["database", "new"] and method == "POST":
            be.new_database(str(body.get("name") or "Нова база"))
            return 200, {"ok": True}
        if p == ["database", "files"] and method == "GET":
            return 200, {"files": self.server.list_files()}
        if p == ["database", "save"] and method == "POST":
            path = self.server.file_path(body.get("name"))
            be.save(path)
            return 200, {"file": os.path.basename(path)}
        if p == ["database", "load"] and method == "POST":
            path = self.server.file_path(body.get("name"))
            be.load(path)
            return 200, {"file": os.path.basename(path)}
        if p == ["tables"] and method == "GET":
            return 200, {"tables": be.list_tables()}
        if p == ["tables"] and method == "POST":
            return 201, be.create_table(body["name"], body["fields"])
        if len(p) == 2 and p[0] == "tables":
            if method == "GET":
                return 200, be.get_table(p[1])
            if method == "DELETE":
                be.drop_table(p[1])
                return 200, {"ok": True}
        if len(p) == 3 and p[0] == "tables" and p[2] == "rows" and method == "POST":
            return 201, {"index": be.add_row(p[1], body["values"])}
        if len(p) == 4 and p[0] == "tables" and p[2] == "rows" and method == "PUT":
            be.update_row(p[1], int(p[3]), body["values"])
            return 200, {"ok": True}
        if p == ["difference"] and method == "POST":
            return 201, be.difference(body["a"], body["b"], body["result"])
        raise NotFoundError("невідомий адрес")


def serve(host: str, port: int, data_dir: str) -> None:
    """Запускає сервер у поточному потоці до Ctrl+C."""
    server = DbServer((host, port), data_dir, log=print)
    print(f"Сервер запущено: http://{host}:{server.port}  (теку даних: {server.data_dir})")
    print("Зупинити: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nЗупинено.")
    finally:
        server.server_close()
