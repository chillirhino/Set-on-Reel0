"use strict";

const TYPES = ["low", "middle", "high", "special", "wild", "hidden"];
const MAX_ID = 999;

const $ = (id) => document.getElementById(id);

const grid = $("grid");
const linesBox = $("lines");
const counter = $("counter");
const linesCounter = $("lines-counter");
const messages = $("messages");
const setSelect = $("set-select");
const setPath = $("set-path");
const betInput = $("bet");
const rowsInput = $("rows");
const reelsInput = $("reels");
const pasteModal = $("paste-modal");
const pasteText = $("paste-text");
const reelPick = $("reel-pick");
const stackRows = $("stack-rows");
const stripsBox = $("strips");
const genStats = $("gen-stats");
const hiddenCards = $("hidden-cards");
const hiddenCounter = $("hidden-counter");
const hiddenRoll = $("hidden-roll");
const lengthsBox = $("lengths");
const gapRows = $("gap-rows");
const gapsCounter = $("gaps-counter");
const textOut = $("text-out");
const stripsText = $("strips-text");
const stripsFile = $("strips-file");
const slotBox = $("slot");
const winList = $("win-list");
const comp = $("comp");
const spinResult = $("spin-result");
const roundsInput = $("rounds");
const rtpBox = $("rtp");
const dists = $("dists");
const hitsBox = $("hits");
const valuesBox = $("values");
const hitsChart = $("hits-chart");
const bonusSymbol = $("bonus-symbol");
const bonusMin = $("bonus-min");
const fsSymbol = $("fs-symbol");
const fsMin = $("fs-min");
const antFields = {
  bonus: { min: $("bonus-ant-min"), each: $("bonus-ant-each"), reels: $("bonus-ant-reels") },
  fs: { min: $("fs-ant-min"), each: $("fs-ant-each"), reels: $("fs-ant-reels") },
};

let state = {
  sets: [],
  active: "",
  bet: 20,
  symbols: [],
  field: { rows: 4, reels: 5, paylines: [] },
  gaps: [],
  reels: [],
  seeds: [],
  strips: [],
  stats: [],
};

let currentReel = 0; // какой рил правим на вкладке «Ленты»

// --- обмен с сервером --------------------------------------------------------

async function api(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || response.statusText);
  return data;
}

// --- папка картриджа на диске -----------------------------------------------
//
// Браузер умеет открывать папку с диска (File System Access API) и читать-писать
// в ней файлы. Формат папки — тот же, что у сета на сервере: set.json рядом с
// images/, поэтому нынешние sets/<имя>/ открываются как есть.
//
// Сервер при этом остаётся оболочкой: он считает и симулирует, а durable-копия
// лежит у пользователя. Переписывать хранилище не пришлось — нужные операции
// уже были: /api/sets/export отдаёт сет одним объектом с картинками в base64,
// /api/sets/import разворачивает такой объект обратно.
//
// Работает в Chrome и Edge; в Safari и Firefox showDirectoryPicker нет, поэтому
// кнопки просто не показываются и остаётся «Экспорт/Импорт файлом».

let folderHandle = null;
const FOLDER_SUPPORTED = typeof window.showDirectoryPicker === "function";

function renderFolder() {
  const open = $("btn-folder-open");
  const save = $("btn-folder-save");
  if (!open || !save) return;
  open.classList.toggle("hidden", !FOLDER_SUPPORTED);
  save.classList.toggle("hidden", !FOLDER_SUPPORTED || !folderHandle);
  if (folderHandle) {
    open.textContent = `Папка: ${folderHandle.name}`;
    save.textContent = `Сохранить в «${folderHandle.name}»`;
  } else {
    open.textContent = "Открыть папку";
  }
}

async function readFolderBundle(handle) {
  const doc = await handle.getFileHandle("set.json").then((h) => h.getFile());
  const bundle = {
    format: "reelgen-set",
    version: 1,
    name: handle.name,
    set: JSON.parse(await doc.text()),
    images: {},
  };

  // Картинки лежат в images/ и едут в base64 — ровно как в файле выгрузки.
  // Отсутствие папки допустимо, а сбой чтения отдельного файла — нет, поэтому
  // ловим только первое: широкий catch однажды уже съел настоящую ошибку.
  let images = null;
  try {
    images = await handle.getDirectoryHandle("images");
  } catch {
    return bundle; // сет без картинок
  }

  for await (const [name, entry] of images.entries()) {
    if (entry.kind !== "file") continue;
    const buffer = await (await entry.getFile()).arrayBuffer();
    let binary = "";
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    bundle.images[name] = btoa(binary);
  }
  return bundle;
}

async function writeFile(dir, name, contents) {
  const handle = await dir.getFileHandle(name, { create: true });
  const stream = await handle.createWritable();
  await stream.write(contents);
  await stream.close();
}

$("btn-folder-open").onclick = async () => {
  try {
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    const bundle = await readFolderBundle(handle);
    state = await api("/api/sets/import", { bundle, name: handle.name });
    folderHandle = handle;
    render();
    say(`картридж «${handle.name}» открыт с диска`, true);
  } catch (error) {
    if (error?.name === "AbortError") return; // просто закрыл диалог
    say(
      error?.name === "NotFoundError"
        ? "в папке нет set.json — выбери папку картриджа, а не её родителя"
        : error.message
    );
  }
};

$("btn-folder-save").onclick = async () => {
  if (!folderHandle) return;
  try {
    const dump = await api("/api/sets/export", { name: state.active });
    const bundle = dump.bundle;
    await writeFile(
      folderHandle,
      "set.json",
      JSON.stringify(bundle.set, null, 2)
    );

    const names = Object.keys(bundle.images || {});
    if (names.length) {
      const images = await folderHandle.getDirectoryHandle("images", { create: true });
      for (const name of names) {
        const binary = atob(bundle.images[name]);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        await writeFile(images, name, bytes);
      }
    }
    // ленты плоским текстом — тем же файлом, что пишет сервер локально
    await writeFile(folderHandle, "strips.txt", state.strips.map((s) => s.join(" ")).join("\n") + "\n");
    say(`записано в «${folderHandle.name}»: set.json, ${names.length} картинок, strips.txt`, true);
  } catch (error) {
    say(`не удалось записать: ${error.message}`);
  }
};

// На хостинге хранилище живёт до следующего деплоя, и об этом надо сказать
// заранее, а не после потери работы. Локально баннера нет.
async function checkEnv() {
  try {
    const env = await api("/api/env", {});
    if (!env.public) return;
    const banner = $("banner");
    banner.classList.remove("hidden");
    banner.innerHTML =
      "<b>Онлайн-версия: правки живут до следующего деплоя.</b> " +
      "Картриджи в списке «сет» приезжают из репозитория. " +
      "Закончил — нажми <b>«Экспорт файлом»</b> и сохрани к себе; " +
      "в следующий раз загрузишь его кнопкой <b>«Импорт файла»</b>. " +
      "Хранилище общее: правки видны всем, у кого есть ссылка.";
  } catch {
    // старый сервер без /api/env — значит локальный запуск, баннер не нужен
  }
}

async function call(path, payload) {
  try {
    state = await api(path, payload);
    render();
  } catch (error) {
    say(error.message);
  }
}

function say(text, ok = false) {
  const box = document.createElement("div");
  box.className = ok ? "msg ok" : "msg";
  box.textContent = text;
  messages.appendChild(box);
  setTimeout(() => box.remove(), ok ? 2500 : 6000);
}

// --- отрисовка ---------------------------------------------------------------

function render() {
  renderSets();
  renderSymbols();
  renderHidden();
  renderField();
  renderGaps();
  renderReels();
  renderPattern();
  renderStats();
}

function renderSets() {
  renderFolder();
  setSelect.textContent = "";
  state.sets.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    option.selected = name === state.active;
    setSelect.appendChild(option);
  });
  setPath.textContent = `sets/${state.active}/`;
  $("btn-set-restore").classList.toggle("hidden", !(state.trash || []).length);
}

function renderSymbols() {
  if (document.activeElement !== betInput) betInput.value = state.bet;
  grid.textContent = "";
  state.symbols.forEach((symbol) => grid.appendChild(card(symbol)));
  grid.appendChild(addCard());
  counter.textContent = `символов: ${state.symbols.length}`;
}

function card(symbol) {
  const node = document.createElement("div");
  node.className = "card";

  const head = document.createElement("div");
  head.className = "card-head";
  head.append(idField(symbol));
  const kill = document.createElement("button");
  kill.className = "kill";
  kill.title = "удалить символ";
  kill.textContent = "×";
  kill.onclick = () => {
    if (confirm(`Удалить символ ${symbol.id}?`)) call("/api/symbols/delete", { id: symbol.id });
  };
  head.append(kill);

  const zone = document.createElement("div");
  zone.className = "drop-zone";
  if (symbol.image) {
    const img = document.createElement("img");
    img.src = `/symimg/${encodeURIComponent(state.active)}/${symbol.image}?v=${Date.now()}`;
    img.alt = `символ ${symbol.id}`;
    zone.appendChild(img);
  } else {
    zone.textContent = "перетащи картинку";
  }
  zone.onclick = () => pick((file) => upload(file, symbol.id));

  const types = document.createElement("div");
  types.className = "types";
  TYPES.forEach((kind) => {
    const button = document.createElement("button");
    button.className = "type" + (symbol.type === kind ? " on" : "");
    button.dataset.type = kind;
    button.textContent = kind;
    button.onclick = () => call("/api/symbols/update", { id: symbol.id, type: kind });
    types.appendChild(button);
  });

  dropTarget(node, (files) => upload(files[0], symbol.id));
  node.append(head, zone, types, pays(symbol));
  return node;
}

// id правится руками и может идти с дырами: hidden-ам удобно жить на 20 и 30.
function idField(symbol) {
  const box = document.createElement("label");
  box.className = "id";
  box.append(document.createTextNode("ID"));

  const input = document.createElement("input");
  input.type = "number";
  input.min = 1;
  input.max = MAX_ID;
  input.value = symbol.id;
  input.title = `номер символа, 1..${MAX_ID}`;
  input.onchange = async () => {
    const wanted = Number(input.value);
    if (wanted === symbol.id) return;
    // номер занят — символы им обменяются; говорим об этом, чтобы второй символ
    // не переехал молча
    const taken = state.symbols.find((item) => item.id === wanted);
    try {
      state = await api("/api/symbols/id", { id: symbol.id, new_id: wanted });
      render();
      if (taken) say(`символы ${symbol.id} и ${wanted} обменялись номерами`, true);
    } catch (error) {
      say(error.message); // кривой номер — говорим и откатываем поле
      input.value = symbol.id;
    }
  };
  box.appendChild(input);
  return box;
}

function pays(symbol) {
  const box = document.createElement("div");
  box.className = "pays";
  const title = document.createElement("div");
  title.className = "pays-title";
  title.textContent = "выплаты за N в линии";
  box.appendChild(title);

  // скрытый превращается до подсчёта линий, поэтому за себя не платит никогда —
  // не показываем поля, которые всё равно ни на что не влияют
  if (symbol.type === "hidden") {
    title.textContent = "скрытый символ";
    const note = document.createElement("div");
    note.className = "pays-note";
    note.textContent = "за себя не платит · веса превращения — на вкладке «Скрытые»";
    box.appendChild(note);
    return box;
  }

  for (let length = 1; length <= state.field.reels; length++) {
    const row = document.createElement("div");
    row.className = "pay-row";

    const label = document.createElement("b");
    label.textContent = length;

    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.placeholder = "—";
    const amount = symbol.pays[String(length)];
    if (amount !== undefined) {
      input.value = amount;
      input.classList.add("filled");
    }
    input.onchange = () =>
      call("/api/symbols/pay", { id: symbol.id, length, amount: input.value });

    const note = document.createElement("span");
    note.className = "bet-note" + (amount !== undefined ? " on" : "");
    note.textContent = amount === undefined ? "" : `${trim(amount / state.bet)}×ставки`;

    row.append(label, input, note);
    box.appendChild(row);
  }
  return box;
}

function trim(value) {
  return Number(value.toFixed(3)).toString();
}

function addCard() {
  const node = document.createElement("div");
  node.className = "card add";
  const plus = document.createElement("div");
  plus.className = "plus";
  plus.textContent = "+";
  const label = document.createElement("div");
  label.textContent = `символ ${nextId()}`;
  const note = document.createElement("small");
  note.textContent = "или брось сюда картинки — по символу на файл";
  node.append(plus, label, note);
  node.onclick = () => call("/api/symbols/add", { type: "low" });
  dropTarget(node, uploadMany);
  return node;
}

function nextId() {
  return state.symbols.reduce((max, symbol) => Math.max(max, symbol.id), 0) + 1;
}

