"""Тести 6: smoke-тест GUI. Керує вікнами програмно; пропускається без Tkinter чи дисплея.

Запуск без монітора (Linux):  xvfb-run -a python run_tests.py
"""
import os
import tempfile
import unittest

try:
    import tkinter

    _probe = tkinter.Tk()
    _probe.destroy()
    HAS_TK = True
except Exception:  # немає tkinter або дисплея
    HAS_TK = False

from tabledb.server import DbServer

from helpers import ROWS_A, ROWS_B

if HAS_TK:
    from gui.app import App

FIELDS = [("№", "integer"), ("Назва", "string"), ("Період", "dateInvl")]


@unittest.skipUnless(HAS_TK, "потрібні tkinter і дисплей")
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = App(modal=False)
        self.errors = []
        self.app.show_error = self.errors.append
        self.app.confirm = lambda title, msg: True
        self.app.withdraw()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._destroy)

    def _destroy(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def make_table(self, name, rows):
        self.app.create_table()
        dlg = self.app.last_dialog
        dlg.fill(name, FIELDS)
        dlg.accept()
        for r in rows:
            self.app.backend.add_row(name, r)
        self.app.refresh(select=name)

    def tree_rows(self):
        return [self.app.tree.item(i, "values") for i in self.app.tree.get_children()]

    # ------------------------------------------------------------------
    def test_starts_empty(self):
        self.assertEqual(self.app.table_list.size(), 0)
        self.assertIn("Таблиць немає", self.app.info.cget("text"))

    def test_create_table_through_dialog(self):
        self.make_table("Проєкти", [])
        self.assertFalse(self.app.last_dialog.winfo_exists())  # діалог закрився
        self.assertEqual(self.app.backend.list_tables(), ["Проєкти"])
        self.assertEqual(self.app.table_list.get(0), "Проєкти")
        headings = [self.app.tree.heading(c, "text") for c in self.app.tree["columns"]]
        self.assertEqual(headings, ["#", "№  (integer)", "Назва  (string)", "Період  (dateInvl)"])
        self.assertTrue(self.app.dirty)
        self.assertTrue(self.app.title().endswith("*"))

    def test_invalid_table_keeps_dialog_open_with_message(self):
        self.app.create_table()
        dlg = self.app.last_dialog
        dlg.fill("", FIELDS)
        dlg.accept()
        self.assertTrue(dlg.winfo_exists())
        self.assertIn("порожнім", dlg.error_text)
        dlg.fill("Ок", [("а", "integer"), ("а", "real")])
        dlg.accept()
        self.assertIn("повторюється", dlg.error_text)
        self.assertEqual(self.app.backend.list_tables(), [])
        dlg.destroy()

    def test_add_row_and_validation_error(self):
        self.make_table("Проєкти", [])
        self.app.add_row()
        dlg = self.app.last_dialog
        dlg.fill(["1", "Альфа", "2025-02-30..2025-03-01"])
        dlg.accept()
        self.assertTrue(dlg.winfo_exists())
        self.assertIn("Період", dlg.error_text)
        self.assertEqual(self.tree_rows(), [])
        dlg.fill(["1", "Альфа", "2025-01-01..2025-03-01"])
        dlg.accept()
        self.assertFalse(dlg.winfo_exists())
        self.assertEqual(self.tree_rows(), [("1", "1", "Альфа", "2025-01-01..2025-03-01")])

    def test_edit_row(self):
        self.make_table("Проєкти", [ROWS_A[0], ROWS_A[1]])
        self.app.tree.selection_set("1")
        self.app.edit_row()
        dlg = self.app.last_dialog
        self.assertEqual([v.get() for v in dlg.vars], ROWS_A[1])  # поля заповнені поточними значеннями
        dlg.fill(["2", "Бета (змінена)", "2025-03-15..2025-04-15"])
        dlg.accept()
        self.assertEqual(self.tree_rows()[1][2], "Бета (змінена)")
        self.assertEqual(self.app.tree.selection(), ("1",))

    def test_edit_button_needs_selection(self):
        self.make_table("Проєкти", [ROWS_A[0]])
        self.app.tree.selection_remove(*self.app.tree.selection())
        self.app._update_buttons()
        self.assertIn("disabled", self.app.btn_edit.state())
        self.app.tree.selection_set("0")
        self.app._update_buttons()
        self.assertNotIn("disabled", self.app.btn_edit.state())

    def test_difference_dialog(self):
        self.make_table("A", ROWS_A)
        self.make_table("B", ROWS_B)
        self.app.difference()
        dlg = self.app.last_dialog
        dlg.a_var.set("A")
        dlg.b_var.set("B")
        dlg.r_var.set("R")
        dlg.accept()
        self.assertFalse(dlg.winfo_exists())
        self.assertEqual(self.app.current, "R")
        self.assertEqual([r[1:] for r in self.tree_rows()], [tuple(ROWS_A[0]), tuple(ROWS_A[2])])
        self.assertIn("2 рядків", self.app.status.get())

    def test_difference_errors_stay_in_dialog(self):
        self.make_table("A", ROWS_A)
        self.app.create_table()
        self.app.last_dialog.fill("Інша", [("x", "integer")])
        self.app.last_dialog.accept()
        self.app.difference()
        dlg = self.app.last_dialog
        dlg.a_var.set("A")
        dlg.b_var.set("Інша")
        dlg.r_var.set("R")
        dlg.accept()
        self.assertIn("несумісні", dlg.error_text)
        dlg.b_var.set("A")
        dlg.r_var.set("A")
        dlg.accept()
        self.assertIn("вже існує", dlg.error_text)
        self.assertEqual(self.app.backend.list_tables(), ["A", "Інша"])
        dlg.destroy()

    def test_difference_without_tables_reports_error(self):
        self.app.difference()
        self.assertEqual(len(self.errors), 1)

    def test_default_result_name_follows_choice_until_edited(self):
        self.make_table("A", [])
        self.make_table("B", [])
        self.app.difference()
        dlg = self.app.last_dialog
        dlg.a_var.set("B")
        dlg.b_var.set("A")
        dlg._suggest_name()
        self.assertEqual(dlg.r_var.get(), "B − A")
        dlg.destroy()

    def test_drop_table(self):
        self.make_table("A", ROWS_A)
        self.make_table("B", [])
        self.app.table_list.selection_clear(0, "end")
        self.app.table_list.selection_set(0)
        self.app._on_pick_table()
        self.app.drop_table()
        self.assertEqual(self.app.backend.list_tables(), ["B"])
        self.assertEqual(self.app.current, "B")

    def test_save_and_open_roundtrip(self):
        self.make_table("A", ROWS_A)
        path = os.path.join(self._tmp.name, "gui.tdb")
        self.assertTrue(self.app.save_path(path))
        self.assertFalse(self.app.dirty)
        self.assertFalse(self.app.title().endswith("*"))
        self.app.new_database()
        self.assertEqual(self.app.table_list.size(), 0)
        self.assertTrue(self.app.open_path(path))
        self.assertEqual(self.tree_rows()[0][1:], tuple(ROWS_A[0]))

    def test_open_bad_file_reports_error_and_keeps_data(self):
        self.make_table("A", ROWS_A)
        bad = os.path.join(self._tmp.name, "bad.tdb")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("пошкоджено")
        self.assertFalse(self.app.open_path(bad))
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.app.backend.list_tables(), ["A"])

    def test_unsaved_changes_ask_for_confirmation(self):
        self.make_table("A", [])
        asked = []
        self.app.confirm = lambda t, m: asked.append(t) or False
        self.app.on_close()
        self.assertEqual(asked, ["Незбережені зміни"])
        self.assertTrue(self.app.winfo_exists())  # користувач відмовився
        self.app.confirm = lambda t, m: True
        self.app.on_close()
        with self.assertRaises(tkinter.TclError):  # вікно знищено — Tk більше не відповідає
            self.app.winfo_exists()


