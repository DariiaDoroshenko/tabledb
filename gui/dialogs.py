"""Діалоги GUI: створення таблиці, введення/редагування рядка, різниця таблиць.

Кожен діалог отримує функцію submit, яка виконує операцію через Backend.
Якщо submit кидає DbError, діалог лишається відкритим і показує повідомлення
під полями, тому користувач виправляє дані, не вводячи їх заново.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Sequence

from tabledb import DbError, FieldType

TYPE_NAMES = [t.value for t in FieldType]
ERROR_COLOR = "#b00020"
HINT_COLOR = "#6b7280"


class FormDialog(tk.Toplevel):
    """Базовий діалог із кнопками «ОК»/«Скасувати» та рядком помилки."""

    def __init__(self, master: tk.Misc, title: str, ok_text: str = "ОК", modal: bool = True):
        super().__init__(master, highlightthickness=1, highlightbackground="#6b7280")
        self.title(title)
        self.resizable(False, False)
        self._modal = modal
        self._error = tk.StringVar()
        self.body = ttk.Frame(self, padding=(16, 14, 16, 4))
        self.body.pack(fill="both", expand=True)
        self.error_label = ttk.Label(
            self, textvariable=self._error, foreground=ERROR_COLOR, wraplength=440, justify="left"
        )
        self.error_label.pack(fill="x", padx=16)
        buttons = ttk.Frame(self, padding=(16, 8, 16, 14))
        buttons.pack(fill="x")
        self.ok_button = ttk.Button(buttons, text=ok_text, command=self.accept)
        self.ok_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, text="Скасувати", command=self.destroy)
        self.cancel_button.pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _e: self.accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(master)

    # --- для нащадків ------------------------------------------------------
    def on_submit(self) -> None:
        raise NotImplementedError

    def show(self) -> None:
        """Центрує діалог над головним вікном; у модальному режимі блокує його."""
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + max((master.winfo_width() - self.winfo_reqwidth()) // 2, 0)
        y = master.winfo_rooty() + max((master.winfo_height() - self.winfo_reqheight()) // 3, 0)
        self.geometry(f"+{x}+{y}")
        if self._modal:
            self.wait_visibility()
            self.grab_set()
            self.wait_window(self)

    # --- спільне -----------------------------------------------------------
    @property
    def error_text(self) -> str:
        return self._error.get()

    def set_error(self, message: str) -> None:
        self._error.set(message)

    def accept(self) -> None:
        self.set_error("")
        try:
            self.on_submit()
        except DbError as exc:
            self.set_error(str(exc))
            return
        self.destroy()


class CreateTableDialog(FormDialog):
    """Ім'я таблиці та динамічний список полів (ім'я + тип)."""

    def __init__(self, master, submit: Callable[[str, list[dict]], object], modal: bool = True):
        super().__init__(master, "Створити таблицю", "Створити", modal)
        self._submit = submit
        self.name_var = tk.StringVar()
        self.rows: list[tuple[tk.StringVar, tk.StringVar, ttk.Entry, ttk.Combobox, ttk.Button]] = []

        top = ttk.Frame(self.body)
        top.pack(fill="x")
        ttk.Label(top, text="Ім'я таблиці:").pack(side="left")
        self.name_entry = ttk.Entry(top, textvariable=self.name_var, width=34)
        self.name_entry.pack(side="left", padx=(8, 0))

        self.bold = tkfont.nametofont("TkDefaultFont").copy()
        self.bold.configure(weight="bold")
        ttk.Label(self.body, text="Поля таблиці", font=self.bold).pack(anchor="w", pady=(12, 4))
        self.grid_frame = ttk.Frame(self.body)
        self.grid_frame.pack(fill="x")
        ttk.Label(self.grid_frame, text="Ім'я поля", foreground=HINT_COLOR).grid(row=0, column=0, sticky="w")
        ttk.Label(self.grid_frame, text="Тип", foreground=HINT_COLOR).grid(row=0, column=1, sticky="w", padx=8)
        self.add_button = ttk.Button(self.body, text="＋ Додати поле", command=self.add_field_row)
        self.add_button.pack(anchor="w", pady=(8, 0))

        self.add_field_row()
        self.name_entry.focus_set()
        self.show()

    def add_field_row(self, name: str = "", ftype: str = "string") -> None:
        r = len(self.rows) + 1
        name_var, type_var = tk.StringVar(value=name), tk.StringVar(value=ftype)
        entry = ttk.Entry(self.grid_frame, textvariable=name_var, width=24)
        combo = ttk.Combobox(self.grid_frame, textvariable=type_var, values=TYPE_NAMES, state="readonly", width=10)
        remove = ttk.Button(self.grid_frame, text="✕", width=3, command=lambda: self._remove_row(entry))
        entry.grid(row=r, column=0, pady=2, sticky="w")
        combo.grid(row=r, column=1, padx=8, pady=2)
        remove.grid(row=r, column=2, pady=2)
        self.rows.append((name_var, type_var, entry, combo, remove))
        entry.focus_set()

    def _remove_row(self, entry: ttk.Entry) -> None:
        if len(self.rows) == 1:
            self.set_error("Потрібне щонайменше одне поле.")
            return
        for i, row in enumerate(self.rows):
            if row[2] is entry:
                for widget in row[2:]:
                    widget.destroy()
                del self.rows[i]
                break
        for i, (_n, _t, e, c, b) in enumerate(self.rows, start=1):  # перенумеровуємо рядки сітки
            e.grid(row=i, column=0)
            c.grid(row=i, column=1)
            b.grid(row=i, column=2)

    def fill(self, name: str, fields: Sequence[tuple[str, str]]) -> None:
        """Програмне заповнення (для автоматичних тестів і знімків екрана)."""
        self.name_var.set(name)
        while len(self.rows) < len(fields):
            self.add_field_row()
        for (n, t), row in zip(fields, self.rows):
            row[0].set(n)
            row[1].set(t)

    def on_submit(self) -> None:
        fields = [{"name": n.get(), "type": t.get()} for n, t, *_ in self.rows]
        self._submit(self.name_var.get(), fields)


class RowDialog(FormDialog):
    """Одне поле введення на кожне поле таблиці, з підказкою формату за типом."""

    def __init__(self, master, table: dict, submit: Callable[[list[str]], object],
                 values: Sequence[str] | None = None, title: str = "Додати рядок",
                 ok_text: str = "Додати", modal: bool = True):
        super().__init__(master, f"{title} — {table['name']}", ok_text, modal)
        self._submit = submit
        self.vars: list[tk.StringVar] = []
        self.entries: list[ttk.Entry] = []
        for i, field in enumerate(table["fields"]):
            ftype = FieldType.parse(field["type"])
            ttk.Label(self.body, text=f"{field['name']} ({field['type']})").grid(
                row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=values[i] if values else "")
            entry = ttk.Entry(self.body, textvariable=var, width=34)
            entry.grid(row=i, column=1, padx=10, pady=4)
            ttk.Label(self.body, text=ftype.hint, foreground=HINT_COLOR).grid(
                row=i, column=2, sticky="w", pady=4)
            self.vars.append(var)
            self.entries.append(entry)
        self.entries[0].focus_set()
        self.show()

    def fill(self, values: Sequence[str]) -> None:
        for var, text in zip(self.vars, values):
            var.set(text)

    def on_submit(self) -> None:
        self._submit([v.get() for v in self.vars])


class DifferenceDialog(FormDialog):
    """Вибір таблиць A і B та імені результату R = A \\ B."""

    def __init__(self, master, names: Sequence[str], submit: Callable[[str, str, str], object],
                 modal: bool = True):
        super().__init__(master, "Різниця таблиць", "Обчислити", modal)
        self._submit = submit
        self.a_var = tk.StringVar(value=names[0])
        self.b_var = tk.StringVar(value=names[1] if len(names) > 1 else names[0])
        self.r_var = tk.StringVar()
        self._r_edited = False

        ttk.Label(
            self.body,
            text="R = A \\ B — нова таблиця з тих рядків A, яких немає в B.\n"
                 "Схеми A і B мають збігатися за кількістю та типами полів.",
            justify="left", foreground=HINT_COLOR,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for i, (label, var) in enumerate([("Таблиця A:", self.a_var), ("Таблиця B:", self.b_var)], start=1):
            ttk.Label(self.body, text=label).grid(row=i, column=0, sticky="w", pady=4)
            combo = ttk.Combobox(self.body, textvariable=var, values=list(names), state="readonly", width=32)
            combo.grid(row=i, column=1, padx=10, pady=4)
            combo.bind("<<ComboboxSelected>>", lambda _e: self._suggest_name())
        ttk.Label(self.body, text="Ім'я результату R:").grid(row=3, column=0, sticky="w", pady=4)
        self.r_entry = ttk.Entry(self.body, textvariable=self.r_var, width=35)
        self.r_entry.grid(row=3, column=1, padx=10, pady=4)
        self.r_entry.bind("<Key>", lambda _e: setattr(self, "_r_edited", True))
        self._suggest_name()
        self.r_entry.focus_set()
        self.show()

    def _suggest_name(self) -> None:
        if not self._r_edited:
            self.r_var.set(f"{self.a_var.get()} − {self.b_var.get()}")

    def on_submit(self) -> None:
        self._submit(self.a_var.get(), self.b_var.get(), self.r_var.get())