// --- вкладка СКРЫТЫЕ ---------------------------------------------------------
//
// У каждого hidden-символа своя таблица весов «во что превращаться». Веса
// относительные: 10 и 30 значат ровно то же, что 1 и 3, — проценты считаются
// здесь и только показываются.

function renderHidden() {
  const hiddens = state.symbols.filter((symbol) => symbol.type === "hidden");
  const targets = state.symbols.filter((symbol) => symbol.type !== "hidden");
  hiddenCounter.textContent = `скрытых символов: ${hiddens.length}`;

  hiddenCards.textContent = "";
  if (!hiddens.length) {
    hiddenCards.innerHTML =
      '<div class="empty">Скрытых символов нет.<br>' +
      'Поставь символу тип <b>hidden</b> на вкладке «Символы» — и он появится здесь.</div>';
    return;
  }
  hiddens.forEach((symbol) => hiddenCards.appendChild(hiddenCard(symbol, targets)));
}

function hiddenCard(symbol, targets) {
  const node = document.createElement("section");
  node.className = "hidden-card";

  const total = Object.values(symbol.weights || {}).reduce((sum, w) => sum + Number(w), 0);

  const head = document.createElement("div");
  head.className = "hidden-head";
  head.append(symbolCell(symbol.id, "who-img"));
  const title = document.createElement("div");
  title.innerHTML =
    `<b>ID ${symbol.id}</b>${symbol.name ? ` · ${symbol.name}` : ""}` +
    `<small>${total ? `сумма весов ${trim(total)}` : "веса не заданы — играть с ним нельзя"}</small>`;
  title.className = "hidden-title" + (total ? "" : " warn");
  head.appendChild(title);
  node.appendChild(head);

  if (!targets.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "не во что превращаться — заведи обычные символы";
    node.appendChild(empty);
    return node;
  }

  const table = document.createElement("div");
  table.className = "weight-rows";
  targets.forEach((target) => {
    const weight = symbol.weights?.[String(target.id)];
    const row = document.createElement("div");
    row.className = "weight-row" + (weight === undefined ? "" : " on");

    const who = document.createElement("div");
    who.className = "who-cell";
    who.append(
      symbolCell(target.id, "who-img"),
      document.createTextNode(`ID ${target.id} · ${target.type}`)
    );

    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.placeholder = "—";
    if (weight !== undefined) input.value = weight;
    input.onchange = () =>
      call("/api/symbols/weight", { id: symbol.id, target: target.id, weight: input.value });

    const share = document.createElement("span");
    share.className = "share" + (weight === undefined ? " zero" : "");
    share.textContent =
      weight === undefined || !total ? "—" : `${((Number(weight) / total) * 100).toFixed(1)}%`;

    row.append(who, input, share);
    table.appendChild(row);
  });

  node.appendChild(table);
  return node;
}

// --- вкладка ПОЛЕ ------------------------------------------------------------

function renderField() {
  const { rows, reels, paylines } = state.field;
  if (document.activeElement !== rowsInput) rowsInput.value = rows;
  if (document.activeElement !== reelsInput) reelsInput.value = reels;
  linesCounter.textContent = `линий: ${paylines.length}`;

  linesBox.textContent = "";
  paylines.forEach((line, index) => linesBox.appendChild(lineCard(line, index)));
}

function lineCard(line, index) {
  const { rows, reels } = state.field;
  const node = document.createElement("div");
  node.className = "line-card";

  const head = document.createElement("div");
  head.className = "line-head";
  const title = document.createElement("span");
  title.textContent = `L${String(index + 1).padStart(2, "0")}`;
  const kill = document.createElement("button");
  kill.className = "kill";
  kill.title = "удалить линию";
  kill.textContent = "×";
  kill.onclick = () => {
    const lines = state.field.paylines.filter((_, position) => position !== index);
    call("/api/field/lines", { lines });
  };
  head.append(title, kill);

  const cells = document.createElement("div");
  cells.className = "line-grid";
  cells.style.gridTemplateColumns = `repeat(${reels}, 1fr)`;
  for (let row = 0; row < rows; row++) {
    for (let reel = 0; reel < reels; reel++) {
      const cell = document.createElement("button");
      cell.className = "cell" + (line[reel] === row ? " on" : "");
      cell.title = `барабан ${reel + 1}, ряд ${row + 1}`;
      cell.onclick = () => {
        const lines = state.field.paylines.map((item) => [...item]);
        lines[index][reel] = row;
        call("/api/field/lines", { lines });
      };
      cells.appendChild(cell);
    }
  }

  const code = document.createElement("div");
  code.className = "line-code";
  code.textContent = `[${line.join(", ")}]`;

  node.append(head, cells, code);
  return node;
}

// --- вкладка ПЕРЕСЕЧЕНИЕ -----------------------------------------------------

function sendGaps(rules) {
  call("/api/gaps/set", { rules });
}

function renderGaps() {
  const rules = state.gaps || [];
  gapsCounter.textContent = `правил: ${rules.length}`;
  gapRows.textContent = "";

  if (!rules.length) {
    const empty = document.createElement("div");
    empty.className = "gap-row empty-row";
    empty.textContent = "правил нет — символы встанут как лягут";
    gapRows.appendChild(empty);
    return;
  }
  rules.forEach((rule, index) => gapRows.appendChild(gapRow(rule, index)));
}

function gapRow(rule, index) {
  const node = document.createElement("div");
  node.className = "gap-row";

  const change = (patch) => {
    const rules = (state.gaps || []).map((item, position) =>
      position === index ? { ...item, ...patch } : item
    );
    sendGaps(rules);
  };

  const between = document.createElement("span");
  between.textContent = "между";
  const and = document.createElement("span");
  and.textContent = "и";
  const least = document.createElement("span");
  least.textContent = "минимум";
  const tail = document.createElement("span");
  tail.textContent = "символов";

  const gap = document.createElement("input");
  gap.type = "number";
  gap.min = "0";
  gap.value = rule.min;
  gap.onchange = () => change({ min: Math.max(0, Number(gap.value) || 0) });

  const kill = document.createElement("button");
  kill.className = "kill";
  kill.textContent = "×";
  kill.title = "убрать правило";
  kill.onclick = () => sendGaps((state.gaps || []).filter((_, position) => position !== index));

  node.append(
    between,
    targetSelect(rule.a, (value) => change({ a: value })),
    and,
    targetSelect(rule.b, (value) => change({ b: value })),
    least,
    gap,
    fillerSelect(rule.filler, (value) => change({ filler: value })),
    tail,
    kill
  );
  return node;
}

function targetSelect(value, onPick) {
  const select = document.createElement("select");

  const classes = document.createElement("optgroup");
  classes.label = "класс символов";
  TYPES.forEach((kind) => classes.appendChild(option(`type:${kind}`, `все ${kind}`, value)));

  const singles = document.createElement("optgroup");
  singles.label = "конкретный символ";
  state.symbols.forEach((symbol) =>
    singles.appendChild(option(`id:${symbol.id}`, `ID ${symbol.id} · ${symbol.type}`, value))
  );

  select.append(classes, singles);
  if (!select.querySelector("option[selected]")) select.value = value;
  select.onchange = () => onPick(select.value);
  return select;
}

function fillerSelect(value, onPick) {
  const select = document.createElement("select");
  TYPES.forEach((kind) => select.appendChild(option(kind, kind, value)));
  select.appendChild(option("any", "любых", value));
  select.value = value;
  select.onchange = () => onPick(select.value);
  return select;
}

function option(value, label, current) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  node.selected = value === current;
  return node;
}

// --- вкладка ЛЕНТЫ -----------------------------------------------------------

// Символ на риле описан тремя вещами: сколько его всего, какие длины стека ему
// разрешены с шансом на каждую, и можно ли ему слипаться. Количество — закон,
// шансы — ориентир: раскладку стеков подбирает генератор.

// Правим либо выбранный рил, либо мастер-рил — таблица одна и та же, меняется
// только хранилище и адрес записи. Пять рилов при включённом мастере не
// перезаписываются: они выводятся на ходу при генерации.
function masterOn() {
  return !!state.master_on;
}

function activeStore() {
  return masterOn() ? state.master || {} : state.reels[currentReel] || {};
}

function reelCfg(reel, symbolId) {
  const store = masterOn() ? state.master || {} : state.reels[reel] || {};
  const entry = store[String(symbolId)];
  return {
    stacks: { ...(entry?.stacks || {}) },
    infinity: !!entry?.infinity,
    count: Number(entry?.count) || 0,
    stacks_total: Number(entry?.stacks_total) || 0,
  };
}

function reelTotal(reel) {
  const store = masterOn() ? state.master || {} : state.reels[reel] || {};
  return Object.values(store).reduce((sum, cfg) => sum + (Number(cfg.count) || 0), 0);
}

function sendCfg(symbolId, cfg) {
  const body = { symbol: symbolId, stacks: cfg.stacks, infinity: cfg.infinity };
  if (masterOn()) call("/api/master/symbol", body);
  else call("/api/reels/symbol", { reel: currentReel, ...body });
}

function stacksTotal(cfg) {
  return Object.values(cfg.stacks).reduce((sum, times) => sum + (Number(times) || 0), 0);
}

function symbolsOf(cfg) {
  return Object.keys(cfg.stacks).reduce(
    (sum, len) => sum + Number(len) * (Number(cfg.stacks[len]) || 0),
    0
  );
}

// Средняя длина стека теперь не оценка, а факт: символы делим на стеки.
function avgStack(cfg) {
  const stacks = stacksTotal(cfg);
  return stacks ? symbolsOf(cfg) / stacks : 0;
}

function stacksOf(cfg) {
  return stacksTotal(cfg);
}

// Стеки заказаны точно, поэтому средняя — деление, а не оценка. Оговорка
// осталась одна: при ∞ соседние стеки могут слипнуться в один длиннее.
const STACK_NOTE_HINT =
  "символов делить на стеки · при ∞ соседние стеки могут слипаться, " +
  "и фактические серии на ленте выйдут длиннее";

function stackNote(cfg) {
  const stacks = stacksTotal(cfg);
  if (!stacks || cfg.mixed) return "";
  return (
    `<br><span class="avg-note" title="${STACK_NOTE_HINT}">` +
    `${stacks} стеков · в стеке ${Number(avgStack(cfg).toFixed(2))}</span>`
  );
}

// --- паттерн рилов -----------------------------------------------------------
//
// Ползунок значит множитель к мастер-количеству. Середина — ×1 всегда: нижняя
// половина растягивается на 0…1, верхняя на 1…макс. Поэтому смена потолка ×3 → ×5
// не двигает уже выставленные количества, а только растягивает шкалу.
//
// Цель паттерна — группа или одиночный символ, ровно как строки в таблице:
// у члена группы своей цели нет, иначе его тянули бы две настройки сразу.

const PATTERN_STEPS = 500; // столько шагов на каждую половину ползунка
let patternTarget = null;

function multToPos(mult, max) {
  if (mult <= 1) return Math.round(mult * PATTERN_STEPS);
  if (max <= 1) return PATTERN_STEPS;
  return Math.round(PATTERN_STEPS * (1 + (mult - 1) / (max - 1)));
}

function posToMult(pos, max) {
  return pos <= PATTERN_STEPS
    ? pos / PATTERN_STEPS
    : 1 + ((pos - PATTERN_STEPS) / PATTERN_STEPS) * (max - 1);
}

function patternEntry(key) {
  const stored = (state.pattern || {})[key];
  const max = Number(stored?.max) || 2;
  const mult = [];
  for (let reel = 0; reel < state.field.reels; reel++) {
    const value = Number(stored?.mult?.[reel]);
    mult.push(Number.isFinite(value) ? value : 1);
  }
  // counts надо протащить как есть: собрав объект только из max и mult, таблица
  // приоритета читала каждую клетку как «не трогал» и молча теряла ручной ввод
  return { max, mult, counts: stored?.counts || {} };
}

function patternTargets() {
  const grouped = new Set();
  const targets = [];
  (state.groups || []).forEach((group) => {
    if (!group.members.length) return;
    group.members.forEach((id) => grouped.add(id));
    targets.push({ key: `group:${group.name}`, label: group.name, group });
  });
  state.symbols
    .filter((symbol) => !grouped.has(symbol.id))
    .forEach((symbol) => targets.push({ key: `id:${symbol.id}`, label: `ID ${symbol.id}`, symbol }));
  return targets;
}

// Мастер-количество цели: у группы это сумма её членов, иначе сам символ.
function masterCount(target) {
  const store = state.master || {};
  if (target.group) {
    return target.group.members.reduce(
      (sum, id) => sum + (Number(store[String(id)]?.count) || 0),
      0
    );
  }
  return Number(store[String(target.symbol.id)]?.count) || 0;
}

