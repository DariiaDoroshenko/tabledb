"""Тести 2: схема, таблиця, рядки (створення, валідація, редагування) і база."""
import time
import unittest

from tabledb import (
    Database, Field, FieldType, NotFoundError, Row, Schema, Table, ValidationError,
)
from tabledb.values import IntegerValue, StringValue

from helpers import PROJECT_FIELDS, project_table


class SchemaTests(unittest.TestCase):
    def test_needs_at_least_one_field(self):
        with self.assertRaises(ValidationError):
            Schema([])

    def test_field_names_unique_and_nonempty(self):
        with self.assertRaises(ValidationError):
            Schema.from_pairs([("a", "integer"), ("a", "string")])
        with self.assertRaises(ValidationError):
            Schema.from_pairs([("  ", "integer")])

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValidationError):
            Schema.from_pairs([("a", "boolean")])

    def test_compatibility_ignores_names_but_not_types(self):
        a = Schema.from_pairs([("x", "integer"), ("y", "string")])
        b = Schema.from_pairs([("p", "integer"), ("q", "string")])
        c = Schema.from_pairs([("x", "integer"), ("y", "char")])
        d = Schema.from_pairs([("x", "integer")])
        self.assertTrue(a.is_compatible_with(b))
        self.assertFalse(a.is_compatible_with(c))
        self.assertFalse(a.is_compatible_with(d))
        self.assertIn("кількість", a.incompatibility(d))
        self.assertIn("тип поля 2", a.incompatibility(c))


class TableRowTests(unittest.TestCase):
    def setUp(self):
        self.t = project_table("Проєкти", [])

    def test_add_valid_row(self):
        self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01"])
        self.assertEqual(self.t.row_count(), 1)
        self.assertEqual(self.t.get_row(0).to_texts(), ["1", "Альфа", "2025-01-01..2025-02-01"])

    def test_invalid_value_leaves_table_unchanged(self):
        self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01"])
        with self.assertRaises(ValidationError) as ctx:
            self.t.add_text_row(["2", "Бета", "2025-02-30..2025-03-01"])
        self.assertIn("Період", str(ctx.exception))
        self.assertEqual(self.t.row_count(), 1)

    def test_wrong_number_of_values(self):
        with self.assertRaises(ValidationError):
            self.t.add_text_row(["1", "Альфа"])
        with self.assertRaises(ValidationError):
            self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01", "зайве"])
        self.assertEqual(self.t.row_count(), 0)

    def test_first_error_is_reported(self):
        with self.assertRaises(ValidationError) as ctx:
            self.t.add_text_row(["abc", "Альфа", "bad"])
        self.assertIn("№", str(ctx.exception))

    def test_row_of_wrong_types_rejected(self):
        bad = Row([StringValue("1"), StringValue("x"), StringValue("y")])
        with self.assertRaises(ValidationError):
            self.t.add_row(bad)
        self.assertEqual(self.t.row_count(), 0)

    def test_update_row(self):
        self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01"])
        old = self.t.get_row(0)
        self.t.update_text_row(0, ["1", "Альфа-2", "2025-01-01..2025-03-01"])
        self.assertEqual(self.t.get_row(0).value_at(1).to_text(), "Альфа-2")
        self.assertFalse(self.t.contains(old))  # індекс оновлено
        self.assertTrue(self.t.contains(self.t.get_row(0)))

    def test_invalid_update_keeps_old_row(self):
        self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01"])
        before = self.t.get_row(0).to_texts()
        with self.assertRaises(ValidationError):
            self.t.update_text_row(0, ["x", "Альфа", "2025-01-01..2025-02-01"])
        self.assertEqual(self.t.get_row(0).to_texts(), before)
        self.assertTrue(self.t.contains(self.t.get_row(0)))

    def test_row_index_out_of_range(self):
        with self.assertRaises(NotFoundError):
            self.t.get_row(0)
        with self.assertRaises(NotFoundError):
            self.t.update_text_row(3, ["1", "a", "2025-01-01..2025-01-02"])

    def test_contains_uses_all_fields(self):
        self.t.add_text_row(["1", "Альфа", "2025-01-01..2025-02-01"])
        same = Row([IntegerValue(1), StringValue("Альфа"),
                    self.t.get_row(0).value_at(2)])
        other = project_table("x", [["1", "Альфа", "2025-01-01..2025-02-02"]]).get_row(0)
        self.assertTrue(self.t.contains(same))
        self.assertFalse(self.t.contains(other))

    def test_duplicate_rows_are_allowed(self):
        self.t.add_text_row(["1", "a", "2025-01-01..2025-01-02"])
        self.t.add_text_row(["1", "a", "2025-01-01..2025-01-02"])
        self.assertEqual(self.t.row_count(), 2)

    def test_table_name_validation(self):
        with self.assertRaises(ValidationError):
            Table("   ", Schema.from_pairs(PROJECT_FIELDS))
        self.assertEqual(Table("  Т  ", Schema.from_pairs(PROJECT_FIELDS)).name, "Т")


class CapacityTests(unittest.TestCase):
    """Кількість полів, рядків і таблиць принципово не обмежена."""

    def test_many_fields_and_rows(self):
        fields = [(f"f{i}", ("integer", "real", "char", "string")[i % 4]) for i in range(60)]
        t = Table("Широка", Schema.from_pairs(fields))
        sample = [("7", "2.5", "x", "текст")[i % 4] for i in range(60)]
        started = time.time()
        for _ in range(3000):
            t.add_text_row(sample)
        self.assertEqual(t.row_count(), 3000)
        self.assertLess(time.time() - started, 5)

    def test_many_tables(self):
        db = Database()
        for i in range(500):
            db.create_table(f"T{i}", Schema.from_pairs([("a", "integer")]))
        self.assertEqual(len(db.table_names()), 500)


class DatabaseTests(unittest.TestCase):
    def test_create_get_drop(self):
        db = Database()
        t = db.create_table("A", Schema.from_pairs([("a", "integer")]))
        self.assertIs(db.get_table("A"), t)
        db.drop_table("A")
        self.assertEqual(db.table_names(), [])
        with self.assertRaises(NotFoundError):
            db.get_table("A")
        with self.assertRaises(NotFoundError):
            db.drop_table("A")

    def test_duplicate_name_rejected(self):
        db = Database()
        db.create_table("A", Schema.from_pairs([("a", "integer")]))
        with self.assertRaises(ValidationError):
            db.create_table("A", Schema.from_pairs([("b", "string")]))
        self.assertEqual(db.table_names(), ["A"])

    def test_names_keep_creation_order(self):
        db = Database()
        for n in ["Ц", "А", "Б"]:
            db.create_table(n, Schema.from_pairs([("a", "integer")]))
        self.assertEqual(db.table_names(), ["Ц", "А", "Б"])

    def test_names_are_case_sensitive(self):
        db = Database()
        db.create_table("a", Schema.from_pairs([("a", "integer")]))
        db.create_table("A", Schema.from_pairs([("a", "integer")]))
        self.assertEqual(len(db.table_names()), 2)

    def test_dropped_table_does_not_affect_others(self):
        db = Database()
        db.add_table(project_table("A", [["1", "a", "2025-01-01..2025-01-02"]]))
        db.add_table(project_table("B", []))
        db.drop_table("B")
        self.assertEqual(db.get_table("A").row_count(), 1)


if __name__ == "__main__":
    unittest.main()