@unittest.skipUnless(HAS_TK, "потрібні tkinter і дисплей")
class GuiRemoteTests(unittest.TestCase):
    def test_same_gui_works_through_server(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        server = DbServer(("127.0.0.1", 0), tmp.name)
        server.start_in_thread()
        self.addCleanup(server.stop)
        app = App(modal=False)
        self.addCleanup(app.destroy)
        errors = []
        app.show_error = errors.append
        app.confirm = lambda t, m: True
        app.withdraw()

        self.assertTrue(app.connect(f"http://127.0.0.1:{server.port}"))
        self.assertIn("Сервер", app.mode.get())
        app.create_table()
        app.last_dialog.fill("Віддалена", FIELDS)
        app.last_dialog.accept()
        app.add_row()
        app.last_dialog.fill(ROWS_A[0])
        app.last_dialog.accept()
        self.assertEqual(server.backend.list_tables(), ["Віддалена"])  # дані справді на сервері
        self.assertEqual(server.backend.get_table("Віддалена")["rows"], [ROWS_A[0]])
        self.assertTrue(app.save_path("демо"))
        self.assertIn("демо.tdb", server.list_files())

    def test_connection_failure_is_reported(self):
        app = App(modal=False)
        self.addCleanup(app.destroy)
        errors = []
        app.show_error = errors.append
        app.withdraw()
        self.assertFalse(app.connect("http://127.0.0.1:1"))
        self.assertIn("недоступний", errors[0])
        self.assertFalse(app.backend.is_remote)  # лишились у локальному режимі


if __name__ == "__main__":
    unittest.main()
