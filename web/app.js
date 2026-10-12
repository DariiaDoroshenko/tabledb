"use strict";

/* Веб-клієнт табличної бази даних. Усі дані й правила перевірки — на сервері (REST API);
   тут лише показ і введення. Значення завжди передаються рядками. */

const TYPES = ["integer", "real", "char", "string", "date", "dateInvl"];
const HINTS = {
  integer: "ціле число, наприклад 42",
  real: "дійсне число, наприклад 3.14",
  char: "рівно один символ",
  string: "довільний текст",
  date: "РРРР-ММ-ДД, наприклад 2025-03-15",
  dateInvl: "РРРР-ММ-ДД..РРРР-ММ-ДД, наприклад 2025-01-01..2025-06-30",
};

const state = {
  tables: [],      // імена таблиць
  current: null,   // ім'я відкритої таблиці
  table: null,     // її вміст {name, fields, rows}
};

const $ = (id) => document.getElementById(id);

/* ---------- REST-клієнт ---------- */
async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch("/api" + path, options);
  } catch (e) {
    throw new Error("сервер недоступний");
  }
  let data = {};
  try { data = await response.json(); } catch (e) { /* порожня відповідь */ }
  if (!response.ok) throw new Error(data.error || `помилка ${response.status}`);
  return data;
}
const tablePath = (name) => "/tables/" + encodeURIComponent(name);

/* ---------- повідомлення ---------- */
let toastTimer = null;
function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 6000 : 3200);
}

/* ---------- відображення ---------- */
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

async function refreshDatabase() {
  const [db, list] = await Promise.all([api("GET", "/database"), api("GET", "/tables")]);
  $("db-name").textContent = db.name;
  state.tables = list.tables;
  if (state.current && !state.tables.includes(state.current)) state.current = null;
  renderSidebar();
  if (state.current) await showTable(state.current);
  else showEmpty();
}

function renderSidebar() {
  const list = $("table-list");
  clear(list);
  $("no-tables").hidden = state.tables.length > 0;
  for (const name of state.tables) {
    const button = el("button", { type: "button", text: name, title: name,
      onclick: () => showTable(name).catch(fail) });
    if (name === state.current) button.setAttribute("aria-current", "true");
    list.append(el("li", {}, button));
  }
}

function showEmpty() {
  state.current = null;
  state.table = null;
  $("empty-state").hidden = false;
  $("table-view").hidden = true;
  renderSidebar();
}

async function showTable(name) {
  state.table = await api("GET", tablePath(name));
  state.current = name;
  renderSidebar();
  renderTable();
}

function renderTable() {
  const t = state.table;
  $("empty-state").hidden = true;
  $("table-view").hidden = false;
  $("table-title").textContent = t.name;
  $("table-info").textContent = `Полів: ${t.fields.length} · рядків: ${t.rows.length}`;

  const head = $("grid-head");
  clear(head);
  const headRow = el("tr", {}, el("th", { class: "idx", text: "#" }));
  for (const f of t.fields) {
    headRow.append(el("th", {}, f.name, el("span", { class: "ftype", text: f.type })));
  }
  headRow.append(el("th", { class: "act" }));
  head.append(headRow);

  const body = $("grid-body");
  clear(body);
  t.rows.forEach((row, index) => {
    const tr = el("tr", {}, el("td", { class: "idx", text: String(index + 1) }));
    row.forEach((value) => tr.append(el("td", { class: "mono", text: value })));
    tr.append(el("td", { class: "act" },
      el("button", { class: "btn icon", type: "button", text: "Редагувати",
        onclick: () => openRowDialog(index) })));
    body.append(tr);
  });
  $("no-rows").hidden = t.rows.length > 0;
}

function fail(error) { toast(error.message, true); }

/* ---------- діалоги ---------- */
function bindDialog(dialog, onSubmit, errorId) {
  dialog.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $(errorId);
    errorBox.textContent = "";
    try {
      await onSubmit();
      dialog.close();
    } catch (error) {
      errorBox.textContent = error.message;   // діалог лишається відкритим
    }
  });
}

/* Створення таблиці */
function addFieldRow(name = "", type = "string") {
  const row = el("div", { class: "field-row" });
  const nameInput = el("input", { type: "text", placeholder: "ім'я поля", "aria-label": "Ім'я поля",
    autocomplete: "off" });
  nameInput.value = name;
  const select = el("select", { "aria-label": "Тип поля" });
  for (const t of TYPES) select.append(el("option", { value: t, text: t }));
  select.value = type;
  const remove = el("button", { class: "btn small", type: "button", text: "✕", title: "Прибрати поле",
    onclick: () => {
      if ($("create-fields").children.length === 1) {
        $("create-error").textContent = "Потрібне щонайменше одне поле.";
        return;
      }
      row.remove();
    } });
  row.append(nameInput, select, remove);
  $("create-fields").append(row);
  return nameInput;
}

function openCreateDialog() {
  $("create-name").value = "";
  $("create-error").textContent = "";
  clear($("create-fields"));
  addFieldRow();
  $("dlg-create").showModal();
  $("create-name").focus();
}

async function submitCreate() {
  const fields = [...$("create-fields").children].map((row) => ({
    name: row.querySelector("input").value,
    type: row.querySelector("select").value,
  }));
  const table = await api("POST", "/tables", { name: $("create-name").value, fields });
  state.current = table.name;
  await refreshDatabase();
  toast(`Таблицю «${table.name}» створено`);
}

