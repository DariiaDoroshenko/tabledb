"""Тести 3: збереження бази на диск і зчитування з диска."""
import json
import os
import tempfile
import unittest

from tabledb import (
    Database, DatabaseStorage, FormatError, LocalBackend, Schema, StorageError,
)

from helpers import sample_database


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, "db.tdb")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_roundtrip_preserves_everything(self):
        db = sample_database()
        db.create_table("Усі типи", Schema.from_pairs([
            ("i", "integer"), ("r", "real"), ("c", "char"), ("s", "string"),
            ("d", "date"), ("p", "dateInvl"),
        ]))
        db.get_table("Усі типи").add_text_row(
            ["-5", "2.5", "Ї", "рядок із «лапками» та \"цитатами\"", "2024-02-29", "2024-01-01..2024-12-31"])
        DatabaseStorage.save(db, self.path)
        loaded = DatabaseStorage.load(self.path)
        self.assertEqual(loaded.name, db.name)
        self.assertEqual(loaded.table_names(), db.table_names())
        for name in db.table_names():
            self.assertEqual(loaded.get_table(name).to_dict(), db.get_table(name).to_dict())

    def test_file_is_utf8_json_with_readable_text(self):
        DatabaseStorage.save(sample_database(), self.path)
        with open(self.path, "rb") as f:
            raw = f.read().decode("utf-8")
        self.assertIn("Проєкт «Альфа»", raw)  # кирилиця не екранується
        self.assertEqual(json.loads(raw)["format"], "tabledb")

    def test_empty_database_roundtrip(self):
        DatabaseStorage.save(Database("Порожня"), self.path)
        loaded = DatabaseStorage.load(self.path)
        self.assertEqual((loaded.name, loaded.table_names()), ("Порожня", []))

    def test_table_without_rows_roundtrip(self):
        db = Database()
        db.create_table("Пуста", Schema.from_pairs([("a", "integer")]))
        DatabaseStorage.save(db, self.path)
        self.assertEqual(DatabaseStorage.load(self.path).get_table("Пуста").row_count(), 0)

    def test_save_leaves_no_temporary_files(self):
        DatabaseStorage.save(sample_database(), self.path)
        DatabaseStorage.save(sample_database(), self.path)  # перезапис
        self.assertEqual(os.listdir(self.dir), ["db.tdb"])

    def test_save_into_missing_directory_fails_cleanly(self):
        with self.assertRaises(StorageError):
            DatabaseStorage.save(sample_database(), os.path.join(self.dir, "немає", "db.tdb"))

    def test_load_missing_file(self):
        with self.assertRaises(StorageError):
            DatabaseStorage.load(os.path.join(self.dir, "nope.tdb"))

    def test_load_garbage(self):
        for text in ["", "не json", "[1, 2, 3]", "{}", '{"format": "other"}']:
            with self.subTest(text=text):
                self.write(text)
                with self.assertRaises(FormatError):
                    DatabaseStorage.load(self.path)

    def test_load_binary_garbage(self):
        with open(self.path, "wb") as f:
            f.write(b"\xff\xfe\x00\x01")
        with self.assertRaises(FormatError):
            DatabaseStorage.load(self.path)

    def test_load_wrong_version(self):
        self.write(json.dumps({"format": "tabledb", "version": 99, "name": "x", "tables": []}))
        with self.assertRaises(FormatError):
            DatabaseStorage.load(self.path)

    def test_load_rejects_invalid_values_and_names_the_row(self):
        DatabaseStorage.save(sample_database(), self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        data["tables"][0]["rows"][1][0] = "не число"
        self.write(json.dumps(data, ensure_ascii=False))
        with self.assertRaises(FormatError) as ctx:
            DatabaseStorage.load(self.path)
        self.assertIn("рядок 2", str(ctx.exception))

    def test_load_rejects_duplicate_tables_and_missing_sections(self):
        DatabaseStorage.save(sample_database(), self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        dup = dict(data)
        dup["tables"] = [data["tables"][0], data["tables"][0]]
        self.write(json.dumps(dup, ensure_ascii=False))
        with self.assertRaises(FormatError):
            DatabaseStorage.load(self.path)
        del data["tables"]
        self.write(json.dumps(data, ensure_ascii=False))
        with self.assertRaises(FormatError):
            DatabaseStorage.load(self.path)

    def test_failed_load_keeps_current_database(self):
        backend = LocalBackend(sample_database())
        self.write("пошкоджено")
        with self.assertRaises(FormatError):
            backend.load(self.path)
        self.assertEqual(backend.list_tables(), ["A", "B"])
        self.assertEqual(backend.get_table("A")["rows"][0][1], "Проєкт «Альфа»")


if __name__ == "__main__":
    unittest.main()
