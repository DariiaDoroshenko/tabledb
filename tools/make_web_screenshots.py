"""Проходить сценарій у браузері (Playwright + Chromium) і знімає скриншоти для звіту етапу 3.

Одночасно це наскрізна перевірка: кожен крок має assert. Потрібно:  pip install playwright
Запуск:  python tools/make_web_screenshots.py screenshots_web
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from tabledb.server import DbServer  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "screenshots_web"
os.makedirs(OUT, exist_ok=True)

PROJECT_FIELDS = [("№", "integer"), ("Назва", "string"), ("Бюджет", "real"),
                  ("Код", "char"), ("Початок", "date"), ("Період", "dateInvl")]
PROJECT_ROWS = [
    ["1", "Система обліку", "125000.5", "A", "2025-01-15", "2025-01-15..2025-06-30"],
    ["2", "Мобільний застосунок", "89990.0", "B", "2025-03-01", "2025-03-01..2025-08-31"],
    ["3", "Портал клієнтів", "240500.75", "A", "2025-05-20", "2025-05-20..2025-12-20"],
]
AB_FIELDS = [("№", "integer"), ("Назва", "string"), ("Період", "dateInvl")]
ROWS_A = [["1", "Проєкт «Альфа»", "2025-01-01..2025-06-30"],
          ["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
          ["3", "Проєкт «Гамма»", "2025-05-01..2025-12-31"]]
ROWS_B = [["2", "Проєкт «Бета»", "2025-03-15..2025-03-20"],
          ["3", "Проєкт «Гамма»", "2025-05-01..2025-11-30"]]


def shot(page, name):
    page.wait_for_timeout(250)
    path = os.path.join(OUT, name)
    page.screenshot(path=path)
    print("знімок:", path)


def create_table(page, name, fields):
    page.click("#btn-create-table")
    page.fill("#create-name", name)
    for i, (fname, ftype) in enumerate(fields):
        if i:
            page.click("#btn-add-field")
        row = page.locator("#create-fields .field-row").nth(i)
        row.locator("input").fill(fname)
        row.locator("select").select_option(ftype)


def submit_create(page):
    page.click("#form-create button[type=submit]")
    expect(page.locator("#dlg-create")).not_to_be_visible()


def add_row(page, values, submit=True):
    page.click("#btn-add-row")
    inputs = page.locator("#row-fields input")
    for i, v in enumerate(values):
        inputs.nth(i).fill(v)
    if submit:
        page.click("#form-row button[type=submit]")


def main():
    tmp = tempfile.mkdtemp()
    server = DbServer(("127.0.0.1", 0), tmp)
    server.start_in_thread()
    url = f"http://127.0.0.1:{server.port}/"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get(
            "CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 760})
        page.on("dialog", lambda d: d.accept())
        page.goto(url)
        expect(page.locator("#no-tables")).to_be_visible()
        shot(page, "w01_empty.png")

        # --- створення таблиці з усіма типами -----------------------------------
        create_table(page, "Проєкти", PROJECT_FIELDS)
        shot(page, "w02_create_dialog.png")
        submit_create(page)
        expect(page.locator("#table-title")).to_have_text("Проєкти")

        # --- рядок із помилкою -------------------------------------------------------
        add_row(page, ["1", "Система обліку", "125000.5", "A", "2025-01-15", "2025-02-30..2025-06-30"])
        expect(page.locator("#row-error")).to_contain_text("Період")
        expect(page.locator("#dlg-row")).to_be_visible()  # діалог лишився відкритим
        shot(page, "w03_row_error.png")
        page.locator("#row-fields input").nth(5).fill(PROJECT_ROWS[0][5])
        page.click("#form-row button[type=submit]")
        expect(page.locator("#dlg-row")).not_to_be_visible()
        for row in PROJECT_ROWS[1:]:
            add_row(page, row)
            expect(page.locator("#dlg-row")).not_to_be_visible()
        expect(page.locator("#grid-body tr")).to_have_count(3)
        shot(page, "w04_table_rows.png")

        # --- редагування ----------------------------------------------------------------
        page.locator("#grid-body tr").nth(1).get_by_text("Редагувати").click()
        page.locator("#row-fields input").nth(1).fill("Мобільний застосунок v2")
        shot(page, "w05_edit_row.png")
        page.click("#form-row button[type=submit]")
        expect(page.locator("#grid-body tr").nth(1)).to_contain_text("Мобільний застосунок v2")

        # --- різниця таблиць ----------------------------------------------------------------
        for name, rows in (("A", ROWS_A), ("B", ROWS_B)):
            create_table(page, name, AB_FIELDS)
            submit_create(page)
            for r in rows:
                add_row(page, r)
                expect(page.locator("#dlg-row")).not_to_be_visible()
        page.locator("#table-list button", has_text="A").first.click()
        page.click("#btn-diff")
        page.select_option("#diff-a", "A")
        page.select_option("#diff-b", "B")
        page.fill("#diff-r", "R")
        shot(page, "w06_diff_dialog.png")
        page.click("#form-diff button[type=submit]")
        expect(page.locator("#table-title")).to_have_text("R")
        rows = [[c.inner_text() for c in tr.locator("td.mono").all()] for tr in page.locator("#grid-body tr").all()]
        assert rows == [ROWS_A[0], ROWS_A[2]], rows
        shot(page, "w07_diff_result.png")

        page.click("#btn-diff")
        page.select_option("#diff-a", "Проєкти")
        page.select_option("#diff-b", "A")
        page.fill("#diff-r", "Помилкова")
        page.click("#form-diff button[type=submit]")
        expect(page.locator("#diff-error")).to_contain_text("несумісні")
        shot(page, "w08_diff_error.png")
        page.click("#dlg-diff [data-close]")

        # --- збереження --------------------------------------------------------------------------
        page.click("#btn-save")
        page.fill("#file-name", "demo")
        shot(page, "w09_save_dialog.png")
        page.click("#form-file button[type=submit]")
        expect(page.locator("#toast")).to_contain_text("demo.tdb")
        assert "demo.tdb" in server.list_files()
        shot(page, "w10_saved.png")

        # --- «друга вкладка» бачить ту саму базу ----------------------------------------------------
        second = browser.new_page(viewport={"width": 1280, "height": 760})
        second.goto(url)
        expect(second.locator("#table-list button")).to_have_count(4)  # Проєкти, A, B, R
        second.close()

        # --- вузький екран -----------------------------------------------------------------------------
        phone = browser.new_page(viewport={"width": 390, "height": 780})
        phone.goto(url)
        phone.locator("#table-list button", has_text="R").click()
        shot(phone, "w11_mobile.png")
        browser.close()
    server.stop()
    print("сценарій пройдено, помилок немає")


if __name__ == "__main__":
    main()