function renderPattern() {
  const box = $("pattern");
  box.textContent = "";

  // Паттерн живёт только в режиме мастера: множить нечего, пока каждый рил
  // настраивается руками. Вкладку не прячем — прыгающие вкладки хуже пустой.
  if (!masterOn()) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML =
      "Паттерн множит <b>мастер-рил</b> — по своему множителю на каждый барабан.<br>" +
      "Сейчас рилы настраиваются по отдельности, множить нечего.";
    const turn = document.createElement("button");
    turn.className = "btn primary";
    turn.textContent = "Включить мастер-рил";
    turn.onclick = () => call("/api/master/mode", { value: true, from_reel: currentReel });
    empty.append(document.createElement("br"), turn);
    box.appendChild(empty);
    return;
  }

  const targets = patternTargets();
  if (!targets.length) {
    box.innerHTML = '<div class="empty">сначала заведи символы на вкладке «Символы»</div>';
    return;
  }
  if (!targets.some((item) => item.key === patternTarget)) patternTarget = targets[0].key;

  const target = targets.find((item) => item.key === patternTarget);
  const entry = patternEntry(target.key);
  const base = masterCount(target);

  const head = document.createElement("div");
  head.className = "pattern-head";

  const who = document.createElement("div");
  who.className = "who-cell";
  who.append(
    target.group
      ? Object.assign(document.createElement("div"), {
          className: "group-mark",
          textContent: "▣",
        })
      : symbolCell(target.symbol.id, "who-img")
  );
  const label = document.createElement("div");
  // без символа в мастере множитель умножает ноль — об этом надо сказать прямо,
  // иначе ползунки крутятся, а лента не меняется
  label.innerHTML =
    `<b>${target.label}</b><small class="${base ? "" : "warn"}">` +
    (base
      ? `в мастере ${base} симв.` +
        (target.group ? ` · ${target.group.members.length} символов` : "")
      : "нет в мастер-риле — множители ни на что не влияют") +
    "</small>";
  who.appendChild(label);

  const maxBox = document.createElement("label");
  maxBox.className = "inline pattern-max";
  maxBox.append(document.createTextNode("максимум ×"));
  const maxInput = document.createElement("input");
  maxInput.type = "number";
  maxInput.min = "1";
  maxInput.max = "100";
  maxInput.step = "1";
  maxInput.value = entry.max;
  maxInput.title = "во сколько раз множитель может превысить мастер-количество";
  maxInput.onchange = () => {
    const value = Number(maxInput.value);
    if (!Number.isFinite(value) || value < 1) {
      maxInput.value = entry.max; // откат, как и у множителя
      return;
    }
    call("/api/pattern/set", { target: target.key, max: value });
  };
  maxBox.appendChild(maxInput);

  const hint = document.createElement("span");
  hint.className = "hint";
  hint.textContent = "середина — ×1 · ноль убирает символ с рила совсем";

  head.append(who, maxBox, hint);
  box.appendChild(head);

  const body = document.createElement("div");
  body.className = "pattern-body";

  const board = document.createElement("div");
  board.className = "board";
  for (let reel = 0; reel < state.field.reels; reel++) {
    board.appendChild(patternColumn(target, entry, base, reel, box));
  }
  body.append(board, mixChart(targets, target));
  box.appendChild(body);
  box.appendChild(skewTable(target, entry));

  const list = document.createElement("div");
  list.className = "pattern-list";
  targets.forEach((item) => {
    const chip = document.createElement("button");
    chip.className = "target-chip" + (item.key === patternTarget ? " on" : "");
    if (item.group) {
      chip.append(
        Object.assign(document.createElement("span"), { textContent: "▣" }),
        document.createTextNode(item.label)
      );
    } else {
      chip.append(symbolCell(item.symbol.id, "who-img"), document.createTextNode(item.label));
      chip.style.setProperty("--sym", `var(--${item.symbol.type})`);
    }
    const touched = (state.pattern || {})[item.key];
    if (touched && touched.mult.some((value) => Number(value) !== 1)) {
      chip.appendChild(
        Object.assign(document.createElement("i"), { className: "tag", textContent: "≠" })
      );
    }
    chip.onclick = () => {
      patternTarget = item.key;
      renderPattern();
    };
    list.appendChild(chip);
  });
  box.appendChild(list);
}

// Приоритет стеков: строка на каждую длину, которая у цели есть в мастере,
// клетка на каждый рил. В клетке само число стеков, а не множитель: «десять
// двоек на первом риле» читается прямо, а «×2» требует счёта в голове.
//
// Пусто — значит не трогал: берётся из мастера и правится общим множителем.
// Вписанное число сильнее и мастера, и множителя.
function masterStacks(target) {
  const store = state.master || {};
  const ids = target.group ? target.group.members : [target.symbol.id];
  const merged = {};
  ids.forEach((id) => {
    Object.entries(store[String(id)]?.stacks || {}).forEach(([len, times]) => {
      merged[len] = Math.max(merged[len] || 0, Number(times) || 0);
    });
  });
  return merged;
}

function handOf(entry, len, reel) {
  const value = entry.counts?.[String(len)]?.[reel];
  return value === null || value === undefined ? null : Number(value);
}

function skewTable(target, entry) {
  const node = document.createElement("div");
  node.className = "skew";

  const head = document.createElement("h4");
  head.textContent = "Приоритет стеков по рилам";
  const note = document.createElement("div");
  note.className = "avg";
  node.append(head, note);

  const stacks = masterStacks(target);
  const lengths = Object.keys(stacks).map(Number).sort((a, b) => a - b);
  if (!lengths.length) {
    note.textContent = "у цели нет стеков в мастер-риле — сначала задай их на «Лентах»";
    return node;
  }
  note.textContent =
    "в клетке — сколько стеков этой длины ляжет на этот рил · " +
    "пусто значит «как в мастере» · вписанное число сильнее общего множителя";

  const grid = document.createElement("div");
  grid.className = "skew-grid";
  grid.style.setProperty("--reels", String(state.field.reels));

  const corner = document.createElement("div");
  corner.className = "skew-corner";
  corner.textContent = "длина";
  grid.appendChild(corner);
  for (let reel = 0; reel < state.field.reels; reel++) {
    const label = document.createElement("div");
    label.className = "skew-head";
    label.textContent = `Рил ${reel + 1}`;
    grid.appendChild(label);
  }

  lengths.forEach((len) => {
    const label = document.createElement("div");
    label.className = "skew-len";
    label.innerHTML = `×${len}<small>${stacks[len]} в мастере</small>`;
    grid.appendChild(label);

    for (let reel = 0; reel < state.field.reels; reel++) {
      grid.appendChild(handCell(target, entry, stacks[len], len, reel));
    }
  });

  node.appendChild(grid);
  return node;
}

function handCell(target, entry, base, len, reel) {
  const hand = handOf(entry, len, reel);
  // половина вверх — так же, как считает сервер
  const inherited = Math.floor(base * entry.mult[reel] + 0.5);

  const cell = document.createElement("div");
  cell.className = "skew-cell" + (hand === null ? "" : " on");

  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "numeric";
  // пустое поле с подсказкой-числом: сразу видно, что унаследовано
  input.placeholder = String(inherited);
  if (hand !== null) input.value = hand;
  input.title =
    `сколько стеков длиной ${len} на риле ${reel + 1}` +
    `\nпусто — как в мастере (${inherited})`;

  const out = document.createElement("div");
  out.className = "skew-out";
  const show = (stacks, own) => {
    out.innerHTML = stacks
      ? `${stacks * len} симв.<small>${own ? "задано руками" : "из мастера"}</small>`
      : '<span class="zero">нет на риле</span>';
    cell.classList.toggle("off", !stacks);
    cell.classList.toggle("on", own);
  };
  show(hand === null ? inherited : hand, hand !== null);

  input.onchange = () => {
    const text = String(input.value).trim();
    if (text === "") {
      show(inherited, false);
      call("/api/pattern/count", { target: target.key, length: len, reel, value: "" });
      return;
    }
    const value = Math.round(Number(text));
    if (!Number.isFinite(value) || value < 0) {
      input.value = hand === null ? "" : hand; // опечатка ничего не меняет
      return;
    }
    show(value, true);
    call("/api/pattern/count", { target: target.key, length: len, reel, value });
  };

  cell.append(input, out);
  return cell;
}

// Состав рилов столбцами: на каждый рил столбец в полную высоту, поделённый на
// доли целей. Считается из state.derived — того, что сервер реально отдаст
// генератору. Второй реализации тех же правил здесь быть не должно: она рано
// или поздно разошлась бы с настоящей.
function mixChart(targets, selected) {
  const node = document.createElement("div");
  node.className = "mix";

  const head = document.createElement("h4");
  head.textContent = "Состав рилов";
  const note = document.createElement("div");
  note.className = "avg";
  note.textContent = "каждый столбец — целый рил · наведи на полосу, чтобы увидеть долю";
  node.append(head, note);

  const derived = state.derived || [];
  const columns = document.createElement("div");
  columns.className = "mix-columns";

  for (let reel = 0; reel < state.field.reels; reel++) {
    const store = derived[reel] || {};
    const total = Object.values(store).reduce((sum, e) => sum + (Number(e.count) || 0), 0);

    const column = document.createElement("div");
    column.className = "mix-column";

    const bar = document.createElement("div");
    bar.className = "mix-bar";
    targets.forEach((item, index) => {
      const ids = item.group ? item.group.members : [item.symbol.id];
      const count = ids.reduce((sum, id) => sum + (Number(store[String(id)]?.count) || 0), 0);
      if (!count || !total) return;
      const share = (count / total) * 100;

      const part = document.createElement("div");
      part.className = "mix-part" + (item.key === selected.key ? " on" : "");
      part.style.height = `${share}%`;
      part.style.setProperty("--sym", mixTint(item));
      // оттенок внутри одного типа чуть разный: два спешела подряд иначе
      // слились бы в одну полосу
      part.style.filter = `brightness(${1 + ((index % 3) - 1) * 0.22})`;
      part.title = `${item.label} · ${count} симв. · ${share.toFixed(1)}% рила ${reel + 1}`;
      if (share >= 7) {
        part.textContent = `${Math.round(share)}%`;
      }
      part.onclick = () => {
        patternTarget = item.key;
        renderPattern();
      };
      bar.appendChild(part);
    });

    const label = document.createElement("div");
    label.className = "mix-label";
    label.innerHTML = `Рил ${reel + 1}<small>${total || "—"} симв.</small>`;

    column.append(bar, label);
    columns.appendChild(column);
  }

  node.appendChild(columns);
  return node;
}

function mixTint(item) {
  if (item.group) {
    const first = symbolById(item.group.members[0]);
    return `var(--${first ? first.type : "accent"})`;
  }
  return `var(--${item.symbol.type})`;
}

function patternColumn(target, entry, base, reel, box) {
  const mult = entry.mult[reel];
  const node = document.createElement("div");
  node.className = "board-reel" + (mult === 0 ? " off" : "");
  node.style.setProperty("--sym", target.group ? "var(--accent)" : `var(--${target.symbol.type})`);

  const title = document.createElement("div");
  title.className = "board-title";
  title.textContent = `Рил ${reel + 1}`;

  // Клетки барабана заполняем символом цели, а у группы — её членами по кругу:
  // пустые клетки читались как сломанные и не говорили ничего.
  const members = target.group
    ? target.group.members
    : [target.symbol.id];
  const face = document.createElement("div");
  face.className = "board-face";
  for (let row = 0; row < state.field.rows; row++) {
    const cell = document.createElement("div");
    cell.className = "board-cell";
    cell.appendChild(symbolCell(members[row % members.length], "who-img"));
    face.appendChild(cell);
  }

  // Множитель — поле ввода, а не подпись: ползунком удобно искать на глаз, а
  // вписать ×2.5 точно можно только числом.
  const multBox = document.createElement("label");
  multBox.className = "board-mult";
  multBox.append(Object.assign(document.createElement("span"), { textContent: "×" }));
  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "decimal";
  input.value = Number(mult.toFixed(2));
  input.title = "множитель к мастер-количеству — впиши число или тяни ползунок";
  multBox.appendChild(input);

  const count = document.createElement("div");
  count.className = "board-count";
  count.innerHTML = patternCount(mult, base);

  const gauge = document.createElement("div");
  gauge.className = "gauge tall";
  const fill = document.createElement("div");
  fill.className = "gauge-fill";
  fill.style.height = `${(multToPos(mult, entry.max) / (PATTERN_STEPS * 2)) * 100}%`;
  const mid = document.createElement("div");
  mid.className = "gauge-mid";
  mid.title = "×1 — как в мастере";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "gauge-slider";
  slider.min = "0";
  slider.max = String(PATTERN_STEPS * 2);
  slider.step = "1";
  slider.value = String(multToPos(mult, entry.max));
  slider.title = "множитель к мастер-количеству — тяни";
  gauge.append(fill, mid, slider);

  const show = (value) => {
    count.innerHTML = patternCount(value, base);
    node.classList.toggle("off", value < 0.005);
  };

  slider.oninput = () => {
    const value = posToMult(Number(slider.value), entry.max);
    fill.style.height = `${(Number(slider.value) / (PATTERN_STEPS * 2)) * 100}%`;
    input.value = Number(value.toFixed(2));
    show(value);
  };
  slider.onchange = () =>
    call("/api/pattern/set", {
      target: target.key,
      reel,
      mult: posToMult(Number(slider.value), entry.max),
    });

  input.onchange = () => {
    // Не число — откатываем поле и ничего не отправляем. Ноль здесь означает
    // «символа на этом риле нет», и опечатка не должна стоить так дорого;
    // явный «0» при этом разбирается как число и работает.
    const text = String(input.value).trim().replace(",", ".");
    const value = text === "" ? NaN : Number(text);
    if (!Number.isFinite(value) || value < 0) {
      input.value = Number(mult.toFixed(2));
      return;
    }
    slider.value = String(multToPos(Math.min(value, entry.max), entry.max));
    fill.style.height = `${(Number(slider.value) / (PATTERN_STEPS * 2)) * 100}%`;
    show(value);
    // вписал больше потолка — потолок поднимается за числом, иначе введённое
    // значение просто обрезалось бы и правка выглядела бы сломанной
    const body = { target: target.key, reel, mult: value };
    if (value > entry.max) body.max = value;
    call("/api/pattern/set", body);
  };

  node.append(title, face, multBox, count, gauge);
  return node;
}

