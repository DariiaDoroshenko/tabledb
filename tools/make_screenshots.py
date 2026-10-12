"""Автоматично проходить типовий сценарій у GUI та знімає скріншоти для звіту.

Запуск (Linux, потрібні xvfb і ImageMagick):
    xvfb-run -a -s "-screen 0 1280x800x24" python tools/make_screenshots.py screenshots
"""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Tk без Xft бачить лише X-шрифти: DejaVu підключається через -fp (див. tools/README_screenshots.txt).
os.environ.setdefault("TABLEDB_FONT", "DejaVu Sans")

from gui.app import App  # noqa: E402
from tabledb.server import DbServer  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "screenshots"
os.makedirs(OUT, exist_ok=True)

PROJECT_FIELDS = [("№", "integer"), ("Назва", "string"), ("Бюджет", "real"),
                  ("Код", "char"), ("Початок", "date"), ("Період", "dateInvl")]
PROJECT_ROWS = [
    ["1", "Система обліку", "125000.5", "A", "2025-01-15", "2025-01-15..2025-06-30"],
    ["2", "Мобільний застосунок", "89990.0", "B", "2025-03-01", "2025-03-01..2025-08-31"],
    ["3", "Портал клієнтів", "240500.75", "A", "2025-05-20", "2025-05-20..2025-12-20"],
    ["4", "Міграція даних", "15000.0", "C", "2024-11-10", "2024-11-10..2025-02-28"],
]
AB_FIELDS = [("№", "integer"), ("Назва", "string"), ("Період", "dateInvl")]
ROWS_A = [["1", "Проєкт «Альфа»", "2025-01-01..2025-06-30"],
          ["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
          ["3", "Проєкт «Гамма»", "2025-05-01..2025-12-31"]]
ROWS_B = [["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
          ["3", "Проєкт «Гамма»", "2025-05-01..2025-11-30"]]


def fields(pairs):
    return [{"name": n, "type": t} for n, t in pairs]


def settle(*windows):
    for w in windows:
        w.update_idletasks()
    for w in windows:
        w.update()
    time.sleep(0.35)
    for w in windows:
        w.update()


def shot(name, *windows):
    """Знімає прямокутник, що охоплює всі вказані вікна (головне + діалог)."""
    settle(*windows)
    boxes = [(w.winfo_rootx(), w.winfo_rooty(), w.winfo_rootx() + w.winfo_width(),
              w.winfo_rooty() + w.winfo_height()) for w in windows]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    path = os.path.join(OUT, name)
    raw = path + ".raw.png"
    subprocess.run(["import", "-window", "root", raw], check=True)
    subprocess.run(
        ["convert", raw, "-crop", f"{x1 - x0}x{y1 - y0}+{x0}+{y0}", "+repage", "-bordercolor",
         "#9aa0a6", "-border", "1", path], check=True)
    os.remove(raw)
    print("знімок:", path)


def new_app(x=15, y=20):
    app = App(modal=False)
    app.confirm = lambda *_: True
    app.show_error = lambda msg: print("ПОМИЛКА:", msg)
    app.geometry(f"1250x600+{x}+{y}")
    return app


def main():
    tmp = tempfile.mkdtemp()
    app = new_app()
    settle(app)
    shot("01_main_empty.png", app)

    # --- створення таблиці з усіма типами -----------------------------------
    app.create_table()
    dlg = app.last_dialog
    dlg.fill("Проєкти", PROJECT_FIELDS)
    dlg.show()  # діалог виріс після додавання полів: центруємо знову
    shot("02_create_table_dialog.png", app, dlg)
    dlg.accept()

    # --- додавання рядка з помилкою валідації ---------------------------------
    app.add_row()
    dlg = app.last_dialog
    dlg.fill(["1", "Система обліку", "125000.5", "A", "2025-01-15", "2025-02-30..2025-06-30"])
    dlg.accept()  # помилка: 30 лютого
    shot("03_add_row_error.png", app, dlg)
    dlg.fill(PROJECT_ROWS[0])
    dlg.accept()
    for row in PROJECT_ROWS[1:]:
        app.backend.add_row("Проєкти", row)
    app.refresh(select="Проєкти", select_row=1)
    shot("04_table_with_rows.png", app)

    # --- редагування рядка -----------------------------------------------------
    app.edit_row()
    dlg = app.last_dialog
    dlg.vars[1].set("Мобільний застосунок v2")
    shot("05_edit_row.png", app, dlg)
    dlg.accept()

    # --- різниця таблиць ---------------------------------------------------------
    for name, rows in (("A", ROWS_A), ("B", ROWS_B)):
        app.backend.create_table(name, fields(AB_FIELDS))
        for r in rows:
            app.backend.add_row(name, r)
    app.refresh(select="A")
    app.difference()
    dlg = app.last_dialog
    dlg.a_var.set("A")
    dlg.b_var.set("B")
    dlg.r_var.set("R")
    shot("06_difference_dialog.png", app, dlg)
    dlg.accept()
    shot("07_difference_result.png", app)

    app.difference()  # несумісні схеми
    dlg = app.last_dialog
    dlg.a_var.set("Проєкти")
    dlg.b_var.set("A")
    dlg.r_var.set("Помилкова")
    dlg.accept()
    shot("08_difference_error.png", app, dlg)
    dlg.destroy()

    # --- збереження ---------------------------------------------------------------
    app.save_path(os.path.join(tmp, "demo.tdb"))
    app.refresh(select="Проєкти")
    shot("09_saved.png", app)
    app.destroy()

    # --- те саме вікно, але з віддаленим сервером -----------------------------------
    server = DbServer(("127.0.0.1", 0), tmp)
    server.start_in_thread()
    remote = new_app()
    remote.connect(f"http://127.0.0.1:{server.port}")
    for name, rows in (("A", ROWS_A), ("B", ROWS_B)):
        remote.backend.create_table(name, fields(AB_FIELDS))
        for r in rows:
            remote.backend.add_row(name, r)
    remote.backend.difference("A", "B", "R")
    remote.refresh(select="R")
    remote._mark_dirty()
    remote.set_status(f"Підключено до {remote.backend.base_url}; усі дані зберігаються на сервері")
    shot("10_remote_mode.png", remote)
    remote.destroy()
    server.stop()


if __name__ == "__main__":
    main()
