"""Тести 5: один набір перевірок для локального та віддаленого (HTTP) бекенду.

Те саме GUI працює з обома, тому вони мають поводитися однаково.
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request

from tabledb import DbError, LocalBackend, NotFoundError, StorageError
from tabledb.client import RemoteBackend
from tabledb.server import DbServer, safe_filename

from helpers import PROJECT_FIELDS, ROWS_A, ROWS_B

FIELDS = [{"name": n, "type": t} for n, t in PROJECT_FIELDS]


class BackendContract:
    """Спільні перевірки; конкретні класи задають make_backend() і file_ref()."""

    def make_backend(self):
        raise NotImplementedError

    def file_ref(self, name):
        raise NotImplementedError

    def setUp(self):
        self.be = self.make_backend()
        self.be.new_database("Контракт")

    def fill(self):
        self.be.create_table("A", FIELDS)
        self.be.create_table("B", FIELDS)
        for r in ROWS_A:
            self.be.add_row("A", r)
        for r in ROWS_B:
            self.be.add_row("B", r)

    def test_create_and_list_tables(self):
        created = self.be.create_table("Проєкти", FIELDS)
        self.assertEqual(created["fields"], FIELDS)
        self.assertEqual(self.be.list_tables(), ["Проєкти"])
        self.assertEqual(self.be.get_table("Проєкти")["rows"], [])

    def test_table_names_with_special_characters(self):
        for name in ["Таблиця/1", "а б?в#г", "100% «лапки»"]:
            self.be.create_table(name, FIELDS)
            self.assertEqual(self.be.get_table(name)["name"], name)

    def test_create_table_validation(self):
        with self.assertRaises(DbError):
            self.be.create_table("", FIELDS)
        with self.assertRaises(DbError):
            self.be.create_table("X", [])
        with self.assertRaises(DbError):
            self.be.create_table("X", [{"name": "a", "type": "integer"}, {"name": "a", "type": "real"}])
        with self.assertRaises(DbError):
            self.be.create_table("X", [{"name": "a", "type": "nope"}])
        self.assertEqual(self.be.list_tables(), [])

    def test_duplicate_table_name(self):
        self.be.create_table("A", FIELDS)
        with self.assertRaises(DbError):
            self.be.create_table("A", FIELDS)

    def test_drop_table(self):
        self.be.create_table("A", FIELDS)
        self.be.drop_table("A")
        self.assertEqual(self.be.list_tables(), [])
        with self.assertRaises(NotFoundError):
            self.be.drop_table("A")

    def test_missing_table(self):
        with self.assertRaises(NotFoundError):
            self.be.get_table("Немає")

    def test_add_and_view_rows(self):
        self.fill()
        self.assertEqual(self.be.get_table("A")["rows"], ROWS_A)
        self.assertEqual(self.be.add_row("A", ["4", "Дельта", "2026-01-01..2026-01-31"]), 3)

    def test_invalid_row_is_rejected_with_field_name(self):
        self.fill()
        with self.assertRaises(DbError) as ctx:
            self.be.add_row("A", ["4", "Дельта", "2026-02-30..2026-03-01"])
        self.assertIn("Період", str(ctx.exception))
        self.assertEqual(len(self.be.get_table("A")["rows"]), 3)

    def test_edit_row(self):
        self.fill()
        self.be.update_row("A", 1, ["2", "Бета (нова)", "2025-03-15..2025-04-01"])
        self.assertEqual(self.be.get_table("A")["rows"][1][1], "Бета (нова)")
        with self.assertRaises(DbError):
            self.be.update_row("A", 1, ["x", "q", "2025-01-01..2025-01-02"])
        self.assertEqual(self.be.get_table("A")["rows"][1][1], "Бета (нова)")
        with self.assertRaises(NotFoundError):
            self.be.update_row("A", 99, ["1", "q", "2025-01-01..2025-01-02"])

    def test_difference(self):
        self.fill()
        result = self.be.difference("A", "B", "R")
        self.assertEqual(result["rows"], [ROWS_A[0], ROWS_A[2]])
        self.assertEqual(self.be.list_tables(), ["A", "B", "R"])

    def test_difference_errors_change_nothing(self):
        self.fill()
        self.be.create_table("C", [{"name": "x", "type": "integer"}])
        with self.assertRaises(DbError):
            self.be.difference("A", "C", "R")  # несумісні схеми
        with self.assertRaises(DbError):
            self.be.difference("A", "B", "A")  # ім'я зайняте
        with self.assertRaises(NotFoundError):
            self.be.difference("A", "Немає", "R")
        self.assertEqual(self.be.list_tables(), ["A", "B", "C"])

    def test_save_and_load_roundtrip(self):
        self.fill()
        self.be.save(self.file_ref("база"))
        self.be.new_database("Інша")
        self.assertEqual(self.be.list_tables(), [])
        self.be.load(self.file_ref("база"))
        self.assertEqual(self.be.list_tables(), ["A", "B"])
        self.assertEqual(self.be.get_table("B")["rows"], ROWS_B)

    def test_load_of_missing_file_keeps_database(self):
        self.fill()
        with self.assertRaises(DbError):
            self.be.load(self.file_ref("немає-такого"))
        self.assertEqual(self.be.list_tables(), ["A", "B"])

    def test_new_database_clears_tables(self):
        self.fill()
        self.be.new_database("Чиста")
        self.assertEqual(self.be.list_tables(), [])


class LocalBackendTests(BackendContract, unittest.TestCase):
    def make_backend(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        return LocalBackend()

    def file_ref(self, name):
        return os.path.join(self._tmp.name, name + ".tdb")


class RemoteBackendTests(BackendContract, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.server = DbServer(("127.0.0.1", 0), cls._tmp.name)
        cls.server.start_in_thread()
        cls.url = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls._tmp.cleanup()

    def make_backend(self):
        return RemoteBackend(self.url)

    def file_ref(self, name):
        return name  # на сервері передається ім'я, а не шлях

    # --- перевірки, специфічні для мережевого режиму -----------------------
    def test_ping_and_files_listing(self):
        self.assertEqual(self.be.ping(), "Контракт")
        self.be.save("перелік")
        self.assertIn("перелік.tdb", self.be.list_files())

    def test_two_clients_share_one_database(self):
        other = RemoteBackend(self.url)
        self.be.create_table("Спільна", FIELDS)
        self.assertEqual(other.list_tables(), ["Спільна"])
        other.add_row("Спільна", ["1", "від другого клієнта", "2025-01-01..2025-01-02"])
        self.assertEqual(len(self.be.get_table("Спільна")["rows"]), 1)

    def test_unreachable_server(self):
        dead = RemoteBackend("http://127.0.0.1:1", timeout=1)
        with self.assertRaises(StorageError) as ctx:
            dead.list_tables()
        self.assertIn("недоступний", str(ctx.exception))

    def test_path_traversal_is_rejected(self):
        for bad in ["../evil", "..\\evil", "/etc/passwd", "a/b", ".hidden", ""]:
            with self.subTest(bad=bad):
                with self.assertRaises(DbError):
                    self.be.save(bad)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self._tmp.name), "evil.tdb")))

    def test_raw_http_errors(self):
        def raw(method, path, body=None):
            req = urllib.request.Request(self.url + path, data=body, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        self.assertEqual(raw("GET", "/api/ping")[0], 200)
        self.assertEqual(raw("GET", "/api/unknown")[0], 404)
        self.assertEqual(raw("GET", "/other")[0], 404)
        self.assertEqual(raw("GET", "/api/tables/%D0%9D%D0%B5%D0%BC%D0%B0%D1%94")[0], 404)
        self.assertEqual(raw("POST", "/api/tables", b"{not json")[0], 400)
        self.assertEqual(raw("POST", "/api/tables", b"[1,2]")[0], 400)
        self.assertEqual(raw("POST", "/api/tables", b"{}")[0], 400)  # немає обов'язкових полів
        code, payload = raw("POST", "/api/tables", json.dumps({"name": "X", "fields": []}).encode())
        self.assertEqual(code, 400)
        self.assertIn("error", payload)


class SafeFilenameTests(unittest.TestCase):
    def test_adds_suffix_once(self):
        self.assertEqual(safe_filename("база"), "база.tdb")
        self.assertEqual(safe_filename("база.tdb"), "база.tdb")

    def test_rejects_unsafe_names(self):
        for bad in ["", " ", "../x", "a/b", "a\\b", ".x", "x" * 101, None]:
            with self.subTest(bad=bad):
                with self.assertRaises(DbError):
                    safe_filename(bad)


if __name__ == "__main__":
    unittest.main()