function patternCount(mult, base) {
  if (mult < 0.005) return '<span class="zero">нет на риле</span>';
  if (!base) return '<span class="warn">нет в мастере</span>';
  return `${Math.round(base * mult)} симв.`;
}

function renderReels() {
  if (currentReel >= state.field.reels) currentReel = 0;

  // В режиме мастера выбирать рил незачем — правится один эталон, а пять
  // выводятся из него. Вместо переключателя стоит отметка «мастер».
  reelPick.textContent = "";
  if (masterOn()) {
    const chip = document.createElement("div");
    chip.className = "reel-btn on master-chip";
    const title = document.createTextNode("Мастер-рил");
    const total = document.createElement("small");
    total.textContent = `${reelTotal(0)} симв. · ×множители в «Паттерне»`;
    chip.append(title, total);
    reelPick.appendChild(chip);
  } else {
    for (let reel = 0; reel < state.field.reels; reel++) {
      const button = document.createElement("button");
      button.className = "reel-btn" + (reel === currentReel ? " on" : "");
      const title = document.createTextNode(`Рил ${reel + 1}`);
      const total = document.createElement("small");
      total.textContent = `${reelTotal(reel)} симв.`;
      button.append(title, total);
      button.onclick = () => {
        currentReel = reel;
        renderReels();
      };
      reelPick.appendChild(button);
    }
  }

  const master = $("btn-master");
  master.classList.toggle("on", masterOn());
  master.onclick = () =>
    call("/api/master/mode", { value: !masterOn(), from_reel: currentReel });

  $("btn-reel-copy").classList.toggle("hidden", masterOn());
  const clear = $("btn-reel-clear");
  clear.textContent = masterOn() ? "Очистить мастер" : "Очистить рил";

  const filler = $("btn-filler-low");
  filler.classList.toggle("on", !!state.filler_low);
  filler.onclick = () => call("/api/set/filler-low", { value: !state.filler_low });

  stackRows.textContent = "";
  if (!state.symbols.length) {
    const empty = document.createElement("div");
    empty.className = "stack-row empty-row";
    empty.textContent = "сначала заведи символы на вкладке «Символы»";
    stackRows.appendChild(empty);
    renderStrips();
    return;
  }

  stackRows.appendChild(stackHead());

  // Сначала группы со своими членами, потом одиночки. Членство общее на сет,
  // поэтому порядок один и тот же на всех рилах — глаз не переучивается.
  const grouped = new Set();
  (state.groups || []).forEach((group) => {
    stackRows.appendChild(groupRow(group));
    group.members.forEach((id) => {
      const symbol = symbolById(id);
      if (!symbol) return;
      grouped.add(id);
      stackRows.appendChild(memberRow(symbol, group));
    });
  });

  const loose = state.symbols.filter((symbol) => !grouped.has(symbol.id));
  if ((state.groups || []).length && loose.length) {
    stackRows.appendChild(looseHead(loose.length));
  }
  loose.forEach((symbol) => stackRows.appendChild(stackRow(symbol)));

  stackRows.appendChild(totalsRow());
  renderStrips();
}

// Заголовок «вне групп» — он же зона, куда можно бросить символ, чтобы вынуть
// его из группы, если крестиком промахнулся.
function looseHead(count) {
  const node = document.createElement("div");
  node.className = "stack-row loose-head";
  const label = document.createElement("div");
  label.className = "who wide-head";
  label.textContent = `вне групп: ${count}`;
  const hint = document.createElement("span");
  hint.className = "hint drop-hint";
  hint.textContent = "брось сюда символ, чтобы вынуть его из группы";
  node.append(label, hint);
  dropZone(node, (symbolId) => {
    const group = groupOf(symbolId);
    if (group) call("/api/groups/member", { name: group.name, symbol: symbolId, join: false });
  });
  return node;
}

function groupOf(symbolId) {
  return (state.groups || []).find((group) => group.members.includes(symbolId));
}

// Перетаскивание: символ берётся за миниатюру, а бросают его на строку группы
// или на зону «вне групп». Тянуть строку целиком при её высоте неудобно.
function dragHandle(node, symbolId) {
  node.draggable = true;
  node.classList.add("grab");
  node.title = "перетащи в группу";
  node.ondragstart = (event) => {
    event.dataTransfer.setData("text/plain", String(symbolId));
    event.dataTransfer.effectAllowed = "move";
  };
}

function dropZone(node, onSymbol) {
  node.ondragover = (event) => {
    event.preventDefault();
    node.classList.add("drop");
  };
  node.ondragleave = () => node.classList.remove("drop");
  node.ondrop = (event) => {
    event.preventDefault();
    node.classList.remove("drop");
    const symbolId = Number(event.dataTransfer.getData("text/plain"));
    if (symbolId) onSymbol(symbolId);
  };
}

function totalsRow() {
  const node = document.createElement("div");
  node.className = "stack-row totals";
  const label = document.createElement("div");
  label.className = "who wide-head";
  label.textContent = masterOn() ? "Итого в мастере" : `Итого в ленте ${currentReel + 1}`;
  const spacer = document.createElement("div");
  spacer.className = "chips";
  const total = document.createElement("div");
  total.className = "total";
  // средняя по всему рилу: сколько символов приходится на один стек
  const size = reelTotal(currentReel);
  const stacks = Object.keys(activeStore()).reduce(
    (sum, key) => sum + stacksOf(reelCfg(currentReel, Number(key))),
    0
  );
  // стеки заказаны точно, поэтому и здесь никаких «≈» и «~»
  total.innerHTML =
    `<b>${size}</b> симв. · <b>100%</b>` +
    (stacks
      ? `<br><span class="avg-note" title="${STACK_NOTE_HINT}">` +
        `${stacks} стеков · ${Number((size / stacks).toFixed(2))} на стек</span>`
      : "");
  node.append(label, spacer, total);
  return node;
}

// Колонки длин: всегда 1..6 (или до высоты поля, если она больше) плюс любые
// длины, заведённые кнопкой «+ длиннее». Набор общий для всех символов рила —
// иначе колонки разъехались бы от строки к строке.
function reelLengths() {
  const top = Math.max(6, state.field.rows);
  const base = Array.from({ length: top }, (_, index) => index + 1);
  const extra = new Set();
  Object.values(activeStore()).forEach((cfg) => {
    Object.keys(cfg.stacks || {})
      .map(Number)
      .filter((len) => len > top)
      .forEach((len) => extra.add(len));
  });
  return base.concat([...extra].sort((a, b) => a - b));
}

function stackHead() {
  const node = document.createElement("div");
  node.className = "stack-row head-row";
  const spacer = document.createElement("div");
  spacer.className = "who wide-head";
  spacer.textContent = "символ";

  const many = document.createElement("span");
  many.className = "how-many head-label";
  many.textContent = "стеков";

  // Заголовок группы стоит над своими колонками, а не сбоку от них: сбоку он
  // налезал на кнопки и читался как отдельный столбец.
  const group = document.createElement("div");
  group.className = "slots-head";
  const caption = document.createElement("div");
  caption.className = "slots-caption";
  caption.textContent = "сколько стеков какой длины";

  const cells = document.createElement("div");
  cells.className = "slots";
  reelLengths().forEach((len) => {
    const label = document.createElement("span");
    label.className = "slot-label";
    label.textContent = len;
    cells.appendChild(label);
  });

  group.append(caption, cells);
  node.append(spacer, many, group);
  return node;
}

// Общий конфиг группы: у членов он всегда одинаковый, потому что группа пишет
// во всех сразу. Разойтись значения могут только в момент сборки группы — тогда
// показываем «разные», и первая же правка их сводит.
function stacksKey(stacks) {
  return Object.keys(stacks)
    .map(Number)
    .sort((a, b) => a - b)
    .map((len) => `${len}:${stacks[String(len)]}`)
    .join(",");
}

function groupCfg(reel, group) {
  const entries = group.members.map((id) => reelCfg(reel, id));
  if (!entries.length) {
    return { stacks: {}, infinity: false, count: 0, stacks_total: 0, mixed: false };
  }
  const first = entries[0];
  const key = stacksKey(first.stacks);
  const mixed = entries.some(
    (item) => item.infinity !== first.infinity || stacksKey(item.stacks) !== key
  );
  return { ...first, mixed };
}

function sendGroupCfg(group, cfg) {
  const body = { group: group.name, stacks: cfg.stacks, infinity: cfg.infinity };
  if (masterOn()) call("/api/master/group", body);
  else call("/api/reels/group", { reel: currentReel, ...body });
}

// Строка группы и строка символа — одна форма. Разница в трёх вещах: что стоит
// слева, куда уходит правка (commit) и можно ли править вообще (члены заморожены,
// потому что их значения задаёт группа).
function configRow(options) {
  const { cfg, tint, locked, commit, lead, tail, klass } = options;
  const lengths = reelLengths();
  const node = document.createElement("div");
  node.className =
    "stack-row" + (klass ? ` ${klass}` : "") + (stacksTotal(cfg) ? "" : " empty-row");
  node.style.setProperty("--sym", tint);

  // Число стеков и число символов считаются из колонок, поэтому здесь показ,
  // а не ввод: два места для одного значения разошлись бы.
  const howMany = document.createElement("span");
  howMany.className = "how-many read" + (cfg.mixed ? " warn" : "");
  howMany.textContent = cfg.mixed ? "разные" : stacksTotal(cfg) || "—";
  howMany.title = "всего стеков — сумма по колонкам";

  const slots = document.createElement("div");
  slots.className = "slots";
  lengths.forEach((len) =>
    slots.appendChild(chanceColumn(cfg, len, node, locked ? null : commit))
  );

  const chips = document.createElement("div");
  chips.className = "chips";
  if (!locked) {
    const add = document.createElement("button");
    add.className = "btn ghost-add";
    add.textContent = "+ длиннее";
    add.title = "разрешить стек длиннее показанных колонок";
    add.onclick = () => {
      const len = Number(prompt("Длина стека:", String(Math.max(...lengths) + 1)));
      if (!len || len < 1) return;
      commit({ ...cfg, stacks: { ...cfg.stacks, [String(Math.round(len))]: 1 } });
    };
    chips.appendChild(add);
  }

  const inf = document.createElement("button");
  inf.className = "inf" + (cfg.infinity ? " on" : "");
  inf.textContent = "∞";
  inf.disabled = locked;
  inf.title = locked
    ? "задаётся группой"
    : "склейка разрешена: стеки могут вставать встык и давать стек любой длины";
  if (!locked) inf.onclick = () => commit({ ...cfg, infinity: !cfg.infinity });

  node.append(lead, howMany, slots, chips, inf, tail);
  refreshChances(node);
  return node;
}