/* Додавання / редагування рядка */
let editingIndex = null;

function openRowDialog(index = null) {
  const t = state.table;
  editingIndex = index;
  $("row-title").textContent = (index === null ? "Додати рядок" : "Редагувати рядок") + " — " + t.name;
  $("row-ok").textContent = index === null ? "Додати" : "Зберегти";
  $("row-error").textContent = "";
  const box = $("row-fields");
  clear(box);
  t.fields.forEach((f, i) => {
    const input = el("input", { type: "text", autocomplete: "off", "data-index": String(i) });
    input.value = index === null ? "" : t.rows[index][i];
    box.append(el("label", { class: "field" }, `${f.name} (${f.type})`, input,
      el("span", { class: "hint", text: HINTS[f.type] })));
  });
  $("dlg-row").showModal();
  box.querySelector("input").focus();
}

async function submitRow() {
  const values = [...$("row-fields").querySelectorAll("input")].map((i) => i.value);
  const path = tablePath(state.table.name);
  if (editingIndex === null) await api("POST", path + "/rows", { values });
  else await api("PUT", `${path}/rows/${editingIndex}`, { values });
  await showTable(state.table.name);
  toast(editingIndex === null ? "Рядок додано" : "Рядок змінено");
}

/* Різниця таблиць */
let diffNameEdited = false;

function suggestDiffName() {
  if (!diffNameEdited) $("diff-r").value = `${$("diff-a").value} − ${$("diff-b").value}`;
}

function openDiffDialog() {
  if (state.tables.length === 0) { toast("Спершу створіть таблицю", true); return; }
  for (const id of ["diff-a", "diff-b"]) {
    const select = $(id);
    clear(select);
    for (const name of state.tables) select.append(el("option", { value: name, text: name }));
  }
  $("diff-a").value = state.current || state.tables[0];
  $("diff-b").value = state.tables[1] || state.tables[0];
  diffNameEdited = false;
  suggestDiffName();
  $("diff-error").textContent = "";
  $("dlg-diff").showModal();
}

async function submitDiff() {
  const result = await api("POST", "/difference",
    { a: $("diff-a").value, b: $("diff-b").value, result: $("diff-r").value });
  state.current = result.name;
  await refreshDatabase();
  toast(`Результат «${result.name}»: ${result.rows.length} рядків`);
}

/* Збереження / відкриття файлу на сервері */
let fileMode = "save";

async function openFileDialog(mode) {
  fileMode = mode;
  const isSave = mode === "save";
  $("file-title").textContent = isSave ? "Зберегти базу" : "Відкрити базу";
  $("file-ok").textContent = isSave ? "Зберегти" : "Відкрити";
  $("file-hint").textContent = isSave
    ? "Файл буде записано в теці даних сервера (розширення .tdb додається автоматично)."
    : "Поточна база на сервері буде замінена вмістом файлу.";
  $("file-error").textContent = "";
  $("file-name").value = isSave ? $("db-name").textContent : "";
  const list = $("file-list");
  clear(list);
  try {
    const { files } = await api("GET", "/database/files");
    for (const f of files) list.append(el("option", { value: f }));
    if (!isSave && files.length) $("file-name").value = files[0];
  } catch (error) { fail(error); }
  $("dlg-file").showModal();
  $("file-name").select();
}

async function submitFile() {
  const name = $("file-name").value;
  const result = await api("POST", fileMode === "save" ? "/database/save" : "/database/load", { name });
  if (fileMode === "load") { state.current = null; await refreshDatabase(); }
  toast(fileMode === "save" ? `Збережено у файл ${result.file}` : `Відкрито файл ${result.file}`);
}

/* ---------- підключення подій ---------- */
$("btn-create-table").addEventListener("click", openCreateDialog);
$("btn-add-field").addEventListener("click", () => addFieldRow().focus());
$("btn-add-row").addEventListener("click", () => openRowDialog(null));
$("btn-diff").addEventListener("click", openDiffDialog);
$("btn-open").addEventListener("click", () => openFileDialog("load"));
$("btn-save").addEventListener("click", () => openFileDialog("save"));
$("diff-a").addEventListener("change", suggestDiffName);
$("diff-b").addEventListener("change", suggestDiffName);
$("diff-r").addEventListener("input", () => { diffNameEdited = true; });

$("btn-new-db").addEventListener("click", async () => {
  if (!confirm("Створити нову порожню базу? Незбережені дані на сервері буде втрачено.")) return;
  try {
    await api("POST", "/database/new", { name: "Нова база" });
    state.current = null;
    await refreshDatabase();
    toast("Створено нову базу");
  } catch (error) { fail(error); }
});

$("btn-drop").addEventListener("click", async () => {
  if (!state.current) return;
  if (!confirm(`Видалити таблицю «${state.current}»?`)) return;
  try {
    await api("DELETE", tablePath(state.current));
    const name = state.current;
    state.current = null;
    await refreshDatabase();
    toast(`Таблицю «${name}» видалено`);
  } catch (error) { fail(error); }
});

bindDialog($("dlg-create"), submitCreate, "create-error");
bindDialog($("dlg-row"), submitRow, "row-error");
bindDialog($("dlg-diff"), submitDiff, "diff-error");
bindDialog($("dlg-file"), submitFile, "file-error");

refreshDatabase().catch(fail);
