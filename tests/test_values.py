"""Тести 1: типи полів і валідація значень (integer, real, char, string, date, dateInvl)."""
import unittest

from tabledb import FieldType, ValidationError, ValueFactory
from tabledb.values import DateInvlValue, DateValue, IntegerValue, RealValue


def make(ftype, text):
    return ValueFactory.create(FieldType(ftype), text)


class IntegerTests(unittest.TestCase):
    def test_valid_and_canonical_text(self):
        self.assertEqual(make("integer", "42").to_text(), "42")
        self.assertEqual(make("integer", "+45").to_text(), "45")
        self.assertEqual(make("integer", "-0").to_text(), "0")
        self.assertEqual(make("integer", " 7 ").to_text(), "7")

    def test_invalid(self):
        for bad in ["", "4.5", "abc", "1e3", "--1", "٣"]:  # остання — арабсько-індійська цифра
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("integer", bad)

    def test_int64_bounds(self):
        self.assertEqual(make("integer", str(2 ** 63 - 1)).to_text(), str(2 ** 63 - 1))
        with self.assertRaises(ValidationError):
            make("integer", str(2 ** 63))
        with self.assertRaises(ValidationError):
            make("integer", str(-(2 ** 63) - 1))


class RealTests(unittest.TestCase):
    def test_valid(self):
        for text, expected in [("3.14", 3.14), ("-0.5", -0.5), ("1e-3", 0.001), ("5", 5.0), (".5", 0.5)]:
            with self.subTest(text=text):
                self.assertEqual(make("real", text)._raw(), expected)

    def test_invalid(self):
        for bad in ["", ".", "nan", "inf", "-inf", "1,5", "1_0", "e5", "0x10"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("real", bad)

    def test_equal_spellings_give_equal_values(self):
        self.assertEqual(make("real", "1"), make("real", "1.0"))
        self.assertEqual(make("real", "1e0"), make("real", "+1.00"))

    def test_non_finite_rejected_in_constructor(self):
        with self.assertRaises(ValidationError):
            RealValue(float("nan"))


class CharAndStringTests(unittest.TestCase):
    def test_char(self):
        self.assertEqual(make("char", "Ж").to_text(), "Ж")
        for bad in ["", "ab", "\n"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("char", bad)

    def test_string(self):
        self.assertEqual(make("string", "").to_text(), "")
        self.assertEqual(make("string", "Іваненко Іван").to_text(), "Іваненко Іван")
        with self.assertRaises(ValidationError):
            make("string", "перший\nдругий")


class DateTests(unittest.TestCase):
    def test_valid_dates(self):
        self.assertEqual(make("date", "2026-10-07").to_text(), "2026-10-07")
        self.assertEqual(make("date", "2024-02-29").to_text(), "2024-02-29")  # високосний
        self.assertEqual(make("date", "2000-02-29").to_text(), "2000-02-29")  # кратний 400
        self.assertEqual(make("date", "0001-01-01").to_text(), "0001-01-01")
        self.assertEqual(make("date", "9999-12-31").to_text(), "9999-12-31")

    def test_nonexistent_dates(self):
        for bad in ["2025-02-29", "1900-02-29", "2025-04-31", "2025-02-30", "2025-06-00"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("date", bad)

    def test_bad_format_and_ranges(self):
        for bad in ["", "2025-1-5", "05.10.2025", "2025/10/05", "2025-13-01", "0000-01-01", "20251005", "abc"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("date", bad)

    def test_leap_year_helpers(self):
        self.assertTrue(DateValue(2024, 1, 1).is_leap_year())
        self.assertFalse(DateValue(1900, 1, 1).is_leap_year())
        self.assertTrue(DateValue(2000, 1, 1).is_leap_year())
        self.assertEqual(DateValue(2025, 2, 1).days_in_month(), 28)
        self.assertEqual(DateValue(2024, 2, 1).days_in_month(), 29)
        self.assertEqual(DateValue(2025, 4, 1).days_in_month(), 30)

    def test_ordering(self):
        a, b = make("date", "2025-01-31"), make("date", "2025-02-01")
        self.assertLess(a.compare_to(b), 0)
        self.assertGreater(b.compare_to(a), 0)
        self.assertEqual(a.compare_to(a), 0)


class DateIntervalTests(unittest.TestCase):
    def test_valid_interval(self):
        v = make("dateInvl", "2025-09-01..2025-12-31")
        self.assertEqual(v.to_text(), "2025-09-01..2025-12-31")
        self.assertEqual(v.length_in_days(), 122)  # межі включно

    def test_single_day_interval(self):
        v = make("dateInvl", "2025-05-05..2025-05-05")
        self.assertEqual(v.length_in_days(), 1)

    def test_start_after_end_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            make("dateInvl", "2025-12-31..2025-01-01")
        self.assertIn("пізніше", str(ctx.exception))

    def test_bad_format_and_bad_dates(self):
        for bad in ["", "2025-01-01", "2025-01-01-2025-02-01", "2025-01-01..", "..2025-01-01",
                    "2025-01-01..2025-02-30", "2025-01-01..2025-02-01..2025-03-01"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    make("dateInvl", bad)

    def test_contains_inclusive(self):
        v = make("dateInvl", "2025-03-01..2025-03-31")
        self.assertTrue(v.contains(DateValue(2025, 3, 1)))
        self.assertTrue(v.contains(DateValue(2025, 3, 31)))
        self.assertFalse(v.contains(DateValue(2025, 4, 1)))
        self.assertFalse(v.contains(DateValue(2025, 2, 28)))

    def test_whitespace_around_parts_is_tolerated(self):
        self.assertEqual(make("dateInvl", " 2025-01-01 .. 2025-01-05 ").to_text(), "2025-01-01..2025-01-05")

    def test_equality_needs_both_bounds(self):
        self.assertEqual(make("dateInvl", "2025-01-01..2025-02-01"), make("dateInvl", "2025-01-01..2025-02-01"))
        self.assertNotEqual(make("dateInvl", "2025-01-01..2025-02-01"), make("dateInvl", "2025-01-01..2025-02-02"))


class ValueContractTests(unittest.TestCase):
    def test_values_of_different_types_are_never_equal(self):
        self.assertNotEqual(IntegerValue(1), RealValue(1.0))
        self.assertNotEqual(make("string", "1"), make("integer", "1"))

    def test_hash_is_consistent_with_equality(self):
        self.assertEqual(hash(make("integer", "5")), hash(make("integer", "+5")))
        self.assertEqual(len({make("string", "a"), make("string", "a"), make("string", "b")}), 2)

    def test_comparing_different_types_is_an_error(self):
        with self.assertRaises(ValidationError):
            IntegerValue(1).compare_to(RealValue(1.0))

    def test_error_message_names_the_field(self):
        with self.assertRaises(ValidationError) as ctx:
            ValueFactory.create(FieldType.INTEGER, "x", "Вік")
        self.assertTrue(str(ctx.exception).startswith("Вік:"))
        self.assertEqual(ctx.exception.field, "Вік")

    def test_unknown_type_name(self):
        with self.assertRaises(ValidationError):
            FieldType.parse("blob")

    def test_all_six_types_present(self):
        self.assertEqual(
            {t.value for t in FieldType},
            {"integer", "real", "char", "string", "date", "dateInvl"},
        )

    def test_interval_requires_date_values(self):
        d1, d2 = DateValue(2025, 1, 1), DateValue(2025, 1, 2)
        self.assertEqual(DateInvlValue(d1, d2).to_text(), "2025-01-01..2025-01-02")


if __name__ == "__main__":
    unittest.main()