function symbolLead(symbol, group) {
  const lead = document.createElement("div");
  lead.className = "lead";

  const thumb = document.createElement(symbol.image ? "img" : "div");
  thumb.className = "thumb";
  if (symbol.image) {
    thumb.src = `/symimg/${encodeURIComponent(state.active)}/${symbol.image}`;
    thumb.alt = "";
  }
  dragHandle(thumb, symbol.id);

  const who = document.createElement("div");
  who.className = "who";
  const id = document.createElement("b");
  id.textContent = `ID ${symbol.id}`;
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.dataset.type = symbol.type;
  badge.textContent = symbol.type;
  who.append(id, badge);

  if (group) {
    const out = document.createElement("button");
    out.className = "kill out";
    out.textContent = "×";
    out.title = `вынуть из группы «${group.name}»`;
    out.onclick = () =>
      call("/api/groups/member", { name: group.name, symbol: symbol.id, join: false });
    who.appendChild(out);
  }

  lead.append(thumb, who);
  return lead;
}

function stackRow(symbol) {
  const cfg = reelCfg(currentReel, symbol.id);
  const reelSize = reelTotal(currentReel);
  const share = reelSize ? (cfg.count / reelSize) * 100 : 0;

  const total = document.createElement("div");
  total.className = "total";
  // живая часть меняется прямо при перетаскивании, доля рила — только после
  // записи: она считается от всей ленты, а та ещё не пересчитана
  const live = document.createElement("div");
  live.className = "live-total";
  const share_line = document.createElement("div");
  share_line.className = "share-line";
  share_line.innerHTML = cfg.count
    ? `${Number(share.toFixed(1))}% рила` + (cfg.infinity ? " · склейка" : "")
    : "";
  total.append(live, share_line);

  return configRow({
    cfg,
    tint: `var(--${symbol.type})`,
    locked: false,
    commit: (next) => sendCfg(symbol.id, next),
    lead: symbolLead(symbol, null),
    tail: total,
    klass: "",
  });
}

// Член группы ничего не задаёт — значение ему рассылает группа. Шкала, которую
// нельзя тянуть, только занимала бы место, поэтому строка узкая и показывает
// одни цифры: сколько символов и какой процент приходится на каждую длину.
function memberRow(symbol, group) {
  const cfg = reelCfg(currentReel, symbol.id);
  const reelSize = reelTotal(currentReel);
  const share = reelSize ? (cfg.count / reelSize) * 100 : 0;

  const node = document.createElement("div");
  node.className = "stack-row member-row" + (cfg.count ? "" : " empty-row");
  node.style.setProperty("--sym", `var(--${symbol.type})`);

  const many = document.createElement("span");
  many.className = "how-many read";
  many.textContent = stacksTotal(cfg) || "—";
  many.title = `стеков — задаётся группой «${group.name}»`;

  const slots = document.createElement("div");
  slots.className = "slots";
  reelLengths().forEach((len) => {
    const times = cfg.stacks[String(len)];
    const cell = document.createElement("div");
    cell.className = "chance read" + (times === undefined ? "" : " on");
    cell.textContent = times === undefined ? "—" : String(times);
    if (times !== undefined) cell.title = `${times} стеков по ${len} = ${times * len} симв.`;
    slots.appendChild(cell);
  });

  const chips = document.createElement("div");
  chips.className = "chips";

  const inf = document.createElement("span");
  inf.className = "inf read" + (cfg.infinity ? " on" : "");
  inf.textContent = "∞";
  inf.title = cfg.infinity ? "склейка разрешена" : "склейка запрещена";

  // в узкой строке средняя идёт в ту же линию, чтобы не отрастить её обратно
  const total = document.createElement("div");
  total.className = "total";
  total.innerHTML = cfg.count
    ? `<b>${cfg.count}</b> симв. · <b>${Number(share.toFixed(1))}%</b>` +
      ` · <span class="avg-note" title="${STACK_NOTE_HINT}">` +
      `${Number(avgStack(cfg).toFixed(2))}/стек</span>`
    : "нет в ленте";

  node.append(symbolLead(symbol, group), many, slots, chips, inf, total);
  return node;
}

function groupRow(group) {
  const cfg = groupCfg(currentReel, group);
  const reelSize = reelTotal(currentReel);
  const laid = group.members.reduce((sum, id) => sum + reelCfg(currentReel, id).count, 0);

  const lead = document.createElement("div");
  lead.className = "lead";

  const mark = document.createElement("div");
  mark.className = "group-mark";
  mark.textContent = "▣";

  const who = document.createElement("div");
  who.className = "who";
  const title = document.createElement("b");
  title.className = "group-name";
  title.textContent = group.name;
  const note = document.createElement("span");
  note.className = "group-note";
  note.textContent = group.members.length
    ? `символов: ${group.members.length}`
    : "пусто — брось сюда символ";

  const tools = document.createElement("span");
  tools.className = "group-tools";
  const rename = document.createElement("button");
  rename.className = "kill";
  rename.textContent = "✎";
  rename.title = "переименовать группу";
  rename.onclick = () => {
    const name = prompt("Новое имя группы:", group.name);
    if (name && name !== group.name) {
      call("/api/groups/rename", { name: group.name, new_name: name });
    }
  };
  const kill = document.createElement("button");
  kill.className = "kill";
  kill.textContent = "✕";
  kill.title = "разобрать группу — значения символов останутся";
  kill.onclick = () => {
    if (confirm(`Разобрать группу «${group.name}»? Значения символов останутся.`)) {
      call("/api/groups/delete", { name: group.name });
    }
  };
  tools.append(rename, kill);
  who.append(title, note, tools);
  lead.append(mark, who);

  const total = document.createElement("div");
  total.className = "total";
  if (!group.members.length) {
    total.textContent = "нет символов";
  } else {
    const share = reelSize ? (laid / reelSize) * 100 : 0;
    // живая часть — на один символ группы: сумма по членам пересчитается после
    // записи, когда станет известен весь рил
    const live = document.createElement("div");
    live.className = "live-total";
    const rest = document.createElement("div");
    rest.className = "share-line";
    rest.innerHTML =
      `${laid} симв. всего · ${Number(share.toFixed(1))}% рила` +
      `<br>на каждый из ${group.members.length}:`;
    total.append(rest, live);
  }

  const node = configRow({
    cfg,
    tint: "var(--accent)",
    locked: !group.members.length,
    commit: (next) => sendGroupCfg(group, next),
    lead,
    tail: total,
    klass: "group-row",
  });
  dropZone(node, (symbolId) =>
    call("/api/groups/member", { name: group.name, symbol: symbolId, join: true })
  );
  return node;
}

// В колонке — сколько стеков этой длины. Не шанс и не доля: сколько написано,
// столько и ляжет. Тянуть слайдер и вводить число — два входа в одно значение.
//
// Пока слайдер тянут, на сервер не ходим: каждое движение мыши перерисовывало бы
// таблицу и роняло захват. Итоги пересчитываются на месте, запись уходит только
// когда кнопку отпустили.
const STACK_SLIDER_MAX = 20; // предел шкалы, числом можно вписать и больше

function chanceColumn(cfg, len, row, commit) {
  const times = cfg.stacks[String(len)];
  const locked = !commit;
  const box = document.createElement("div");
  box.className = "chance" + (locked ? " locked" : "");
  box.dataset.len = String(len);
  box.dataset.stacks = times === undefined ? "0" : String(times);

  const gauge = document.createElement("div");
  gauge.className = "gauge";
  const fill = document.createElement("div");
  fill.className = "gauge-fill";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "gauge-slider";
  slider.min = "0";
  slider.max = String(STACK_SLIDER_MAX);
  slider.step = "1";
  slider.value = String(Math.min(Number(box.dataset.stacks) || 0, STACK_SLIDER_MAX));
  slider.disabled = locked;
  slider.title = locked
    ? "задаётся группой"
    : `сколько стеков длиной ${len} — тяни или впиши число`;
  gauge.append(fill, slider);

  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "numeric";
  input.className = "slot";
  input.placeholder = cfg.mixed ? "≠" : "—";
  input.disabled = locked;
  input.title = locked ? "задаётся группой" : `сколько стеков длиной ${len}`;
  if (times !== undefined && !cfg.mixed) input.value = times;

  const share = document.createElement("span");
  share.className = "chance-share";

  if (!locked) {
    slider.oninput = () => {
      box.dataset.stacks = slider.value;
      input.value = Number(slider.value) ? slider.value : "";
      refreshChances(row);
    };
    slider.onchange = () => commitChances(cfg, row, commit);

    input.onchange = () => {
      // не число — откатываем: стеки это целые штуки, «полстека» не бывает
      const text = String(input.value).trim();
      const value = text === "" ? 0 : Math.round(Number(text));
      if (!Number.isFinite(value) || value < 0) {
        input.value = times === undefined ? "" : times;
        return;
      }
      box.dataset.stacks = String(value);
      slider.value = String(Math.min(value, STACK_SLIDER_MAX));
      refreshChances(row);
      commitChances(cfg, row, commit);
    };
  }

  box.append(gauge, input, share);
  return box;
}

// Под колонкой показываем, во сколько символов обходятся её стеки: 6 стеков по
// 2 это 12 символов. Итог строки меняется вместе с любой колонкой, поэтому
// пересчитываем её целиком.
function refreshChances(row) {
  const cells = [...row.querySelectorAll(".chance")];
  let symbols = 0;
  let stacks = 0;
  cells.forEach((cell) => {
    const times = Number(cell.dataset.stacks) || 0;
    const length = Number(cell.dataset.len) || 0;
    symbols += times * length;
    stacks += times;
    cell.classList.toggle("on", times > 0);
    cell.querySelector(".gauge-fill").style.height =
      `${Math.min((times / STACK_SLIDER_MAX) * 100, 100)}%`;
    cell.querySelector(".slot").classList.toggle("filled", times > 0);
    cell.querySelector(".chance-share").textContent = times ? `${times * length}` : "";
  });

  const live = row.querySelector(".live-total");
  if (live) {
    live.innerHTML = stacks
      ? `<b>${symbols}</b> симв. · ${stacks} стеков · в стеке ${Number((symbols / stacks).toFixed(2))}`
      : "нет в ленте";
  }
}

function commitChances(cfg, row, commit) {
  const stacks = {};
  row.querySelectorAll(".chance").forEach((cell) => {
    const times = Number(cell.dataset.stacks) || 0;
    if (times > 0) stacks[cell.dataset.len] = times;
  });
  commit({ ...cfg, stacks });
}

function renderStrips() {
  const built = state.strips.filter((strip) => strip.length);
  const stats = state.stats || [];
  const parts = [];
  if (built.length) {
    parts.push(`длины лент: ${state.strips.map((strip) => strip.length).join(" · ")}`);
  }
  let broken = 0;
  if (built.length && stats.length) {
    broken = stats.reduce((sum, item) => sum + (item.broken || 0), 0);
    const glued = stats.reduce((sum, item) => sum + (item.glued || 0), 0);
    parts.push(broken ? `⚠ НАРУШЕНИЙ ДИСТАНЦИИ: ${broken}` : "✓ дистанции соблюдены");
    parts.push(glued ? `⚠ СЛИПШИХСЯ СТЕКОВ: ${glued}` : "✓ стеки как заказаны");
    broken += glued;
  }
  const stale = staleReels();
  if (stale.length) {
    parts.push(`⚠ настройки изменились после генерации — пересобери рил${stale.length > 1 ? "ы" : ""} ${stale.join(", ")}`);
  }
  const line = parts.join("  —  ");
  [genStats, $("pattern-stats")].forEach((node) => {
    if (!node) return;
    node.textContent = line;
    node.classList.toggle("bad", broken > 0 || stale.length > 0);
  });

  const patternHint = document.querySelector("#pattern-gen .hint");
  if (patternHint) {
    patternHint.classList.toggle("bad", stale.length > 0);
    patternHint.textContent = stale.length
      ? `⚠ ленты собраны по прежним настройкам — пересобери рил${stale.length > 1 ? "ы" : ""} ${stale.join(", ")}`
      : "эти ленты и крутит «Статистика» — она считает по тому, что лежит в сете";
  }

  renderStripsText();
  // один и тот же вид на двух вкладках: обработчики вешаются на элементы,
  // поэтому обе копии живые — клонировать DOM было бы нельзя
  fillStrips(stripsBox);
  fillStrips($("pattern-strips"));
}

// Ленты лежат в сете с прошлой генерации, а состав показывает то, что выйдет
// сейчас. Расхождение значит «ты правил настройки после Generate» — молчать об
// этом нельзя: симуляция крутит ленты, а не настройки.
function staleReels() {
  const derived = state.derived || [];
  const stale = [];
  for (let reel = 0; reel < state.field.reels; reel++) {
    const want = Object.values(derived[reel] || {}).reduce(
      (sum, entry) => sum + (Number(entry.count) || 0),
      0
    );
    const have = (state.strips[reel] || []).length;
    if (want !== have) stale.push(reel + 1);
  }
  return stale;
}

