"""Тести 7 (етап 3): веб-інтерфейс, який роздає сервер, і REST API, яким він користується."""
import json
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote

from tabledb.server import DbServer, STATIC_FILES, WEB_DIR

from helpers import ROWS_A, ROWS_B

FIELDS = [{"name": "№", "type": "integer"}, {"name": "Назва", "type": "string"},
          {"name": "Період", "type": "dateInvl"}]


def fetch(url, method="GET", body=None):
    """Повертає (статус, заголовки, байти); не кидає виняток на 4xx/5xx."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


class WebServerTests(unittest.TestCase):
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

    def setUp(self):
        fetch(self.url + "/api/database/new", "POST", {"name": "Веб"})

    # --- статичні файли ----------------------------------------------------
    def test_index_page_is_served_as_html(self):
        status, headers, body = fetch(self.url + "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("charset=utf-8", headers["Content-Type"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        text = body.decode("utf-8")
        self.assertIn("<title>Табличні бази даних</title>", text)
        self.assertIn('id="btn-diff"', text)  # кнопка операції варіанта

    def test_all_declared_static_files_exist_and_have_right_type(self):
        for path, (_name, content_type) in STATIC_FILES.items():
            with self.subTest(path=path):
                status, headers, body = fetch(self.url + path)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], content_type)
                self.assertGreater(len(body), 100)

    def test_index_references_only_files_the_server_serves(self):
        _s, _h, body = fetch(self.url + "/")
        refs = re.findall(r'(?:href|src)="(/[^"]*)"', body.decode("utf-8"))
        self.assertTrue(refs)
        for ref in refs:
            self.assertIn(ref, STATIC_FILES)

    def test_other_paths_are_not_files(self):
        for path in ("/server.py", "/web/app.js", "/../tabledb/server.py", "/%2e%2e/run_server.py",
                     "/tests/helpers.py", "/api/../app.js"):
            with self.subTest(path=path):
                status, _h, body = fetch(self.url + path)
                self.assertEqual(status, 404)
                self.assertIn("error", json.loads(body))

    def test_web_directory_contains_every_served_file(self):
        import os
        for filename, _type in STATIC_FILES.values():
            self.assertTrue(os.path.isfile(os.path.join(WEB_DIR, filename)), filename)

    def test_static_route_ignores_query_string(self):
        status, _h, _b = fetch(self.url + "/app.js?v=2")
        self.assertEqual(status, 200)

    # --- REST API, як його викликає app.js ---------------------------------------
    def make(self, name, rows):
        status, _h, body = fetch(self.url + "/api/tables", "POST", {"name": name, "fields": FIELDS})
        self.assertEqual(status, 201, body)
        for row in rows:
            status, _h, body = fetch(self.url + f"/api/tables/{quote(name)}/rows", "POST", {"values": row})
            self.assertEqual(status, 201, body)

    def test_difference_through_rest_api_for_browser_flow(self):
        self.make("A", ROWS_A)
        self.make("B", ROWS_B)
        status, _h, body = fetch(self.url + "/api/difference", "POST",
                                 {"a": "A", "b": "B", "result": "R"})
        self.assertEqual(status, 201)
        result = json.loads(body)
        self.assertEqual(result["name"], "R")
        self.assertEqual(result["rows"], [ROWS_A[0], ROWS_A[2]])
        self.assertEqual(json.loads(fetch(self.url + "/api/tables")[2])["tables"], ["A", "B", "R"])

    def test_validation_error_is_json_with_field_name(self):
        self.make("A", [])
        status, headers, body = fetch(self.url + "/api/tables/A/rows", "POST",
                                      {"values": ["1", "Альфа", "2025-02-30..2025-06-30"]})
        self.assertEqual(status, 400)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertIn("Період", json.loads(body)["error"])
        self.assertEqual(json.loads(fetch(self.url + "/api/tables/A")[2])["rows"], [])

    def test_cyrillic_table_name_in_url(self):
        self.make("Проєкти", [ROWS_A[0]])
        status, _h, body = fetch(self.url + "/api/tables/" + quote("Проєкти"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["rows"], [ROWS_A[0]])

    def test_save_then_open_through_rest(self):
        self.make("A", ROWS_A)
        self.assertEqual(fetch(self.url + "/api/database/save", "POST", {"name": "веб-тест"})[0], 200)
        fetch(self.url + "/api/database/new", "POST", {"name": "Порожня"})
        self.assertEqual(json.loads(fetch(self.url + "/api/tables")[2])["tables"], [])
        self.assertEqual(fetch(self.url + "/api/database/load", "POST", {"name": "веб-тест"})[0], 200)
        self.assertEqual(json.loads(fetch(self.url + "/api/tables")[2])["tables"], ["A"])

    def test_two_browser_sessions_see_same_data(self):
        self.make("A", ROWS_A)
        first = json.loads(fetch(self.url + "/api/tables/A")[2])
        second = json.loads(fetch(self.url + "/api/tables/A")[2])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
