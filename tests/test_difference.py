"""Тести 4: індивідуальна операція варіанта — різниця таблиць A \\ B."""
import time
import unittest

from tabledb import (
    Database, DifferenceError, LocalBackend, Schema, Table, TableDifference, ValidationError,
)

from helpers import ROWS_A, ROWS_B, project_table, sample_database


class DifferenceTests(unittest.TestCase):
    def setUp(self):
        self.a = project_table("A", ROWS_A)
        self.b = project_table("B", ROWS_B)

    def texts(self, table):
        return [r.to_texts() for r in table.rows]

    def test_example_from_the_report(self):
        """Приклад зі звіту етапу 1 (таблиця 4): у R лишаються рядки 1 і 3 з таблиці A."""
        r = TableDifference.difference(self.a, self.b, "R")
        self.assertEqual(self.texts(r), [ROWS_A[0], ROWS_A[2]])

    def test_row_differing_only_in_interval_bound_is_kept(self):
        # Рядок 3 у B має кінець інтервалу 2025-11-30, а в A — 2025-12-31.
        r = TableDifference.difference(self.a, self.b, "R")
        self.assertIn(ROWS_A[2], self.texts(r))
        self.assertNotIn(ROWS_A[1], self.texts(r))  # рядок 2 однаковий у A та B

    def test_result_has_schema_of_a_and_keeps_order(self):
        b = Table("B2", Schema.from_pairs([("x", "integer"), ("y", "string"), ("z", "dateInvl")]))
        r = TableDifference.difference(self.a, b, "R")
        self.assertEqual([f.name for f in r.schema.fields], ["№", "Назва", "Період"])
        self.assertEqual(self.texts(r), ROWS_A)  # B порожня — усе з A, у тому ж порядку

    def test_not_commutative(self):
        ab = TableDifference.difference(self.a, self.b, "R1")
        ba = TableDifference.difference(self.b, self.a, "R2")
        self.assertEqual(len(ab.rows), 2)
        self.assertEqual(self.texts(ba), [ROWS_B[1]])
        self.assertNotEqual(self.texts(ab), self.texts(ba))

    def test_a_minus_a_is_empty(self):
        r = TableDifference.difference(self.a, self.a, "R")
        self.assertEqual(r.row_count(), 0)

    def test_empty_a_gives_empty_result(self):
        r = TableDifference.difference(project_table("E", []), self.b, "R")
        self.assertEqual(r.row_count(), 0)

    def test_sources_are_not_modified(self):
        before_a, before_b = self.texts(self.a), self.texts(self.b)
        r = TableDifference.difference(self.a, self.b, "R")
        r.add_text_row(["9", "новий", "2025-01-01..2025-01-02"])  # зміна результату
        self.assertEqual(self.texts(self.a), before_a)
        self.assertEqual(self.texts(self.b), before_b)

    def test_duplicates_in_a_are_kept_when_absent_from_b(self):
        a = project_table("A", [ROWS_A[0], ROWS_A[0], ROWS_A[1]])
        r = TableDifference.difference(a, self.b, "R")
        self.assertEqual(self.texts(r), [ROWS_A[0], ROWS_A[0]])

    def test_equal_real_spellings_count_as_same_row(self):
        schema = Schema.from_pairs([("x", "real")])
        a, b = Table("A", schema), Table("B", schema)
        a.add_text_row(["1"])
        a.add_text_row(["2.50"])
        b.add_text_row(["1.0"])
        self.assertEqual(self.texts(TableDifference.difference(a, b, "R")), [["2.5"]])

    def test_incompatible_field_count(self):
        b = Table("B", Schema.from_pairs([("a", "integer")]))
        with self.assertRaises(DifferenceError) as ctx:
            TableDifference.difference(self.a, b, "R")
        self.assertIn("кількість полів", str(ctx.exception))

    def test_incompatible_field_type(self):
        b = Table("B", Schema.from_pairs([("a", "integer"), ("b", "string"), ("c", "date")]))
        with self.assertRaises(DifferenceError) as ctx:
            TableDifference.difference(self.a, b, "R")
        self.assertIn("тип поля 3", str(ctx.exception))

    def test_empty_result_name_rejected(self):
        with self.assertRaises(ValidationError):
            TableDifference.difference(self.a, self.b, "  ")

    def test_scales_to_many_rows(self):
        schema = Schema.from_pairs([("n", "integer"), ("s", "string")])
        a, b = Table("A", schema), Table("B", schema)
        for i in range(20000):
            a.add_text_row([str(i), f"рядок {i}"])
            if i % 2 == 0:
                b.add_text_row([str(i), f"рядок {i}"])
        started = time.time()
        r = TableDifference.difference(a, b, "R")
        self.assertEqual(r.row_count(), 10000)
        self.assertLess(time.time() - started, 5)  # O(n + m), а не O(n·m)


class DifferenceThroughBackendTests(unittest.TestCase):
    """Різниця як операція над базою: реєстрація результату й відмови без побічних ефектів."""

    def setUp(self):
        self.backend = LocalBackend(sample_database())

    def test_result_is_registered_in_database(self):
        result = self.backend.difference("A", "B", "R")
        self.assertEqual(self.backend.list_tables(), ["A", "B", "R"])
        self.assertEqual(result["rows"], [ROWS_A[0], ROWS_A[2]])
        self.assertEqual(self.backend.get_table("R")["rows"], result["rows"])

    def test_missing_table(self):
        from tabledb import NotFoundError

        with self.assertRaises(NotFoundError):
            self.backend.difference("A", "Немає", "R")
        self.assertEqual(self.backend.list_tables(), ["A", "B"])

    def test_taken_result_name(self):
        with self.assertRaises(ValidationError):
            self.backend.difference("A", "B", "A")
        self.assertEqual(self.backend.list_tables(), ["A", "B"])
        self.assertEqual(self.backend.get_table("A")["rows"], ROWS_A)  # A не зіпсовано

    def test_incompatible_schemas_register_nothing(self):
        self.backend.create_table("C", [{"name": "x", "type": "integer"}])
        with self.assertRaises(DifferenceError):
            self.backend.difference("A", "C", "R")
        self.assertEqual(self.backend.list_tables(), ["A", "B", "C"])

    def test_a_minus_a_through_backend(self):
        self.assertEqual(self.backend.difference("A", "A", "Порожня")["rows"], [])

    def test_result_can_be_edited_and_used_again(self):
        self.backend.difference("A", "B", "R")
        self.backend.add_row("R", ["7", "Додано", "2025-01-01..2025-01-02"])
        again = self.backend.difference("R", "B", "R2")
        self.assertEqual(len(again["rows"]), 3)


if __name__ == "__main__":
    unittest.main()