function fillStrips(box) {
  if (!box) return;
  box.textContent = "";
  for (let reel = 0; reel < state.field.reels; reel++) {
    const strip = state.strips[reel] || [];
    const node = document.createElement("div");
    node.className = "strip";
    const head = document.createElement("h4");
    head.innerHTML = `Рил ${reel + 1} · <span>${strip.length}</span>`;

    const cells = document.createElement("div");
    cells.className = "strip-cells";
    strip.forEach((symbolId, position) => {
      const symbol = state.symbols.find((item) => item.id === symbolId);
      const cell = document.createElement("div");
      cell.className = "strip-cell" + (strip[position - 1] !== symbolId ? " run-start" : "");
      if (symbol?.image) {
        const img = document.createElement("img");
        img.src = `/symimg/${encodeURIComponent(state.active)}/${symbol.image}`;
        img.alt = "";
        cell.appendChild(img);
      }
      const label = document.createElement("span");
      label.textContent = symbolId;
      cell.appendChild(label);
      cells.appendChild(cell);
    });

    node.append(head, seedBox(reel), cells);
    box.appendChild(node);
  }
}

function seedBox(reel) {
  const box = document.createElement("div");
  box.className = "seed-box";

  const label = document.createElement("span");
  label.textContent = "сид";

  const input = document.createElement("input");
  input.type = "number";
  input.min = "0";
  input.value = state.seeds?.[reel] ?? 1;
  input.title = "свой сид этого рила — тот же сид даёт ту же ленту";
  input.onchange = () => generateStrips({ reel, seed: Number(input.value) || 0 });

  const roll = document.createElement("button");
  roll.className = "btn squat";
  roll.textContent = "↺";
  roll.title = `перекатить только рил ${reel + 1}`;
  roll.onclick = () => generateStrips({ reel, reseed: true });

  const stats = state.stats?.[reel];
  const trouble = (stats?.broken || 0) + (stats?.glued || 0);
  const note = document.createElement("span");
  note.className = "seed-note" + (trouble ? " bad" : "");
  if (stats) {
    note.textContent = trouble
      ? `⚠ нарушений ${stats.broken} · склеек ${stats.glued}`
      : "стеки и дистанции в порядке";
  }

  box.append(label, input, roll, note);
  return box;
}

function renderStripsText() {
  const filled = state.strips.filter((strip) => strip.length);
  const text = state.strips.map((strip) => strip.join(" ")).join("\n");
  const file = `sets/${state.active}/strips.txt`;

  [
    [textOut, stripsText, stripsFile],
    [$("pattern-text-out"), $("pattern-strips-text"), $("pattern-strips-file")],
  ].forEach(([box, area, hint]) => {
    if (!box) return;
    box.classList.toggle("hidden", !filled.length);
    if (!filled.length) return;
    area.value = text;
    hint.textContent = file;
  });
}

$("btn-pattern-copy").onclick = async () => {
  const area = $("pattern-strips-text");
  try {
    await navigator.clipboard.writeText(area.value);
  } catch {
    area.select();
    document.execCommand("copy");
  }
  say("ленты скопированы", true);
};

$("btn-copy-strips").onclick = async () => {
  try {
    await navigator.clipboard.writeText(stripsText.value);
  } catch {
    stripsText.select(); // если буфер обмена недоступен — хотя бы выделим
    document.execCommand("copy");
  }
  say("ленты скопированы", true);
};

// --- вкладка СТАТИСТИКА ------------------------------------------------------

let lastSpin = null;

function symbolById(id) {
  return state.symbols.find((item) => item.id === id);
}

function symbolCell(id, className) {
  const cell = document.createElement("div");
  cell.className = className;
  const symbol = symbolById(id);
  if (symbol?.image) {
    const img = document.createElement("img");
    img.src = `/symimg/${encodeURIComponent(state.active)}/${symbol.image}`;
    img.alt = String(id);
    img.title = `ID ${id} · ${symbol.type}`;
    cell.appendChild(img);
  } else {
    cell.textContent = id;
  }
  return cell;
}

function renderStats() {
  renderSlot();
  renderComposition();
  renderTriggers();
  // первый заход на вкладку — сразу показываем один спин, чтобы окно не пустовало
  if (!lastSpin && state.strips.some((strip) => strip.length)) $("btn-spin").onclick();
}

function renderSlot() {
  slotBox.textContent = "";
  slotBox.parentNode.querySelector(".hidden-note")?.remove();
  const { rows, reels, paylines } = state.field;

  // какие клетки участвуют в выигрыше: по каждой линии — её начало нужной длины
  const hits = new Set();
  (lastSpin?.wins || []).forEach((win) => {
    const line = paylines[win.line] || [];
    for (let reel = 0; reel < win.length; reel++) hits.add(`${reel}:${line[reel]}`);
  });

  for (let reel = 0; reel < reels; reel++) {
    const column = document.createElement("div");
    column.className = "slot-reel";
    for (let row = 0; row < rows; row++) {
      const id = lastSpin?.window?.[reel]?.[row];
      if (id === undefined) {
        const blank = document.createElement("div");
        blank.className = "slot-cell";
        column.appendChild(blank);
        continue;
      }
      // клетка показывает то, во что превратилась; откуда пришла — в маркере
      const from = lastSpin?.hidden_cells?.[reel]?.[row] || 0;
      const cell = symbolCell(
        id,
        "slot-cell" + (hits.has(`${reel}:${row}`) ? " hit" : "") + (from ? " from-hidden" : "")
      );
      if (from) {
        const mark = document.createElement("span");
        mark.className = "hidden-mark";
        mark.textContent = from;
        mark.title = `был скрытым ID ${from}`;
        cell.appendChild(mark);
      }
      column.appendChild(cell);
    }
    slotBox.appendChild(column);
  }

  spinHiddenNote();

  winList.textContent = "";
  (lastSpin?.wins || []).forEach((win) => {
    const chip = document.createElement("div");
    chip.className = "win-chip" + (win.with_hidden ? " with-hidden" : "");
    chip.innerHTML =
      `L${String(win.line + 1).padStart(2, "0")} · ID ${win.symbol} ×${win.length} · ` +
      `<b>${trim(win.amount)}</b>` +
      (win.with_hidden ? ' <i class="tag">через скрытый</i>' : "");
    winList.appendChild(chip);
  });
}

// Строка «что во что превратилось» под окном: без неё маркер в клетке читается,
// только если помнишь номера скрытых символов наизусть.
function spinHiddenNote() {
  const map = lastSpin?.hidden_map || {};
  const pairs = Object.keys(map);
  if (!pairs.length) return;

  const note = document.createElement("div");
  note.className = "hidden-note";
  pairs.forEach((from) => {
    const chip = document.createElement("span");
    chip.className = "hidden-pair";
    chip.append(
      symbolCell(Number(from), "who-img"),
      document.createTextNode("→"),
      symbolCell(map[from], "who-img")
    );
    chip.title = `скрытый ID ${from} стал ID ${map[from]}`;
    note.appendChild(chip);
  });
  slotBox.after(note);
}

function renderComposition() {
  const counts = {};
  let total = 0;
  state.strips.forEach((strip) => {
    strip.forEach((id) => {
      counts[id] = (counts[id] || 0) + 1;
      total += 1;
    });
  });

  comp.textContent = "";
  if (!total) {
    comp.innerHTML = '<div class="hint">лент ещё нет — сгенерируй их на вкладке «Ленты»</div>';
    return;
  }

  const table = document.createElement("table");
  const head = document.createElement("tr");
  head.innerHTML = "<th>символ</th><th>всего</th><th>%</th>" +
    state.strips.map((_, reel) => `<th>рил ${reel + 1}</th>`).join("");
  table.appendChild(head);

  state.symbols.forEach((symbol) => {
    const count = counts[symbol.id] || 0;
    const row = document.createElement("tr");

    const who = document.createElement("td");
    const box = document.createElement("div");
    box.className = "who-cell";
    box.append(symbolCell(symbol.id, "who-img"), document.createTextNode(`ID ${symbol.id}`));
    who.appendChild(box);

    const totalCell = document.createElement("td");
    totalCell.textContent = count;
    const shareCell = document.createElement("td");
    shareCell.className = "share";
    shareCell.textContent = `${Number(((count / total) * 100).toFixed(1))}%`;

    row.append(who, totalCell, shareCell);
    state.strips.forEach((strip) => {
      const cell = document.createElement("td");
      cell.textContent = strip.filter((id) => id === symbol.id).length || "—";
      row.appendChild(cell);
    });
    table.appendChild(row);
  });

  const sum = document.createElement("tr");
  sum.className = "sum";
  sum.innerHTML = `<td>всего</td><td>${total}</td><td>100%</td>` +
    state.strips.map((strip) => `<td>${strip.length}</td>`).join("");
  table.appendChild(sum);

  comp.appendChild(table);
}

$("btn-spin").onclick = async () => {
  try {
    lastSpin = await api("/api/play/spin", {});
    spinResult.textContent = lastSpin.total
      ? `выигрыш ${trim(lastSpin.total)} · ${trim(lastSpin.total / state.bet)}×ставки`
      : "мимо";
    renderSlot();
  } catch (error) {
    say(error.message);
  }
};

$("btn-sim").onclick = async () => {
  const button = $("btn-sim");
  const rounds = Math.max(1, Number(roundsInput.value) || 0);
  button.disabled = true;
  rtpBox.innerHTML = "считаю…";
  try {
    renderSimulation(await api("/api/play/simulate", { rounds }));
  } catch (error) {
    rtpBox.innerHTML = "RTP — <b>?</b>";
    say(error.message);
  } finally {
    button.disabled = false;
  }
};

function renderSimulation(data) {
  rtpBox.innerHTML =
    `RTP <b>${data.rtp.toFixed(2)}%</b><small>${data.rounds.toLocaleString("ru")} раундов ` +
    `по ставке ${trim(data.bet)}</small>`;
  $("hit-rate").innerHTML =
    `Hit rate <b>${data.hit_rate.toFixed(2)}%</b>` +
    `<small>платит каждый ${(100 / (data.hit_rate || 1)).toFixed(1)}-й спин</small>`;
  const staked = data.bet * data.rounds;
  $("wild-part").innerHTML = data.wild_win
    ? `RTP через вайлды <b>${((data.wild_win / staked) * 100).toFixed(2)}</b>` +
      `<small>${((data.wild_win / data.total_win) * 100).toFixed(1)}% всех выплат прошло через замещение</small>`
    : "";
  $("hidden-part").innerHTML = data.hidden_win
    ? `RTP через скрытые <b>${((data.hidden_win / staked) * 100).toFixed(2)}</b>` +
      `<small>${((data.hidden_win / data.total_win) * 100).toFixed(1)}% всех выплат прошло через превращение</small>`
    : "";
  $("win-avg").innerHTML =
    `Средний вин <b>${trim(data.win_avg)}</b>` +
    `<small>${(data.win_avg / data.bet).toFixed(2)}×ставки за выигрышный спин</small>`;

  $("trig-bonus").innerHTML = triggerText("Бонус", data.triggers.bonus);
  $("trig-fs").innerHTML = triggerText("Фриспины", data.triggers.fs);
  $("ant-bonus").innerHTML = antText("Бонус: антисипейшн", data.triggers.bonus);
  $("ant-fs").innerHTML = antText("Фриспины: антисипейшн", data.triggers.fs);

  dists.textContent = "";
  dists.append(
    distBlock("Линий на выигрышном спине", data.lines_hist, data.lines_avg, data.paying_spins, "линий"),
    distBlock("Разных символов на поле", data.diversity_hist, data.diversity_avg, data.rounds, "видов")
  );
  dists.append(...screenBlocks(data));

  renderLengths(data);
  renderHiddenRoll(data);
  renderValues(data);
  renderHits(data);
}

// Тепловая заливка: чем крупнее доля, тем ярче клетка — пики видно сразу.
function heat(cell, share, top, hue) {
  const ratio = top ? Math.min(share / top, 1) : 0;
  if (!ratio) return;
  cell.style.background = `hsla(${hue}, 85%, 60%, ${(0.08 + 0.5 * ratio).toFixed(3)})`;
  cell.style.color = ratio > 0.45 ? "var(--text)" : "";
  cell.style.fontWeight = ratio > 0.25 ? "600" : "";
}

