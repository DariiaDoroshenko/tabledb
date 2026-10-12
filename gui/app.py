"""Головне вікно десктоп-клієнта.

Вікно працює лише з інтерфейсом Backend: локальна база в пам'яті
(LocalBackend) або віддалений сервер (RemoteBackend). Перемикається в меню
«З'єднання» без зміни решти коду.
"""
from __future__ import annotations

import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from tabledb import Backend, DbError, LocalBackend
from tabledb.client import RemoteBackend

from .dialogs import CreateTableDialog, DifferenceDialog, RowDialog

DEFAULT_SERVER = "http://127.0.0.1:8765"
COLUMN_WIDTH = {"integer": 80, "real": 90, "char": 60, "string": 200, "date": 100, "dateInvl": 190}
FILE_TYPES = [("Табличні бази даних", "*.tdb"), ("Усі файли", "*.*")]


class App(tk.Tk):
    def __init__(self, backend: Backend | None = None, modal: bool = True):
        super().__init__()
        self.backend: Backend = backend or LocalBackend()
        self.modal = modal                # False: діалоги не блокують (знімки екрана, тести)
        self.path: str | None = None      # файл (локально) або ім'я файлу на сервері
        self.dirty = False                # є незбережені зміни
        self.current: str | None = None   # ім'я вибраної таблиці
        self.current_table: dict | None = None
        self.last_dialog = None
        # Обробники можна підмінити (автоматичні тести не мають блокуватися вікнами).
        self.show_error = lambda msg: messagebox.showerror("Помилка", msg, parent=self)
        self.confirm = lambda title, msg: messagebox.askyesno(title, msg, parent=self)

        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self.geometry("1180x600")
        self.minsize(760, 420)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        for seq, fn in (("<Control-n>", self.new_database), ("<Control-o>", self.open_database),
                        ("<Control-s>", self.save_database)):
            self.bind(seq, lambda _e, f=fn: f())
        self.refresh()

    # ------------------------------------------------------------------ вигляд
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        if sys.platform.startswith("linux") and "clam" in style.theme_names():
            style.theme_use("clam")
        forced = os.environ.get("TABLEDB_FONT")  # для систем без підходящих шрифтів
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkFixedFont"):
            named = tkfont.nametofont(name)
            named.configure(size=10)
            if forced:
                named.configure(family=forced)
        base = tkfont.nametofont("TkDefaultFont")
        style.configure("Treeview", rowheight=26, font=base)
        style.configure("Treeview.Heading", font=(base.actual("family"), 10, "bold"))
        style.configure("Status.TLabel", padding=(8, 3))

    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label="Нова база", accelerator="Ctrl+N", command=self.new_database)
        file_menu.add_command(label="Відкрити…", accelerator="Ctrl+O", command=self.open_database)
        file_menu.add_command(label="Зберегти", accelerator="Ctrl+S", command=self.save_database)
        file_menu.add_command(label="Зберегти як…", command=self.save_database_as)
        file_menu.add_separator()
        file_menu.add_command(label="Вийти", command=self.on_close)
        table_menu = tk.Menu(bar, tearoff=False)
        table_menu.add_command(label="Створити таблицю…", command=self.create_table)
        table_menu.add_command(label="Знищити таблицю", command=self.drop_table)
        table_menu.add_separator()
        table_menu.add_command(label="Різниця таблиць…", command=self.difference)
        row_menu = tk.Menu(bar, tearoff=False)
        row_menu.add_command(label="Додати рядок…", command=self.add_row)
        row_menu.add_command(label="Редагувати рядок…", command=self.edit_row)
        conn_menu = tk.Menu(bar, tearoff=False)
        conn_menu.add_command(label="Підключитися до сервера…", command=self.connect_server)
        conn_menu.add_command(label="Працювати локально", command=self.use_local)
        bar.add_cascade(label="Файл", menu=file_menu)
        bar.add_cascade(label="Таблиця", menu=table_menu)
        bar.add_cascade(label="Рядок", menu=row_menu)
        bar.add_cascade(label="З'єднання", menu=conn_menu)
        self.config(menu=bar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        spec = [
            ("Створити таблицю", self.create_table, "btn_create"),
            ("Знищити таблицю", self.drop_table, "btn_drop"),
            None,
            ("Додати рядок", self.add_row, "btn_add"),
            ("Редагувати рядок", self.edit_row, "btn_edit"),
            None,
            ("Різниця таблиць…", self.difference, "btn_diff"),
        ]
        for item in spec:
            if item is None:
                ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
                continue
            text, command, attr = item
            button = ttk.Button(bar, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            setattr(self, attr, button)
        ttk.Separator(self).pack(fill="x")

    def _build_body(self) -> None:
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Labelframe(panes, text="Таблиці бази", padding=6)
        self.table_list = tk.Listbox(left, exportselection=False, activestyle="none",
                                     font=tkfont.nametofont("TkDefaultFont"), width=22,
                                     borderwidth=0, highlightthickness=0,
                                     selectbackground="#2f6fed", selectforeground="white")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.table_list.yview)
        self.table_list.configure(yscrollcommand=sb.set)
        self.table_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.table_list.bind("<<ListboxSelect>>", self._on_pick_table)
        panes.add(left, weight=0)

        right = ttk.Labelframe(panes, text="Рядки таблиці", padding=6)
        self.info = ttk.Label(right, text="", foreground="#4b5563")
        self.info.pack(anchor="w", pady=(0, 6))
        holder = ttk.Frame(right)
        holder.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(holder, show="headings", selectmode="browse")
        ys = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.tree.tag_configure("odd", background="#f3f6fc")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        self.tree.bind("<Double-1>", lambda _e: self.edit_row())
        panes.add(right, weight=1)

    def _build_status(self) -> None:
        ttk.Separator(self).pack(fill="x")
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.status = tk.StringVar(value="Готово")
        self.mode = tk.StringVar()
        ttk.Label(bar, textvariable=self.status, style="Status.TLabel").pack(side="left")
        ttk.Label(bar, textvariable=self.mode, style="Status.TLabel", foreground="#4b5563").pack(side="right")

    # ------------------------------------------------------------------ допоміжне
    def set_status(self, message: str) -> None:
        self.status.set(message)

    def _guard(self, func, *args):
        """Виконує дію, показуючи DbError у вікні повідомлення. Повертає (успіх, результат)."""
        try:
            return True, func(*args)
        except DbError as exc:
            self.show_error(str(exc))
            return False, None

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = self.path or self._safe(self.backend.database_name, "—")
        self.title(f"Табличні бази даних — {name}{' *' if self.dirty else ''}")
        self.mode.set(f"Режим: {self.backend.description}")

    @staticmethod
    def _safe(func, default):
        try:
            return func()
        except DbError:
            return default

    def _confirm_discard(self) -> bool:
        return (not self.dirty) or self.confirm(
            "Незбережені зміни", "У базі є незбережені зміни. Відкинути їх?")

    def _selected_row_index(self) -> int | None:
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _update_buttons(self) -> None:
        has_table = self.current is not None
        has_row = has_table and self._selected_row_index() is not None
        self.btn_drop.state(["!disabled"] if has_table else ["disabled"])
        self.btn_add.state(["!disabled"] if has_table else ["disabled"])
        self.btn_edit.state(["!disabled"] if has_row else ["disabled"])
        self.btn_diff.state(["!disabled"] if has_table else ["disabled"])

    # ------------------------------------------------------------------ відображення даних
    def refresh(self, select: str | None = None, select_row: int | None = None) -> None:
        """Перечитує перелік таблиць і вміст вибраної таблиці з бекенду."""
        ok, names = self._guard(self.backend.list_tables)
        if not ok:
            names = []
        self.table_list.delete(0, "end")
        for n in names:
            self.table_list.insert("end", n)
        target = select if select in names else (self.current if self.current in names else None)
        if target is None and names:
            target = names[0]
        self.current = target
        if target is not None:
            index = names.index(target)
            self.table_list.selection_set(index)
            self.table_list.see(index)
            self._show_table(target, select_row)
        else:
            self.current_table = None
            self._clear_tree()
            self.info.config(text="Таблиць немає. Створіть першу: «Створити таблицю».")
        self._update_buttons()
        self._update_title()

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ()

    def _show_table(self, name: str, select_row: int | None = None) -> None:
        ok, data = self._guard(self.backend.get_table, name)
        if not ok:
            return
        self.current_table = data
        self._clear_tree()
        columns = ["#"] + [f"c{i}" for i in range(len(data["fields"]))]
        self.tree["columns"] = columns
        self.tree.heading("#", text="#")
        self.tree.column("#", width=48, minwidth=40, anchor="e", stretch=False)
        head_font = tkfont.nametofont("TkHeadingFont")
        for i, f in enumerate(data["fields"]):
            col = f"c{i}"
            title = f"{f['name']}  ({f['type']})"
            width = max(COLUMN_WIDTH.get(f["type"], 140), head_font.measure(title) + 24)
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=60, anchor="w", stretch=False)
        for i, row in enumerate(data["rows"]):
            self.tree.insert("", "end", iid=str(i), values=[i + 1] + row,
                             tags=("odd",) if i % 2 else ())
        self.info.config(
            text=f"Таблиця «{data['name']}»: {len(data['fields'])} полів, {len(data['rows'])} рядків")
        if select_row is not None and 0 <= select_row < len(data["rows"]):
            self.tree.selection_set(str(select_row))
            self.tree.see(str(select_row))

    def _on_pick_table(self, _event=None) -> None:
        picked = self.table_list.curselection()
        if picked:
            self.current = self.table_list.get(picked[0])
            self._show_table(self.current)
            self._update_buttons()

    # ------------------------------------------------------------------ база даних
    def new_database(self) -> None:
        if not self._confirm_discard():
            return
        ok, _ = self._guard(self.backend.new_database)
        if ok:
            self.path, self.dirty, self.current = None, False, None
            self.refresh()
            self.set_status("Створено нову порожню базу")

    def open_database(self) -> None:
        if not self._confirm_discard():
            return
        if self.backend.is_remote:
            ok, files = self._guard(self.backend.list_files)
            if not ok:
                return
            listing = "\n".join(files) if files else "(файлів ще немає)"
            path = simpledialog.askstring(
                "Відкрити базу на сервері", f"Файли на сервері:\n{listing}\n\nІм'я файлу:", parent=self)
        else:
            path = filedialog.askopenfilename(parent=self, title="Відкрити базу", filetypes=FILE_TYPES)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        ok, _ = self._guard(self.backend.load, path)
        if ok:
            self.path, self.dirty, self.current = path, False, None
            self.refresh()
            self.set_status(f"Базу відкрито: {path}")
        return ok

    def save_database(self) -> None:
        if self.path is None:
            self.save_database_as()
        else:
            self.save_path(self.path)

    def save_database_as(self) -> None:
        if self.backend.is_remote:
            path = simpledialog.askstring(
                "Зберегти на сервері", "Ім'я файлу (на сервері):", parent=self,
                initialvalue=self.path or self._safe(self.backend.database_name, ""))
        else:
            path = filedialog.asksaveasfilename(
                parent=self, title="Зберегти базу", defaultextension=".tdb", filetypes=FILE_TYPES)
        if path:
            self.save_path(path)

    def save_path(self, path: str) -> bool:
        ok, _ = self._guard(self.backend.save, path)
        if ok:
            self.path, self.dirty = path, False
            self._update_title()
            self.set_status(f"Базу збережено: {path}")
        return ok

    # ------------------------------------------------------------------ таблиці
    def create_table(self) -> None:
        self.last_dialog = CreateTableDialog(self, self._do_create_table, modal=self.modal)

    def _do_create_table(self, name: str, fields: list[dict]) -> None:
        created = self.backend.create_table(name, fields)
        self._mark_dirty()
        self.refresh(select=created["name"])
        self.set_status(f"Створено таблицю «{created['name']}»")

    def drop_table(self) -> None:
        if self.current is None:
            return
        name = self.current
        if not self.confirm("Знищити таблицю", f"Знищити таблицю «{name}» разом з усіма рядками?"):
            return
        ok, _ = self._guard(self.backend.drop_table, name)
        if ok:
            self.current = None
            self._mark_dirty()
            self.refresh()
            self.set_status(f"Таблицю «{name}» знищено")

    def difference(self) -> None:
        ok, names = self._guard(self.backend.list_tables)
        if not ok:
            return
        if not names:
            self.show_error("У базі немає таблиць. Спочатку створіть таблицю.")
            return
        self.last_dialog = DifferenceDialog(self, names, self._do_difference, modal=self.modal)

    def _do_difference(self, a: str, b: str, result: str) -> None:
        created = self.backend.difference(a, b, result)
        self._mark_dirty()
        self.refresh(select=created["name"])
        self.set_status(
            f"Різниця «{a}» − «{b}»: створено таблицю «{created['name']}», {len(created['rows'])} рядків")

    # ------------------------------------------------------------------ рядки
    def add_row(self) -> None:
        if self.current_table is None:
            return
        self.last_dialog = RowDialog(self, self.current_table, self._do_add_row, modal=self.modal)

    def _do_add_row(self, values: list[str]) -> None:
        name = self.current
        index = self.backend.add_row(name, values)
        self._mark_dirty()
        self.refresh(select=name, select_row=index)
        self.set_status(f"Додано рядок {index + 1}")

    def edit_row(self) -> None:
        index = self._selected_row_index()
        if self.current_table is None or index is None:
            return
        row = self.current_table["rows"][index]
        self.last_dialog = RowDialog(
            self, self.current_table, lambda v, i=index: self._do_edit_row(i, v), values=row,
            title=f"Редагувати рядок {index + 1}", ok_text="Зберегти", modal=self.modal)

    def _do_edit_row(self, index: int, values: list[str]) -> None:
        name = self.current
        self.backend.update_row(name, index, values)
        self._mark_dirty()
        self.refresh(select=name, select_row=index)
        self.set_status(f"Рядок {index + 1} змінено")

    # ------------------------------------------------------------------ з'єднання
    def connect_server(self) -> None:
        url = simpledialog.askstring(
            "Підключитися до сервера", "Адреса сервера:", parent=self, initialvalue=DEFAULT_SERVER)
        if url:
            self.connect(url)

    def connect(self, url: str) -> bool:
        remote = RemoteBackend(url)
        ok, db_name = self._guard(remote.ping)
        if not ok or not self._confirm_discard():
            return False
        self.backend, self.path, self.dirty, self.current = remote, None, False, None
        self.refresh()
        self.set_status(f"Підключено до {remote.base_url}; база на сервері: «{db_name}»")
        return True

    def use_local(self) -> None:
        if not self._confirm_discard():
            return
        self.backend, self.path, self.dirty, self.current = LocalBackend(), None, False, None
        self.refresh()
        self.set_status("Локальний режим: нова порожня база")

    def on_close(self) -> None:
        if self._confirm_discard():
            self.destroy()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Десктоп-клієнт табличної бази даних")
    parser.add_argument("--server", metavar="URL", help=f"одразу підключитися до сервера, напр. {DEFAULT_SERVER}")
    parser.add_argument("--open", metavar="ФАЙЛ", help="відкрити файл бази (.tdb) у локальному режимі")
    args = parser.parse_args(argv)
    app = App()
    if args.server:
        app.connect(args.server)
    elif args.open:
        app.open_path(args.open)
    app.mainloop()