function renderValues(data) {
  valuesBox.textContent = "";
  const rows = data.win_values || [];
  if (!rows.length) return;

  const staked = data.bet * data.rounds;
  const box = document.createElement("div");
  box.className = "dist wide";
  const head = document.createElement("h4");
  head.textContent = "Выплата за выигрышный спин";
  const avg = document.createElement("div");
  avg.className = "avg";
  avg.textContent =
    `в среднем ${trim(data.win_avg)} = ${(data.win_avg / data.bet).toFixed(2)}×ставки · ` +
    `в ставках считаем от общей ставки ${trim(data.bet)}`;
  box.append(head, avg);

  const topShare = Math.max(...rows.map(([, , count]) => count), 1);
  rows.forEach(([from, to, count, amount]) => {
    const row = document.createElement("div");
    row.className = "bar-row wide-row";

    const label = document.createElement("span");
    label.className = "band";
    label.textContent = to === null ? `${from}×+` : `${from}–${to}×`;

    const track = document.createElement("div");
    track.className = "bar-track";
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.width = `${(count / topShare) * 100}%`;
    track.appendChild(bar);

    const spins = document.createElement("b");
    spins.textContent = `${count.toLocaleString("ru")} · ${((count / data.paying_spins) * 100).toFixed(1)}%`;

    const part = document.createElement("b");
    part.className = "rtp-part";
    part.textContent = `${((amount / staked) * 100).toFixed(2)} п.п.`;

    const share = document.createElement("b");
    share.className = "pay-share";
    share.textContent = data.total_win ? `${((amount / data.total_win) * 100).toFixed(1)}% выплат` : "—";

    row.append(label, track, spins, share, part);
    box.appendChild(row);
  });

  valuesBox.appendChild(box);
}

// Длина комбинации в одной карточке: и как часто выпадает, и сколько стоит.
// Врозь это читалось плохо — тройки выпадают вдесятеро чаще пятёрок и всё равно
// могут отдавать меньше денег, а чтобы это увидеть, приходилось сличать два
// блока глазами.
//
// Считаем из symbol_hits: там у каждой строки есть и длина, и выплата, так что
// отдельная цифра с сервера была бы копией уже приехавшей.
function renderLengths(data) {
  lengthsBox.textContent = "";
  const rows = data.symbol_hits || [];
  if (!rows.length) return;

  const byLength = new Map();
  rows.forEach(([, length, count, amount]) => {
    const slot = byLength.get(length) || { count: 0, amount: 0 };
    slot.count += count;
    slot.amount += amount;
    byLength.set(length, slot);
  });

  const lengths = [...byLength.keys()].sort((a, b) => a - b).filter((len) => byLength.get(len).count);
  if (!lengths.length) return;

  const staked = data.bet * data.rounds;
  const combos = lengths.reduce((sum, len) => sum + byLength.get(len).count, 0);
  const box = document.createElement("div");
  box.className = "dist wide";
  const head = document.createElement("h4");
  head.textContent = "Выигрышные комбинации по длине";
  const avg = document.createElement("div");
  avg.className = "avg";
  avg.textContent =
    `в среднем ${data.length_avg.toFixed(2)} символов · ` +
    `${combos.toLocaleString("ru")} комбинаций · ` +
    `сумма по длинам складывается в общий RTP ${data.rtp.toFixed(2)}%`;
  box.append(head, avg);

  // Две шкалы в строке: частота и деньги. Одной полосы мало — вопрос карточки
  // именно в расхождении между ними, а его видно только когда обе рядом.
  const topHit = Math.max(...lengths.map((len) => byLength.get(len).count), 1);
  const topPay = Math.max(...lengths.map((len) => byLength.get(len).amount), 1);

  const legend = document.createElement("div");
  legend.className = "bar-row wide-row legend-row";
  ["", "как часто выпадает", "", "сколько платит", "", ""].forEach((text) => {
    const cell = document.createElement("span");
    cell.textContent = text;
    legend.appendChild(cell);
  });
  box.appendChild(legend);

  lengths.forEach((length) => {
    const { count, amount } = byLength.get(length);
    const row = document.createElement("div");
    row.className = "bar-row wide-row";

    const label = document.createElement("span");
    label.className = "band";
    label.textContent = `×${length}`;

    const hitTrack = document.createElement("div");
    hitTrack.className = "bar-track";
    const hitBar = document.createElement("div");
    hitBar.className = "bar";
    hitBar.style.width = `${(count / topHit) * 100}%`;
    hitTrack.appendChild(hitBar);

    const hits = document.createElement("b");
    hits.innerHTML =
      `${count.toLocaleString("ru")}` +
      (combos ? ` · <span class="hit-share">${((count / combos) * 100).toFixed(1)}%</span>` : "");

    const payTrack = document.createElement("div");
    payTrack.className = "bar-track";
    const payBar = document.createElement("div");
    payBar.className = "bar hot";
    payBar.style.width = `${(amount / topPay) * 100}%`;
    payTrack.appendChild(payBar);

    const share = document.createElement("b");
    share.className = "pay-share";
    share.textContent = data.total_win
      ? `${((amount / data.total_win) * 100).toFixed(1)}%`
      : "—";

    const part = document.createElement("b");
    part.className = "rtp-part";
    part.textContent = `${((amount / staked) * 100).toFixed(2)} п.п.`;

    row.append(label, hitTrack, hits, payTrack, share, part);
    box.appendChild(row);
  });

  lengthsBox.appendChild(box);
}

// Роялсы (тип low) против всего остального. Считается по экрану после
// превращения скрытых: на стопе hidden уже стал другим символом, поэтому клетка
// из него идёт в ту группу, в какую попал её символ.
//
// Роялсы и картинки дополняют друг друга до полного экрана, поэтому распределение
// нужно одно: картинки это остаток.
function screenBlocks(data) {
  if (!data.screen) return [];
  const screen = data.screen;
  const pictures = data.picture_avg;
  const dry = (data.wild_hist || []).find(([count]) => count === 0);
  const dryShare = dry ? (dry[1] / data.rounds) * 100 : 0;

  return [
    distBlock(
      "Роялсов на экране",
      data.royal_hist,
      data.royal_avg,
      data.rounds,
      `из ${screen}`,
      `картинок ${pictures.toFixed(2)} — ${Math.round((pictures / screen) * 100)}% экрана`
    ),
    distBlock(
      "Вайлдов на спин",
      data.wild_hist,
      data.wild_avg,
      data.rounds,
      "штук",
      `без вайлда ${dryShare.toFixed(1)}% спинов`
    ),
    distBlock(
      "Рилов с вайлдом",
      data.wild_reels_hist,
      data.wild_reels_avg,
      data.rounds,
      "рилов",
      "считаем барабаны, где лежит хотя бы один"
    ),
  ];
}

function triggerText(title, trigger) {
  if (!trigger.symbol || !trigger.min) return `${title}<small>не настроен</small>`;
  if (!trigger.hits) {
    return `${title} <b>—</b><small>ни разу за симуляцию (ID ${trigger.symbol} ×${trigger.min})</small>`;
  }
  return (
    `${title} <b>1 / ${Math.round(trigger.one_in).toLocaleString("ru")}</b>` +
    `<small>${trigger.rate.toFixed(3)}% спинов · ID ${trigger.symbol} от ${trigger.min} на поле</small>`
  );
}

function antText(title, trigger) {
  const ant = trigger.ant || {};
  if (!trigger.symbol || !ant.reels?.length) return "";
  const where = `${ant.min} ${ant.each ? "на каждом из рилов" : "суммарно на рилах"} ${ant.reels.join(", ")}`;
  if (!ant.hits) return `${title} <b>—</b><small>ни разу · ${where}</small>`;
  return (
    `${title} <b>1 / ${Math.round(ant.one_in).toLocaleString("ru")}</b>` +
    `<small>${ant.rate.toFixed(2)}% спинов · ${where}</small>`
  );
}

function distBlock(title, rows, average, base, unit, note) {
  const node = document.createElement("div");
  node.className = "dist";
  const head = document.createElement("h4");
  head.textContent = title;
  const avg = document.createElement("div");
  avg.className = "avg";
  avg.textContent = `в среднем ${average.toFixed(2)} ${unit}` + (note ? ` · ${note}` : "");
  node.append(head, avg);

  const total = base || rows.reduce((sum, [, count]) => sum + count, 0);
  const top = Math.max(...rows.map(([, count]) => count), 1);
  rows.forEach(([key, count]) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const label = document.createElement("span");
    label.textContent = key;
    const track = document.createElement("div");
    track.className = "bar-track";
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.width = `${(count / top) * 100}%`;
    track.appendChild(bar);
    const value = document.createElement("b");
    value.textContent = `${count.toLocaleString("ru")} · ${((count / total) * 100).toFixed(1)}%`;
    row.append(label, track, value);
    node.appendChild(row);
  });
  return node;
}

// Заданный вес против фактической доли. Расхождение на большом числе раундов —
// первый признак, что с механикой что-то не так.
function renderHiddenRoll(data) {
  hiddenRoll.textContent = "";
  const blocks = data.hidden || [];
  if (!blocks.length) return;

  const head = document.createElement("h4");
  head.textContent = "Разрешение скрытых — во что превращались";
  hiddenRoll.appendChild(head);

  blocks.forEach((block) => {
    const box = document.createElement("div");
    box.className = "roll-box";

    const title = document.createElement("div");
    title.className = "roll-head";
    title.append(symbolCell(block.symbol, "who-img"));
    const text = document.createElement("div");
    text.innerHTML =
      `<b>ID ${block.symbol}</b>` +
      `<small>${block.rolls.toLocaleString("ru")} бросков · на экране ` +
      `${block.on_screen.toLocaleString("ru")} спинов (${block.on_screen_rate.toFixed(1)}%)</small>`;
    title.appendChild(text);
    box.appendChild(title);

    const table = document.createElement("table");
    table.innerHTML =
      "<tr><th>во что</th><th>вес</th><th>задано</th><th>выпало</th><th>фактически</th></tr>";
    block.targets.forEach((target) => {
      const row = document.createElement("tr");
      const who = document.createElement("td");
      const cell = document.createElement("div");
      cell.className = "who-cell";
      cell.append(
        symbolCell(target.symbol, "who-img"),
        document.createTextNode(`ID ${target.symbol}`)
      );
      who.appendChild(cell);

      const drift = Math.abs(target.got - target.want);
      const got = document.createElement("td");
      got.className = "share" + (drift > 2 ? " drift" : "");
      got.textContent = `${target.got.toFixed(2)}%`;

      row.append(who);
      [trim(target.weight), `${target.want.toFixed(2)}%`, target.hits.toLocaleString("ru")].forEach(
        (value) => {
          const td = document.createElement("td");
          td.textContent = value;
          row.appendChild(td);
        }
      );
      row.appendChild(got);
      table.appendChild(row);
    });

    box.appendChild(table);
    hiddenRoll.appendChild(box);
  });
}

function renderHits(data) {
  hitsBox.textContent = "";
  const staked = data.bet * data.rounds;

  const combos = data.symbol_hits.reduce((sum, row) => sum + row[2], 0);
  const topPay = Math.max(...data.symbol_hits.map((row) => row[3]), 1);
  const topHit = Math.max(...data.symbol_hits.map((row) => row[2]), 1);

  const table = document.createElement("table");
  const head = document.createElement("tr");
  // колонка скрытых нужна, только если скрытые в сете вообще есть
  const anyHidden = (data.hidden || []).length > 0;
  head.innerHTML =
    "<th>символ</th><th>в линии</th><th>комбинаций</th><th>доля хитов</th>" +
    "<th>раз на 1000 спинов</th><th>из них с вайлдом</th>" +
    (anyHidden ? "<th>из них со скрытым</th>" : "") +
    "<th>выплачено</th><th>доля выплат</th><th>RTP, п.п.</th>";
  table.appendChild(head);

  let previous = null;
  data.symbol_hits.forEach(([symbolId, length, count, amount, wildCount, , hiddenCount]) => {
    const row = document.createElement("tr");
    if (symbolId !== previous) row.className = "group-start";

    const sym = document.createElement("td");
    sym.className = "sym";
    if (symbolId !== previous) {
      const box = document.createElement("div");
      box.className = "who-cell";
      const symbol = symbolById(symbolId);
      box.append(
        symbolCell(symbolId, "who-img"),
        document.createTextNode(`ID ${symbolId} · ${symbol?.type || ""}`)
      );
      sym.appendChild(box);
    }
    previous = symbolId;

    row.appendChild(sym);

    const hitShare = combos ? (count / combos) * 100 : 0;
    const payShare = data.total_win ? (amount / data.total_win) * 100 : 0;

    const plain = [
      `×${length}`,
      count.toLocaleString("ru"),
      null, // доля хитов — с заливкой
      ((count / data.rounds) * 1000).toFixed(1),
      count ? `${wildCount.toLocaleString("ru")} · ${((wildCount / count) * 100).toFixed(0)}%` : "—",
      ...(anyHidden
        ? [count ? `${hiddenCount.toLocaleString("ru")} · ${((hiddenCount / count) * 100).toFixed(0)}%` : "—"]
        : []),
      Math.round(amount).toLocaleString("ru"),
      null, // доля выплат — с заливкой
    ];
    plain.forEach((text, index) => {
      const cell = document.createElement("td");
      if (text === null) {
        const isHits = index === 2;
        const share = isHits ? hitShare : payShare;
        cell.textContent = count ? `${share.toFixed(1)}%` : "—";
        heat(cell, count ? (isHits ? count : amount) : 0, isHits ? topHit : topPay, isHits ? 215 : 28);
      } else {
        cell.textContent = text;
      }
      if (!count) cell.classList.add("zero");
      row.appendChild(cell);
    });

    const part = document.createElement("td");
    part.className = "rtp-part" + (count ? "" : " zero");
    part.textContent = staked ? `${((amount / staked) * 100).toFixed(2)}` : "—";
    row.appendChild(part);

    table.appendChild(row);
  });

  hitsBox.appendChild(table);
  renderHitsChart(data, staked);
}

// График: те же комбинации, но отсортированные по вкладу в RTP — пики сверху.
function renderHitsChart(data, staked) {
  hitsChart.textContent = "";
  const rows = data.symbol_hits.filter((row) => row[2]).sort((a, b) => b[3] - a[3]);
  if (!rows.length) return;

  const head = document.createElement("h4");
  head.textContent = "Что съедает RTP — комбинации по вкладу";
  const top = rows[0][3];
  hitsChart.appendChild(head);

  rows.forEach(([symbolId, length, count, amount]) => {
    const row = document.createElement("div");
    row.className = "chart-row";

    const label = document.createElement("div");
    label.className = "chart-label";
    label.append(symbolCell(symbolId, "who-img"), document.createTextNode(`ID ${symbolId} ×${length}`));

    const track = document.createElement("div");
    track.className = "bar-track";
    const bar = document.createElement("div");
    bar.className = "bar hot";
    bar.style.width = `${(amount / top) * 100}%`;
    track.appendChild(bar);

    const value = document.createElement("b");
    value.textContent =
      `${((amount / staked) * 100).toFixed(2)} п.п. · ` +
      `${((amount / data.total_win) * 100).toFixed(1)}% выплат · ${count.toLocaleString("ru")} раз`;

    row.append(label, track, value);
    hitsChart.appendChild(row);
  });
}

// --- триггеры бонуса и фриспинов ---------------------------------------------

function renderTriggers() {
  const { bonus, fs } = state.triggers || { bonus: {}, fs: {} };
  fillSymbolSelect(bonusSymbol, bonus.symbol);
  fillSymbolSelect(fsSymbol, fs.symbol);
  if (document.activeElement !== bonusMin) bonusMin.value = bonus.min ?? 6;
  if (document.activeElement !== fsMin) fsMin.value = fs.min ?? 3;
  fillAnt("bonus", bonus);
  fillAnt("fs", fs);
}

function fillAnt(key, trigger) {
  const fields = antFields[key];
  if (document.activeElement !== fields.min) fields.min.value = trigger.ant_min ?? 1;
  if (document.activeElement !== fields.reels) {
    fields.reels.value = (trigger.ant_reels || []).join(",");
  }
  fields.each.value = trigger.ant_each ? "1" : "";
}

function antValues(key) {
  const fields = antFields[key];
  return {
    ant_min: Number(fields.min.value) || 1,
    ant_each: !!fields.each.value,
    ant_reels: fields.reels.value
      .split(/[^0-9]+/)
      .map(Number)
      .filter(Boolean),
  };
}

function fillSymbolSelect(select, current) {
  select.textContent = "";
  select.appendChild(option("0", "— символ не выбран —", String(current ?? 0)));
  state.symbols.forEach((symbol) =>
    select.appendChild(
      option(String(symbol.id), `ID ${symbol.id} · ${symbol.type}`, String(current ?? 0))
    )
  );
}

function sendTriggers() {
  call("/api/set/triggers", {
    bonus: { symbol: Number(bonusSymbol.value), min: Number(bonusMin.value) || 1, ...antValues("bonus") },
    fs: { symbol: Number(fsSymbol.value), min: Number(fsMin.value) || 1, ...antValues("fs") },
  });
}

[bonusSymbol, bonusMin, fsSymbol, fsMin]
  .concat(Object.values(antFields).flatMap((fields) => Object.values(fields)))
  .forEach((node) => (node.onchange = sendTriggers));

// --- drag-n-drop -------------------------------------------------------------

function dropTarget(node, onFiles) {
  node.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.stopPropagation();
    node.classList.add("drop");
  });
  node.addEventListener("dragleave", () => node.classList.remove("drop"));
  node.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    node.classList.remove("drop");
    const files = [...(event.dataTransfer?.files || [])];
    if (files.length) onFiles(files);
  });
}

function pick(onFile) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = () => input.files[0] && onFile(input.files[0]);
  input.click();
}

async function upload(file, symbolId) {
  if (!file) return;
  try {
    state = await api("/api/symbols/image", {
      id: symbolId ?? "new",
      filename: file.name,
      data: await readDataUrl(file),
    });
    render();
  } catch (error) {
    say(`${file.name}: ${error.message}`);
  }
}

async function uploadMany(files) {
  for (const file of files) await upload(file, null); // по очереди — id идут подряд
}

function readDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("файл не читается"));
    reader.readAsDataURL(file);
  });
}

// --- вкладки -----------------------------------------------------------------

function openTab(name) {
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (!tab) return;
  document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
  tab.classList.add("active");
  document.querySelectorAll(".page").forEach((page) => page.classList.add("hidden"));
  $(`tab-${name}`).classList.remove("hidden");
  location.hash = name; // вкладка переживает перезагрузку страницы
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => openTab(tab.dataset.tab);
});

openTab(location.hash.slice(1) || "symbols");

// --- сеты --------------------------------------------------------------------

setSelect.onchange = () => call("/api/sets/select", { name: setSelect.value });

$("btn-set-new").onclick = () => {
  const name = prompt("Имя нового сета:", "");
  if (name) call("/api/sets/create", { name });
};

$("btn-set-save").onclick = async () => {
  await call("/api/sets/save", {});
  say(`сет «${state.active}» сохранён`, true);
};

$("btn-set-copy").onclick = async () => {
  const name = prompt("Сохранить как:", `${state.active} копия`);
  if (!name) return;
  const exists = state.sets.includes(name.trim());
  if (exists && !confirm(`Сет «${name.trim()}» уже есть. Перезаписать его целиком?`)) return;
  await call("/api/sets/save-as", { name, overwrite: exists });
  say(`сохранено в «${state.active}»`, true);
};

$("btn-set-rename").onclick = () => {
  const name = prompt("Новое имя сета:", state.active);
  if (name && name !== state.active) call("/api/sets/rename", { old: state.active, name });
};

$("btn-set-delete").onclick = async () => {
  const name = state.active;
  if (!confirm(`Убрать сет «${name}» в корзину sets/.trash? Вернуть можно кнопкой «Из корзины».`)) {
    return;
  }
  await call("/api/sets/delete", { name });
  say(`«${name}» в корзине — sets/.trash/${name}`, true);
};

$("btn-set-export").onclick = async () => {
  try {
    const data = await api("/api/sets/export", { name: state.active });
    // отдаём файл браузеру — пусть кладёт куда удобно
    const blob = new Blob([JSON.stringify(data.bundle)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${data.name}.rgset.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    say(`сет выгружен · копия лежит в ${data.file}`, true);
  } catch (error) {
    say(error.message);
  }
};

$("btn-set-import").onclick = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const bundle = JSON.parse(await file.text());
      await call("/api/sets/import", { bundle });
      say(`сет загружен как «${state.active}»`, true);
    } catch (error) {
      say(`${file.name}: ${error.message}`);
    }
  };
  input.click();
};

$("btn-set-restore").onclick = () => {
  const names = state.trash || [];
  if (!names.length) return;
  const name = prompt(`Что вернуть из корзины?\n\n${names.join("\n")}`, names[names.length - 1]);
  if (name) call("/api/sets/restore", { name });
};

// --- ставка, размер поля, линии ----------------------------------------------

betInput.onchange = () => call("/api/set/bet", { bet: betInput.value });

// Уменьшение поля подрезает линии под новый размер — предупреждаем заранее.
function sendSize() {
  const rows = Number(rowsInput.value);
  const reels = Number(reelsInput.value);
  const shrinks = rows < state.field.rows || reels < state.field.reels;
  if (shrinks && state.field.paylines.length) {
    const ok = confirm(
      `Поле уменьшается до ${rows}×${reels}. Линии подрежутся под новый размер — вернуть их можно кнопкой «20 стандартных». Продолжить?`
    );
    if (!ok) {
      renderField();
      return;
    }
  }
  call("/api/field/size", { rows, reels });
}

rowsInput.onchange = sendSize;
reelsInput.onchange = sendSize;

$("btn-add").onclick = () => call("/api/symbols/add", { type: "low" });

$("btn-line-add").onclick = () => {
  const lines = state.field.paylines.map((item) => [...item]);
  lines.push(new Array(state.field.reels).fill(0));
  call("/api/field/lines", { lines });
};

$("btn-lines-reset").onclick = () => {
  if (confirm("Заменить текущие линии на 20 стандартных?")) call("/api/field/lines/reset", {});
};

$("btn-lines-paste").onclick = () => {
  pasteText.value = "";
  pasteModal.classList.remove("hidden");
  pasteText.focus();
};

$("btn-paste-cancel").onclick = () => pasteModal.classList.add("hidden");

$("btn-paste-ok").onclick = async () => {
  pasteModal.classList.add("hidden");
  await call("/api/field/lines/paste", { text: pasteText.value });
};

// --- пересечение: добавление правила -----------------------------------------

$("btn-gap-add").onclick = () => {
  // заготовка ровно по классике: два спецсимвола нельзя ставить ближе двух low
  sendGaps([...(state.gaps || []), { a: "type:special", b: "type:special", min: 2, filler: "low" }]);
};

// --- ленты: копирование, очистка, генерация ----------------------------------

$("btn-group-new").onclick = () => {
  const name = prompt("Имя группы:", "роялсы");
  if (name) call("/api/groups/create", { name });
};

$("btn-reel-copy").onclick = () => {
  if (confirm(`Разложить настройки рила ${currentReel + 1} на все рилы?`)) {
    call("/api/reels/copy", { reel: currentReel });
  }
};

$("btn-reel-clear").onclick = () => {
  if (masterOn()) {
    if (confirm("Убрать все символы из мастер-рила?")) call("/api/master/clear", {});
    return;
  }
  if (confirm(`Убрать все стеки с рила ${currentReel + 1}?`)) {
    call("/api/reels/clear", { reel: currentReel });
  }
};

$("btn-reseed").onclick = () => generateStrips({ reseed: true });
$("btn-generate").onclick = () => generateStrips();

// те же кнопки на вкладке «Паттерн»: настроил множители — сгенерировал, не уходя
$("btn-pattern-generate").onclick = () => generateStrips();
$("btn-pattern-reseed").onclick = () => generateStrips({ reseed: true });

async function generateStrips(payload = {}) {
  const before = (state.strips || []).map((strip) => strip.join(" ")).join("|");
  try {
    const data = await api("/api/reels/generate", payload);
    state = data;
    render();
    warnBroken();

    // Генерация детерминирована: тот же сид даёт ту же ленту. Промолчать здесь
    // значит выглядеть сломанной кнопкой — именно так это и читалось.
    const after = state.strips.map((strip) => strip.join(" ")).join("|");
    const lengths = state.strips.map((strip) => strip.length).join(" · ");
    if (after === before) {
      say(`ленты те же: сиды не менялись, а при том же сиде раскладка повторяется — нажми «↺ Новые сиды всем» (${lengths})`, true);
    } else {
      say(`ленты собраны: ${lengths}`, true);
    }
  } catch (error) {
    say(error.message);
  }
}

// Правила и склейки — про это нельзя молчать мелким шрифтом.
function warnBroken() {
  const stats = state.stats || [];
  const broken = stats
    .map((item, reel) => ({ reel: reel + 1, count: item.broken || 0 }))
    .filter((item) => item.count);
  const glued = stats
    .map((item, reel) => ({ reel: reel + 1, count: item.glued || 0 }))
    .filter((item) => item.count);

  if (broken.length) {
    const where = broken.map((item) => `рил ${item.reel}: ${item.count}`).join(", ");
    say(`Правила пересечения не сошлись — ${where}. Не хватает прокладок: добавь low или ослабь правило.`);
  }
  if (glued.length) {
    const where = glued.map((item) => `рил ${item.reel}: ${item.count}`).join(", ");
    say(`Стеки слиплись — ${where}. Столько одинаковых символов не развести: уменьши их количество или добавь других.`);
  }
}

// --- старт -------------------------------------------------------------------

// файл, брошенный мимо карточек, не должен открываться в браузере
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

call("/api/symbols/list", {});
checkEnv();

