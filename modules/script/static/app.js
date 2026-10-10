"use strict";

var tg = window.Telegram && window.Telegram.WebApp;

var SVG_DOWN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
var SVG_LEFT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg>';
var SVG_RIGHT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
var SVG_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
var PM = '<span class="pm" aria-hidden="true"><svg viewBox="0 0 12 12"><path d="M6 1.5v9M1.5 6h9"/></svg></span>';
var $ = function (selector) { return document.querySelector(selector); };
var esc = function (value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
  });
};
var ic = function (name, cls) {
  return '<svg class="ic' + (cls ? " " + cls : "") + '" aria-hidden="true"><use href="#i-' + esc(name) + '"/></svg>';
};
var hap = function () {
  try {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
  } catch (_) {}
};

/* Горизонтальная лента с кнопками ‹ › (на ПК ленту нельзя пролистать пальцем). */

function hstrip(key, inner, cls) {
  return '<div class="hs' + (cls ? " " + cls : "") + '"><button type="button" class="hs-btn l" data-hs="-1" aria-label="Прокрутить влево">' + SVG_LEFT +
    '</button><div class="hs-track" data-k="' + esc(key) + '">' + inner + '</div><button type="button" class="hs-btn r" data-hs="1" aria-label="Прокрутить вправо">' +
    SVG_RIGHT + "</button></div>";
}

function updateStrips(root) {
  (root || document).querySelectorAll(".hs").forEach(function (box) {
    var track = box.querySelector(".hs-track");
    if (!track) return;
    var max = track.scrollWidth - track.clientWidth;
    box.classList.toggle("can-l", track.scrollLeft > 2);
    box.classList.toggle("can-r", track.scrollLeft < max - 2);
  });
}

function saveStrips(root) {
  var saved = {};
  (root || document).querySelectorAll(".hs-track[data-k]").forEach(function (track) { saved[track.dataset.k] = track.scrollLeft; });
  return saved;
}

function restoreStrips(saved, root) {
  (root || document).querySelectorAll(".hs-track[data-k]").forEach(function (track) {
    var value = saved[track.dataset.k];
    if (value) { track.style.scrollBehavior = "auto"; track.scrollLeft = value; track.style.scrollBehavior = ""; }
    else {
      var active = track.querySelector(".on");
      if (active && active.offsetLeft + active.offsetWidth > track.clientWidth) {
        track.style.scrollBehavior = "auto";
        track.scrollLeft = active.offsetLeft - 16;
        track.style.scrollBehavior = "";
      }
    }
  });
  updateStrips(root);
}

/* Кнопка выбора из списка (страна, город, ниша): стрелка по центру и поворачивается при открытии. */

function normalizeSearch(text) {
  return String(text || "").toLowerCase().replace(/ё/g, "е").trim();
}

function toast(message) {
  var node = $("#toast");
  node.textContent = String(message || "");
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(function () { node.classList.remove("show"); }, Math.max(3200, String(message || "").length * 55));
}

function api(path, options) {
  options = options || {};
  var headers = Object.assign({}, options.headers || {}, {
    "X-Init-Data": tg && tg.initData ? tg.initData : ""
  });
  if (options.body) headers["Content-Type"] = "application/json";
  return fetch((window.CC_BASE || "") + path, Object.assign({}, options, { headers: headers }))
    .catch(function () {
      throw new Error("Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.");
    })
    .then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var detail = data.detail;
          var text = detail;
          if (detail && typeof detail === "object" && !Array.isArray(detail)) text = detail.message;
          if (Array.isArray(detail)) text = "Проверьте введённые данные.";
          var error = new Error(text || ("Ошибка сервера: " + response.status));
          error.status = response.status;
          error.detail = detail;
          throw error;
        }
        return data;
      });
    });
}

function openLink(url) {
  if (/^\/#/.test(url) || /startapp=join/.test(url)) { if (window.ccGo) window.ccGo("join"); return; }
  try {
    if (tg && /^https:\/\/t\.me\//.test(url)) return tg.openTelegramLink(url);
    if (tg && /^https?:/.test(url)) return tg.openLink(url);
  } catch (_) {}
  window.open(url, "_blank", "noopener");
}

function copyText(text) {
  var done = function () { toast("Скопировано"); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); });
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  var area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try { document.execCommand("copy"); toast("Скопировано"); } catch (_) { toast("Выделите текст и скопируйте вручную."); }
  document.body.removeChild(area);
}

function countUp(element, value) {
  var start = performance.now();
  (function frame(now) {
    var progress = Math.min(1, (now - start) / 700);
    element.textContent = Math.round(value * (1 - Math.pow(1 - progress, 3)));
    if (progress < 1) requestAnimationFrame(frame);
  })(start);
}

function openSheet(html) {
  S.sheetSeq = (S.sheetSeq || 0) + 1;
  var sheet = $("#sheet");
  sheet.innerHTML = '<div class="sheet">' + html + "</div>";
  sheet.classList.add("show");
  document.body.style.overflow = "hidden";
  restoreStrips({}, sheet);
}

function setSheetBody(html) {
  var inner = $("#sheet .sheet");
  if (!inner) { openSheet(html); return; }
  var strips = saveStrips(inner);
  inner.innerHTML = html;
  restoreStrips(strips, inner);
}

function closeSheet() {
  S.sheetSeq = (S.sheetSeq || 0) + 1;
  var sheet = $("#sheet");
  sheet.classList.remove("show");
  sheet.innerHTML = "";
  document.body.style.overflow = "";
  if (S.pickerUnused) {
    S.pickerUnused = null;
    document.querySelectorAll(".pick.open").forEach(function (node) { node.classList.remove("open"); });
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("cc_theme", theme); } catch (_) {}
  $("#theme").innerHTML = ic(theme === "dark" ? "sun" : "moon");
  var background = theme === "dark" ? "#0e0f11" : "#f2f2f4";
  document.querySelector('meta[name="theme-color"]').content = background;
  try {
    if (tg) {
      tg.setHeaderColor(background);
      tg.setBackgroundColor(background);
    }
  } catch (_) {}
}

function broadcastCard() {
  return '<div class="card"><h3>Рассылка</h3><form id="broadcast-form" class="rte">' +
    '<div class="rte-bar" role="toolbar" aria-label="Оформление текста">' +
    '<button type="button" data-fmt="bold" aria-label="Жирный"><b>Ж</b></button>' +
    '<button type="button" data-fmt="italic" aria-label="Курсив"><i>К</i></button>' +
    '<button type="button" data-fmt="underline" aria-label="Подчёркнутый"><u>Ч</u></button>' +
    '<button type="button" data-fmt="strikeThrough" aria-label="Зачёркнутый"><s>З</s></button>' +
    '<button type="button" data-act="bimg">' + ic("image") + "<span>Картинка</span></button></div>" +
    '<div class="rte-ed" id="bc-ed" contenteditable="true" role="textbox" aria-multiline="true" data-ph="Текст сообщения. Выделите слово и нажмите Ж или К — как в Telegram.">' + S.bcHtml + "</div>" +
    (S.bcImage ? '<div class="rte-img"><img src="' + esc(S.bcImage) + '" alt="Картинка рассылки"><button type="button" data-act="bimgdel" aria-label="Убрать картинку">' + ic("x") + "</button></div>" : "") +
    '<input type="file" id="bc-file" accept="image/png,image/jpeg,image/webp" hidden>' +
    '<button class="btn main" type="submit">' + ic("send") + "Отправить всем, кроме забаненных</button></form></div>";
}

function adminMembers() {
  var query = normalizeSearch(S.memberQuery);
  var all = S.members || [];
  var list = all.filter(function (m) {
    return !query || normalizeSearch("@" + m.username + " " + m.first_name + " " + m.id).indexOf(query) >= 0;
  });
  var opened = all.filter(function (m) { return m.app_opened; }).length;
  return '<div class="grid">' + [["Запустили бота", all.length], ["Открыли мини‑апп", opened], ["Не открывали", all.length - opened], ["Забанено", all.filter(function (m) { return m.banned; }).length]].map(function (row) {
      return '<div class="card tile"><small class="muted">' + row[0] + '</small><b class="num" data-to="' + row[1] + '">' + row[1] + "</b></div>";
    }).join("") + "</div>" +
    '<div class="card"><h3>Все участники</h3><input id="mem-q" value="' + esc(S.memberQuery) + '" placeholder="Поиск по @username, имени или ID" autocomplete="off">' +
    '<div class="ulist">' + (list.length ? list.map(function (m) {
      var name = m.username ? "@" + m.username : (m.first_name || "Без имени");
      return '<div class="mem"><i class="dot' + (m.app_opened ? " on" : "") + '" aria-hidden="true"></i><div><b>' + esc(name) + "</b>" +
        '<span class="meta">ID ' + esc(m.id) + (m.username && m.first_name ? " · " + esc(m.first_name) : "") + (m.banned ? " · бан" : "") + "</span></div>" +
        '<span class="badge' + (m.app_opened ? " m" : "") + '">' + (m.app_opened ? "Открыл мини‑апп" : "Не открывал") + "</span></div>";
    }).join("") : '<p class="muted">Никого не найдено.</p>') + "</div></div>";
}

function adminErrors() {
  var errors = S.errors || { recent: [], day: {} };
  var names = { osm: "OpenStreetMap", geoapify: "Geoapify", google: "Google", gemini: "Нейросеть", ai: "Нейросеть", geocoder: "Геокодер" };
  var day = Object.keys(errors.day || {});
  return '<div class="card"><h3>За сутки</h3>' + (day.length ? day.map(function (key) {
      return '<div class="row"><span>' + esc(names[key] || key) + "</span><b>" + esc(errors.day[key]) + "</b></div>";
    }).join("") : '<p class="muted">Ошибок нет — все источники отвечают.</p>') + "</div>" +
    '<div class="card"><h3>Последние</h3>' + (errors.recent.length ? errors.recent.map(function (item) {
      return '<div class="err"><b>' + esc(names[item.provider] || item.provider) + '</b> <span class="muted small">' +
        esc(new Date(item.created_at * 1000).toLocaleString("ru-RU")) + "</span><p class=\"muted small\">" + esc(item.message) + "</p></div>";
    }).join("") : '<p class="muted">Пусто.</p>') + "</div>" +
    '<p class="muted small">Ошибка одного источника не ломает поиск: остальные продолжают работать.</p>';
}

function shrinkImage(file) {
  return new Promise(function (resolve, reject) {
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var scale = Math.min(1, 1600 / Math.max(img.width, img.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.86));
    };
    img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });
}

/* Текст редактора → HTML для Telegram: только <b> <i> <u> <s>, переносы строк. */
function editorToTelegram(node) {
  var out = "";
  node.childNodes.forEach(function (child) {
    if (child.nodeType === 3) { out += child.nodeValue.replace(/\u00a0/g, " "); return; }
    if (child.nodeType !== 1) return;
    var tag = child.tagName.toLowerCase();
    if (tag === "br") { out += "\n"; return; }
    var inner = editorToTelegram(child);
    var style = child.style || {};
    var deco = String(style.textDecorationLine || style.textDecoration || "");
    var weight = String(style.fontWeight || "");
    if (tag === "b" || tag === "strong" || weight === "bold" || Number(weight) >= 600) inner = "<b>" + inner + "</b>";
    if (tag === "i" || tag === "em" || style.fontStyle === "italic") inner = "<i>" + inner + "</i>";
    if (tag === "u" || deco.indexOf("underline") >= 0) inner = "<u>" + inner + "</u>";
    if (tag === "s" || tag === "strike" || tag === "del" || deco.indexOf("line-through") >= 0) inner = "<s>" + inner + "</s>";
    if ((tag === "div" || tag === "p") && out && !/\n$/.test(out)) out += "\n";
    out += inner;
  });
  return out;
}

document.addEventListener("mousedown", function (event) {
  var fmt = event.target.closest && event.target.closest("[data-fmt]");
  if (!fmt) return;
  event.preventDefault();
  var ed = $("#bc-ed");
  if (ed && document.activeElement !== ed) ed.focus();
  try { document.execCommand(fmt.dataset.fmt, false, null); } catch (_) {}
  if (ed) S.bcHtml = ed.innerHTML;
});
document.addEventListener("paste", function (event) {
  if (!event.target.closest || !event.target.closest("#bc-ed")) return;
  event.preventDefault();
  var text = (event.clipboardData || window.clipboardData).getData("text/plain");
  try { document.execCommand("insertText", false, text); } catch (_) {}
});
document.addEventListener("scroll", function (event) {
  var track = event.target;
  if (track && track.classList && track.classList.contains("hs-track")) updateStrips(track.parentNode.parentNode);
}, true);
document.addEventListener("wheel", function (event) {
  var track = event.target.closest && event.target.closest(".hs-track");
  if (!track || track.scrollWidth <= track.clientWidth) return;
  if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
  event.preventDefault();
  track.scrollBy({ left: event.deltaY, behavior: "auto" });
}, { passive: false });
window.addEventListener("resize", function () { updateStrips(); });

function formValue(form, name) {
  return String(new FormData(form).get(name) || "").trim();
}

function appReady() {
  if (typeof window.__appReady === "function") window.__appReady();
}


/* ================= Script C&C ================= */
var SHORT_CH = { telegram: "Telegram", instagram: "Instagram", call: "Звонок", email: "Email" };
var SUPPORT_TELEGRAM = "SUN9ISE";
var JOIN_URL = "/#join"; // тарифы C&C Family в общем мини-аппе
var TABS = [
  ["home", "Главная", "home"], ["library", "Библиотека", "book"], ["create", "Создать", "spark"],
  ["saved", "Мои", "bookmark"], ["faq", "Вопросы", "help"], ["admin", "Админ", "shield"]
];
var ADMIN_TABS = [
  ["overview", "Статистика"], ["users", "Пользователи"], ["members", "Участники"], ["library", "Библиотека"],
  ["keys", "Ключи"], ["broadcast", "Рассылка"], ["requests", "Запросы"], ["errors", "Ошибки"]
];
var TIPS = [
  "Читаю описание и подбираю подходящий тон…",
  "Пишу текст так, чтобы на него было легко ответить.",
  "Добавляю один простой вопрос в конце — так чаще отвечают.",
  "Совет: замените [Имя] и [Название] на реальные данные перед отправкой.",
  "Совет: первое сообщение лучше делать коротким — 3–5 предложений.",
  "Совет: если не ответили, напишите повторно через 2–3 дня.",
  "Готовые скрипты на каждый случай — во вкладке «Библиотека».",
  "Понравился текст — сохраните его в «Мои скрипты»."
];
var NOTES = {
  no_ai: "Нейросеть сейчас не подключена, поэтому скрипт собран из шаблона.",
  ai_error: "Нейросеть не ответила, поэтому скрипт собран из шаблона.",
  global_limit: "Нейросеть сегодня уже много работала, поэтому скрипт собран из шаблона.",
  user_limit: "Вы достигли дневного лимита нейросети, поэтому скрипт собран из шаблона."
};
var S = {
  tab: "home", name: "", username: "", admin: false, access: null, stats: { generated: 0, week: 0, saved: 0 },
  purposes: [], channels: [], tones: [], nicheHints: [], ai: true,
  lib: [], libCat: "all", libOpen: {}, libLoaded: false,
  saved: [], savedLoaded: false, savedEdit: null, savedOpen: {},
  form: { niche: "", purpose: "first", channel: "telegram", tone: "friendly", details: "" },
  genState: "form", gen: null, genRes: null, genVariant: 0, genSaved: false, genDone: false, genMinAt: 0, genLoop: null, shown: 0, tipIndex: 0,
  intro: { library: true, create: true },
  atab: "overview", users: [], members: [], keys: [], overview: null, requests: [], adminLib: [], errors: null,
  libNew: false, libEdit: null, libDel: null, userQuery: "", memberQuery: "", editId: null, editVal: 20, delConfirm: null,
  defLimit: 20, defVal: 20, defScope: "standard", defOpen: false,
  bcHtml: "", bcImage: "", newKey: "", sheetSeq: 0
};

var isTrial = function () { return S.access && S.access.plan === "trial"; };
var trialOver = function () { return isTrial() && S.access.left <= 0; };
var canGenerate = function () {
  if (!S.access) return false;
  return isTrial() ? S.access.left > 0 : S.access.used < S.access.limit;
};
var restGens = function () {
  if (!S.access) return 0;
  return isTrial() ? Math.max(0, S.access.left) : Math.max(0, S.access.limit - S.access.used);
};
function purposeTitle(id) {
  var found = S.purposes.filter(function (item) { return item.id === id; })[0];
  return found ? found.title : "";
}
function genWord(n) { return plural(n, "генерация", "генерации", "генераций"); }

function introBlock(key, title, body) {
  return '<details class="intro"' + (S.intro[key] ? " open" : "") + ' data-intro="' + key + '"><summary>' + ic("info") + esc(title) + PM +
    '</summary><div class="intro-body">' + body + "</div></details>";
}

/* ---------- Загрузка данных ---------- */

function loadMe() {
  return api("/api/me").then(function (me) {
    S.name = me.name || "";
    S.username = me.username || "";
    S.admin = Boolean(me.is_admin);
    S.access = me.access || null;
    S.stats = me.stats || S.stats;
    S.ai = me.ai !== false;
    if (me.access && me.access.join) JOIN_URL = me.access.join;
    if (me.access && me.access.contact) SUPPORT_TELEGRAM = me.access.contact;
    if (Array.isArray(me.purposes)) S.purposes = me.purposes;
    if (Array.isArray(me.channels)) S.channels = me.channels;
    if (Array.isArray(me.tones)) S.tones = me.tones;
    if (Array.isArray(me.niche_hints)) S.nicheHints = me.niche_hints;
    if (S.tab === "admin" && !S.admin) S.tab = "home";
    return me;
  });
}

function loadLibrary() {
  return api("/api/library").then(function (data) {
    S.lib = data.items || [];
    S.libLoaded = true;
    return S.lib;
  });
}

function loadSaved() {
  return api("/api/saved").then(function (data) {
    S.saved = data.items || [];
    S.savedLoaded = true;
    S.stats.saved = S.saved.length;
    return S.saved;
  });
}

function refreshAll() {
  return loadMe().then(function () {
    return Promise.all([loadLibrary().catch(function () {}), loadSaved().catch(function () {})]);
  }).then(function () {
    if (S.tab === "admin" && S.admin) return loadAdmin();
  }).then(function () { render(); });
}

/* ---------- Доступ ---------- */

function accessCard() {
  if (!S.access) return "";
  if (trialOver()) return trialOfferCard(S.access.trial_message);
  if (isTrial()) {
    return '<div class="card access"><div class="row"><span>Пробный доступ</span><b>' +
      S.access.left + " " + genWord(S.access.left) +
      '</b></div><p class="muted small">Из ' + S.access.trial_total + ' бесплатных. Часть библиотеки открыта сразу, остальное — в команде C&amp;C Family или по ключу.</p></div>';
  }
  var usedPercent = S.access.limit ? Math.min(100, Math.round(S.access.used / S.access.limit * 100)) : 0;
  return '<div class="card"><div class="row"><span>Лимит на сегодня</span><b>' +
    S.access.used + " / " + S.access.limit + '</b></div><div class="bar"><i style="width:' +
    usedPercent + '%"></i></div><p class="muted small">Осталось ' + restGens() +
    ". Обновление по времени сервера.</p></div>";
}

function trialOfferCard(message) {
  var text = message || ("Пробный доступ закончился.\nЧтобы продолжить создавать скрипты и пользоваться библиотекой Script C&C, вступите в команду C&C Family,\nподробности можно узнать у @" + SUPPORT_TELEGRAM + ".");
  return '<div class="card offer"><p>' + esc(text) + '</p><div class="btns">' +
    '<a class="btn main" data-ext href="' + esc(JOIN_URL) + '" target="_blank" rel="noopener">' + ic("users") + "Вступить в команду</a>" +
    '<a class="btn" data-ext href="https://t.me/' + esc(SUPPORT_TELEGRAM) + '" target="_blank" rel="noopener">' + ic("plus") + "Докупить генерации</a>" +
    '<a class="btn" data-ext href="https://t.me/' + esc(SUPPORT_TELEGRAM) + '" target="_blank" rel="noopener">' + ic("send") + "Написать @" + esc(SUPPORT_TELEGRAM) + "</a></div>" +
    '<form id="key-form" class="keyform"><input name="code" placeholder="Ключ доступа CC-…" autocomplete="off" maxlength="64" aria-label="Ключ доступа">' +
    '<button class="btn" type="submit">' + ic("key") + "Ввести</button></form></div>";
}

function showOffer(message) {
  openSheet('<div class="top"><h2>Нужен полный доступ</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' + ic("x") + "</button></div>" +
    trialOfferCard(message));
}

function plural(n, one, few, many) {
  var mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

/* ---------- Главная ---------- */

function vHome() {
  var hello = S.name ? "Привет, " + esc(S.name) : "Привет";
  var libCount = S.lib.length;
  return '<section class="screen"><div class="hello">' + hello +
    "<small>Скрипты для общения с клиентами — готовые и под вашу нишу</small></div>" +
    accessCard() +
    '<div class="hero">' +
    '<button class="big main" data-act="tab" data-v="create"><span class="bi">' + ic("spark") + '</span><span><b>Создать скрипт</b><small>Опишите нишу и цель — Script C&amp;C напишет текст</small></span>' + ic("chev", "chev") + "</button>" +
    '<button class="big" data-act="tab" data-v="library"><span class="bi">' + ic("book") + '</span><span><b>Библиотека скриптов</b><small>' +
      (libCount ? libCount + " " + plural(libCount, "готовый скрипт", "готовых скрипта", "готовых скриптов") + ": сообщения, звонки, возражения" : "Готовые скрипты на все случаи") + "</small></span>" + ic("chev", "chev") + "</button>" +
    '<button class="big" data-act="tab" data-v="saved"><span class="bi">' + ic("bookmark") + '</span><span><b>Мои скрипты</b><small>' +
      (S.stats.saved ? "Сохранено: " + S.stats.saved : "Здесь будут ваши сохранённые тексты") + "</small></span>" + ic("chev", "chev") + "</button>" +
    "</div>" +
    '<div class="mini-stats">' + [["Создано", S.stats.generated], ["За 7 дней", S.stats.week], ["Сохранено", S.stats.saved]].map(function (row) {
      return '<div class="card"><small>' + row[0] + '</small><b class="num" data-to="' + (row[1] || 0) + '">' + (row[1] || 0) + "</b></div>";
    }).join("") + "</div></section>";
}

/* ---------- Библиотека ---------- */

function libItem(item) {
  var open = Boolean(S.libOpen[item.id]);
  var tag = item.locked
    ? '<span class="tag lock">' + ic("lock") + "Закрыто</span>"
    : '<span class="tag">' + esc(purposeTitle(item.category)) + "</span>";
  var head = '<div class="scr-head"><b>' + esc(item.title) + "</b>" + tag + "</div>";
  if (item.locked) {
    return '<div class="scr locked">' + head + '<p class="scr-text clamp">' + esc(item.body) + "</p>" +
      '<div class="lockbar">' + ic("lock") + "<span>Полный текст — для участников C&amp;C Family</span></div>" +
      '<div class="tools"><button class="main" data-act="offer">' + ic("key") + "Открыть доступ</button></div></div>";
  }
  return '<div class="scr">' + head + '<p class="scr-text' + (open ? "" : " clamp") + '">' + esc(item.body) + "</p>" +
    '<div class="tools"><button class="main" data-act="lcopy" data-id="' + item.id + '">' + ic("copy") + "Копировать</button>" +
    '<button data-act="lopen" data-id="' + item.id + '">' + (open ? "Свернуть" : "Читать полностью") + "</button>" +
    '<button data-act="lsave" data-id="' + item.id + '">' + ic("bookmark") + "В мои скрипты</button></div></div>";
}

function vLibrary() {
  var list = S.lib.filter(function (item) { return S.libCat === "all" || item.category === S.libCat; });
  var chips = [["all", "Все"]].concat(S.purposes.map(function (p) { return [p.id, p.title]; }));
  return '<section class="screen"><div class="top"><h2>Библиотека <small>' + S.lib.length + "</small></h2></div>" +
    introBlock("library", "Как пользоваться библиотекой",
      "<p>Здесь готовые скрипты на разные случаи общения с клиентом.</p>" +
      '<ul class="steps"><li><b>Выберите категорию</b> — первое сообщение, звонок, возражение, закрытие сделки и другие.</li>' +
      "<li><b>Скопируйте</b> скрипт и замените пометки в квадратных скобках на свои данные.</li>" +
      "<li><b>Сохраните в «Мои»</b>, если хотите править текст под себя.</li>" +
      "<li><b>Нужно под вашу нишу?</b> Откройте вкладку «Создать».</li></ul>" +
      (isTrial() ? '<p class="meta">На пробном доступе часть скриптов открыта полностью, остальные закрыты.</p>' : "")) +
    hstrip("libcats", chips.map(function (item) {
      return '<button class="chip ' + (S.libCat === item[0] ? "on" : "") + '" data-act="libcat" data-v="' + esc(item[0]) + '">' + esc(item[1]) + "</button>";
    }).join("")) +
    (S.libLoaded
      ? (list.length
        ? '<div class="card scr-list">' + list.map(libItem).join("") + "</div>"
        : '<div class="empty">' + ic("book") + "<p>В этой категории пока пусто</p></div>")
      : '<div class="dots"><i></i><i></i><i></i></div>') +
    "</section>";
}

/* ---------- Создать скрипт ---------- */

function syncForm() {
  var details = $("#g-details"), niche = $("#g-niche");
  if (details) S.form.details = details.value;
  if (niche) S.form.niche = niche.value;
}

function vCreate() {
  if (S.genState === "loading") return loadingView();
  if (S.genState === "result" && S.gen) return resultView();
  return formView();
}

function formView() {
  var f = S.form;
  var over = !canGenerate();
  return '<section class="screen"><h2>Создать скрипт</h2>' +
    introBlock("create", "Что можно делать на этой странице",
      "<p>Опишите, какой скрипт вам нужен, — Script C&amp;C напишет его за несколько секунд.</p>" +
      '<ul class="steps"><li><b>Опишите задачу</b> своими словами: кому пишете и что предлагаете.</li>' +
      "<li><b>Укажите нишу</b> клиента и выберите, для чего скрипт.</li>" +
      "<li><b>Выберите канал и тон</b> — текст подстроится под них.</li>" +
      "<li><b>Нажмите «Сгенерировать»</b>. Не понравилось — нажмите «Ещё вариант».</li></ul>" +
      '<p class="meta">Пометки в квадратных скобках замените своими данными. Ничего не выдумывается: цифры и обещания добавляйте сами.</p>') +
    "<h3>Что нужно написать</h3>" +
    '<textarea id="g-details" rows="4" maxlength="700" placeholder="Например: первое сообщение владельцу барбершопа, я делаю сайты с онлайн-записью">' + esc(f.details) + "</textarea>" +
    '<div class="count"><span id="g-count">' + f.details.length + "/700</span></div>" +
    "<h3>Ниша клиента</h3>" +
    '<input id="g-niche" value="' + esc(f.niche) + '" maxlength="80" placeholder="Например: барбершоп, автосервис, стоматология" autocomplete="off">' +
    '<div style="margin-top:8px">' + hstrip("hints", S.nicheHints.map(function (name) {
      return '<button class="chip ' + (f.niche.toLowerCase() === name.toLowerCase() ? "on" : "") + '" data-act="hint" data-v="' + esc(name) + '">' + esc(name) + "</button>";
    }).join("")) + "</div>" +
    "<h3>Для чего скрипт</h3>" +
    hstrip("purposes", S.purposes.map(function (p) {
      return '<button class="chip ' + (f.purpose === p.id ? "on" : "") + '" data-act="purpose" data-v="' + esc(p.id) + '">' + esc(p.title) + "</button>";
    }).join("")) +
    "<h3>Канал</h3>" +
    '<div class="seg four">' + S.channels.map(function (c) {
      return '<button class="' + (f.channel === c.id ? "on" : "") + '" data-act="channel" data-v="' + esc(c.id) + '">' + esc(SHORT_CH[c.id] || c.title) + "</button>";
    }).join("") + "</div>" +
    "<h3>Тон</h3>" +
    '<div class="seg three">' + S.tones.map(function (t) {
      return '<button class="' + (f.tone === t.id ? "on" : "") + '" data-act="tone" data-v="' + esc(t.id) + '">' + esc(t.title) + "</button>";
    }).join("") + "</div>" +
    (over && trialOver() ? trialOfferCard(S.access.trial_message) : "") +
    '<button class="cta" data-act="gen" ' + (over ? "disabled" : "") + ">" +
    (over ? (isTrial() ? "Пробный доступ закончился" : "Лимит на сегодня исчерпан") : "Сгенерировать скрипт") + "</button>" +
    (!over ? '<p class="count-tip">Осталось: ' + restGens() + " " + genWord(restGens()) + (isTrial() ? " из пробного доступа." : " на сегодня.") + "</p>" : "") +
    "</section>";
}

function loadingView() {
  return '<section class="screen center"><div class="beat"><i class="bird"></i></div>' +
    "<h2>Пишу скрипт</h2>" +
    '<div class="glow"><i id="pb" style="width:' + Math.max(3, S.shown) + '%"></i></div>' +
    '<p class="tipline" id="ptip">' + esc(TIPS[S.tipIndex % TIPS.length]) + "</p>" +
    '<p class="muted small loadnote">Обычно это занимает 5–15 секунд.</p></section>';
}

function stopGenLoop() {
  if (S.genLoop) clearInterval(S.genLoop);
  S.genLoop = null;
}

function startGenLoop() {
  stopGenLoop();
  var last = performance.now();
  var tipAt = last;
  var finished = false;
  S.genLoop = setInterval(function () {
    var now = performance.now();
    var dt = Math.min(200, now - last);
    last = now;
    var ready = S.genDone && now >= S.genMinAt;
    if (ready) S.shown = Math.min(100, S.shown + dt * 0.12);
    else S.shown += (91 - S.shown) * 0.0016 * dt;
    if (now - tipAt > 3200) {
      tipAt = now;
      var tip = $("#ptip");
      if (tip) {
        tip.classList.add("fade");
        setTimeout(function () {
          S.tipIndex = (S.tipIndex + 1) % TIPS.length;
          var node = $("#ptip");
          if (node) { node.textContent = TIPS[S.tipIndex]; node.classList.remove("fade"); }
        }, 350);
      }
    }
    var bar = $("#pb");
    if (bar) bar.style.width = S.shown.toFixed(1) + "%";
    if (ready && !finished && S.shown >= 100) {
      finished = true;
      stopGenLoop();
      setTimeout(finishGen, 350);
    }
  }, 40);
}

function finishGen() {
  S.gen = S.genRes;
  S.genState = "result";
  S.genSaved = false;
  if (S.tab === "create") render();
}

function doGenerate(variant) {
  syncForm();
  var f = S.form;
  if (f.niche.trim().length < 2 && f.details.trim().length < 8) {
    toast("Напишите нишу или коротко опишите, какой скрипт нужен.");
    return;
  }
  if (!canGenerate()) { if (trialOver()) showOffer(S.access.trial_message); else toast("Дневной лимит исчерпан."); return; }
  S.genState = "loading";
  S.genDone = false;
  S.shown = 4;
  S.genVariant = variant || 0;
  S.genMinAt = performance.now() + 1800;
  render();
  startGenLoop();
  api("/api/generate", {
    method: "POST",
    body: JSON.stringify({ niche: f.niche, purpose: f.purpose, channel: f.channel, tone: f.tone, details: f.details, variant: S.genVariant })
  }).then(function (res) {
    S.access = res.access || S.access;
    S.genRes = res;
    S.stats.generated = (S.stats.generated || 0) + 1;
    S.stats.week = (S.stats.week || 0) + 1;
    S.genDone = true;
  }).catch(function (error) {
    stopGenLoop();
    S.genState = S.gen ? "result" : "form";
    var code = error.detail && error.detail.code;
    if (code === "trial_over") {
      S.access = Object.assign({}, S.access, { left: 0, trial_over: true, trial_message: error.detail.message });
      render();
      showOffer(error.detail.message);
      return;
    }
    if (S.tab === "create") render();
    toast(error.message);
  });
}

function copyCard(text) {
  return '<div class="card tapcopy" data-act="copygen" role="button" tabindex="0" aria-label="Скопировать текст"><pre class="scr-text" id="gen-text" style="margin:0">' + esc(text) + "</pre></div>" +
    '<p class="copyhint">Нажми на текст, чтобы скопировать</p>';
}

function resultView() {
  var g = S.gen;
  var ai = g.source === "ai";
  return '<section class="screen"><div class="top"><h2>Готово</h2><button class="icon-btn" data-act="editreq" aria-label="Изменить запрос">' + ic("edit") + "</button></div>" +
    '<div class="result-meta"><span class="tag' + (ai ? " own" : "") + '">' + (ai ? "Нейросеть" : "Шаблон") + '</span><span class="src">' + esc(g.title) + "</span></div>" +
    (NOTES[g.note] ? '<p class="meta" style="margin-bottom:8px">' + esc(NOTES[g.note] + (g.refunded ? " Эта генерация не списана." : "")) + "</p>" : "") +
    copyCard(g.text) +
    '<div class="tools"><button class="main" data-act="copygen">' + ic("copy") + "Копировать</button>" +
    '<button data-act="genmore">' + ic("spark") + "Ещё вариант</button>" +
    '<button id="save-gen" data-act="savegen"' + (S.genSaved ? " disabled" : "") + ">" + ic("bookmark") + (S.genSaved ? "Сохранено" : "Сохранить в мои") + "</button>" +
    '<button data-act="editreq">' + ic("edit") + "Изменить запрос</button></div>" +
    (isTrial() && trialOver() ? trialOfferCard(S.access.trial_message) : '<p class="count-tip">Осталось: ' + restGens() + " " + genWord(restGens()) + ".</p>") +
    "</section>";
}

function saveGenerated() {
  if (S.genSaved || !S.gen) return;
  S.genSaved = true;
  var button = $("#save-gen");
  if (button) { button.disabled = true; button.innerHTML = ic("bookmark") + "Сохранено"; }
  api("/api/saved", {
    method: "POST",
    body: JSON.stringify({ title: S.gen.title, body: S.gen.text, niche: S.form.niche, purpose: S.form.purpose })
  }).then(function () {
    toast("Сохранено во вкладке «Мои».");
    return loadSaved();
  }).catch(function (error) {
    S.genSaved = false;
    if (button) { button.disabled = false; button.innerHTML = ic("bookmark") + "Сохранить в мои"; }
    toast(error.message);
  });
}

/* ---------- Мои скрипты ---------- */

function savedItem(item) {
  var editing = S.savedEdit === item.id;
  var open = Boolean(S.savedOpen[item.id]);
  if (editing) {
    return '<div class="scr"><form id="saved-form" data-id="' + item.id + '" class="form">' +
      '<input name="title" value="' + esc(item.title) + '" maxlength="80" required aria-label="Название">' +
      '<textarea name="body" rows="9" maxlength="4000" required>' + esc(item.body) + "</textarea>" +
      '<div class="tools"><button class="main" type="submit">Сохранить</button><button type="button" data-act="scancel">Отмена</button></div></form></div>';
  }
  return '<div class="scr"><div class="scr-head"><b>' + esc(item.title) + '</b><span class="tag own">' + esc(purposeTitle(item.purpose) || "Мой") + "</span></div>" +
    '<p class="scr-text' + (open ? "" : " clamp") + '">' + esc(item.body) + "</p>" +
    '<div class="tools"><button class="main" data-act="scopy" data-id="' + item.id + '">' + ic("copy") + "Копировать</button>" +
    '<button data-act="sedit" data-id="' + item.id + '">' + ic("edit") + "Изменить</button>" +
    '<button data-act="sopen" data-id="' + item.id + '">' + (open ? "Свернуть" : "Читать полностью") + "</button>" +
    '<button data-act="sdel" data-id="' + item.id + '">' + ic("trash") + "Удалить</button></div></div>";
}

function vSaved() {
  return '<section class="screen"><div class="top"><h2>Мои скрипты <small>' + S.saved.length + "</small></h2></div>" +
    (S.saved.length
      ? '<div class="card scr-list">' + S.saved.map(savedItem).join("") + "</div>"
      : '<div class="empty">' + ic("bookmark") + "<p>Здесь пока пусто</p></div>" +
        '<div class="btns"><button class="btn main" data-act="tab" data-v="create">' + ic("spark") + "Создать скрипт</button>" +
        '<button class="btn" data-act="tab" data-v="library">' + ic("book") + "Открыть библиотеку</button></div>") +
    "</section>";
}

/* ---------- Вопросы ---------- */

function faqItem(question, answer) {
  return "<details><summary><span>" + question + "</span>" + PM + '</summary><div class="faq-a">' + answer + "</div></details>";
}

function vFaq() {
  var steps = [
    ["Откройте «Создать»", "Опишите, какой скрипт нужен, укажите нишу клиента и выберите, для чего он."],
    ["Выберите канал и тон", "Telegram, Instagram, звонок или email — текст подстроится под формат."],
    ["Нажмите «Сгенерировать»", "Script C&C напишет текст за несколько секунд. Не подошло — «Ещё вариант»."],
    ["Подставьте свои данные", "Замените пометки в квадратных скобках: [Имя], [Название], [Ваше имя]."],
    ["Сохраните и используйте", "Лучшие тексты сохраняйте в «Мои скрипты» и копируйте в один тап."]
  ];
  var keys = [
    ["Что такое «Библиотека»?", "Готовые скрипты на разные случаи: первое сообщение, звонок, дожим, ответ на возражение, презентация, закрытие сделки, возвращение клиента и просьба об отзыве."],
    ["Как создать свой скрипт?", "Вкладка <b>«Создать»</b>: опишите задачу, нишу и цель. Нейросеть напишет текст под ваш запрос."],
    ["Что значит «Шаблон»?", "Если нейросеть временно недоступна, скрипт собирается из готового шаблона. Несколько таких генераций в день <b>не списываются</b> — об этом будет написано под текстом."],
    ["Что такое пробный доступ?", "Несколько бесплатных генераций и часть библиотеки целиком. Остальное — в команде C&amp;C Family."],
    ["Как получить полный доступ?", "Вступите в команду C&amp;C Family — подробности у @" + esc(SUPPORT_TELEGRAM) + ". Если вам выдали ключ, введите его на главной или отправьте боту: <b>/key КОД</b>."],
    ["Что такое лимит?", "Для участников — сколько скриптов можно создать за день. Обновляется каждый день."],
    ["Можно ли править скрипты?", "Да. Сохраните скрипт в «Мои» и нажмите «Изменить». Библиотека при этом не меняется."],
    ["Скрипт получился не таким", "Уточните описание: кому пишете, что предлагаете и какой тон нужен. Или нажмите «Ещё вариант»."],
    ["Нейросеть выдумывает факты?", "Скрипты пишутся без цифр, отзывов и гарантий, а неизвестное остаётся в квадратных скобках. Перед отправкой всё равно перечитайте текст."]
  ];
  return '<section class="screen"><h2>Вопросы</h2>' +
    '<div class="card howto"><h3>Как пользоваться</h3><ol class="howto-steps">' +
    steps.map(function (step) { return "<li><b>" + esc(step[0]) + "</b><span>" + esc(step[1]) + "</span></li>"; }).join("") +
    "</ol></div>" +
    '<div class="card faq"><h3>Частые вопросы</h3>' +
    keys.map(function (item) { return faqItem(esc(item[0]), item[1]); }).join("") +
    '</div><a class="contact" data-ext href="https://t.me/' + esc(SUPPORT_TELEGRAM) + '" target="_blank" rel="noopener">' + ic("send") +
    "Написать @" + esc(SUPPORT_TELEGRAM) + "</a>" +
    '<p class="meta center-text" style="margin:10px 0 4px">Поддержка</p></section>';
}

/* ---------- Админ ---------- */

function loadAdmin() {
  if (!S.admin) return Promise.reject(new Error("Только для администратора."));
  var loaders = {
    overview: function () {
      return Promise.all([api("/api/admin/overview"), api("/api/admin/settings")]).then(function (r) {
        S.overview = r[0]; S.errors = r[0].errors;
        S.defLimit = Number(r[1].default_limit);
        if (!S.defOpen) S.defVal = S.defLimit;
      });
    },
    users: function () {
      return Promise.all([api("/api/admin/users"), api("/api/admin/settings")]).then(function (r) {
        S.users = r[0].users || [];
        S.defLimit = Number(r[1].default_limit);
        if (!S.defOpen) S.defVal = S.defLimit;
      });
    },
    members: function () { return api("/api/admin/members").then(function (d) { S.members = d.members || []; }); },
    library: function () { return api("/api/admin/library").then(function (d) { S.adminLib = d.items || []; }); },
    keys: function () {
      return Promise.all([api("/api/admin/keys"), api("/api/admin/settings")]).then(function (r) {
        S.keys = r[0].keys || [];
        S.defLimit = Number(r[1].default_limit);
      });
    },
    broadcast: function () { return Promise.resolve(); },
    requests: function () { return api("/api/admin/requests").then(function (d) { S.requests = d.items || []; }); },
    errors: function () { return api("/api/admin/overview").then(function (d) { S.errors = d.errors; S.overview = d; }); }
  };
  return (loaders[S.atab] || loaders.overview)();
}

function tiles(rows) {
  return '<div class="grid">' + rows.map(function (row) {
    return '<div class="card tile"><small class="muted">' + row[0] + '</small><b class="num" data-to="' + (row[1] || 0) + '">' + (row[1] || 0) + "</b></div>";
  }).join("") + "</div>";
}

function table2(rows, headers, nameFn) {
  if (!rows || !rows.length) return '<p class="muted">Пока нет данных.</p>';
  return '<div style="overflow-x:auto"><table class="tbl"><tr>' + headers.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr>" +
    rows.map(function (row) { return "<tr><td>" + esc(nameFn ? nameFn(row.name) : row.name) + "</td><td>" + esc(row.n) + "</td></tr>"; }).join("") +
    "</table></div>";
}

function last7(series) {
  var map = {};
  (series || []).forEach(function (row) { map[row.day] = row.n; });
  var days = [];
  for (var i = 6; i >= 0; i--) {
    var d = new Date(Date.now() - i * 86400000);
    var key = d.toISOString().slice(0, 10);
    days.push({ key: key, label: key.slice(8, 10) + "." + key.slice(5, 7), n: map[key] || 0 });
  }
  return days;
}

function adminOverview() {
  var o = S.overview;
  if (!o) return '<div class="dots"><i></i><i></i><i></i></div>';
  var days = last7(o.series);
  var max = Math.max(1, Math.max.apply(null, days.map(function (d) { return d.n; })));
  var aiLine = o.api.ai_enabled
    ? "Подключена. Сегодня запросов: " + o.api.ai_day + " из " + o.api.ai_limit + "."
    : "Не подключена: скрипты собираются из шаблона. Добавьте GEMINI_API_KEY в переменные сервера.";
  return tiles([["Пользователей", o.users.total], ["Участников", o.users.members], ["На пробе", (o.users.trial_used || 0) + (o.users.trial_left || 0)], ["Забанено", o.users.banned]]) +
    defaultLimitCard() +
    tiles([["Скриптов создано", o.gens.total], ["Сегодня", o.gens.today], ["За 7 дней", o.gens.week], ["Людей создавали", o.gens.people]]) +
    '<div class="card"><h3>Нейросеть</h3><p class="small">' + esc(aiLine) + '</p><p class="muted small">Нейросеть: ' + esc(o.gens.ai) + " · Шаблон: " + esc(o.gens.template) + "</p></div>" +
    '<div class="card"><h3>Последние 7 дней</h3><div class="bars">' + days.map(function (d) {
      return "<div><i style=\"height:" + Math.round(d.n / max * 100) + '%" title="' + d.n + '"></i><span>' + esc(d.label) + "</span></div>";
    }).join("") + "</div></div>" +
    '<div class="card"><h3>Для чего создают</h3>' + table2(o.purposes, ["Цель", "Раз"], function (name) { return (o.purpose_titles && o.purpose_titles[name]) || name; }) + "</div>" +
    '<div class="card"><h3>Популярные ниши</h3>' + table2(o.niches, ["Ниша", "Раз"]) + "</div>" +
    '<div class="card"><h3>Контент</h3><div class="row"><span>В библиотеке</span><b>' + esc(o.library) + '</b></div><div class="row g"><span>Сохранено пользователями</span><b>' + esc(o.saved) + "</b></div></div>";
}

function userRow(user) {
  var editing = S.editId === user.id;
  var badge = user.banned ? '<span class="badge b">Бан</span>' :
    user.plan === "member" ? '<span class="badge m">' + (user.is_admin ? "Владелец" : "Участник") + "</span>" :
    '<span class="badge">Проба ' + user.trial_used + "/" + (Number(user.trial_used || 0) + Number(user.trial_left || 0)) + "</span>";
  return '<div class="usr"><div class="row"><b>' + esc(user.n) + "</b>" + badge + "</div>" +
    '<p class="muted small">ID ' + esc(user.id) + (user.plan === "member" ? " · сегодня " + user.t + "/" + user.lim : " · осталось " + esc(user.trial_left)) +
    " · скриптов " + user.g + " · сохранено " + user.s + (user.bonus ? " · бонус " + user.bonus : "") + "</p>" +
    (user.is_admin ? "" : '<div class="urow">' +
      '<button class="' + (user.approved ? "" : "main") + '" data-act="access" data-id="' + user.id + '" data-v="' + (user.approved ? "0" : "1") + '">' +
        ic(user.approved ? "x" : "key") + "<span>" + (user.approved ? "Закрыть доступ" : "Выдать доступ") + "</span></button>" +
      '<button data-act="edit" data-id="' + user.id + '">' + ic("edit") + "<span>Лимит</span></button>" +
      '<button data-act="bonus" data-id="' + user.id + '" data-v="5">' + ic("plus") + "<span>+5 генераций</span></button>" +
      '<button data-act="ban" data-id="' + user.id + '" data-v="' + (user.banned ? "0" : "1") + '">' + ic("ban") + "<span>" + (user.banned ? "Разбанить" : "Забанить") + "</span></button>" +
      (S.delConfirm === user.id
        ? '<button class="danger" data-act="udel" data-id="' + user.id + '">' + ic("trash") + "<span>Точно удалить?</span></button>"
        : '<button class="danger" data-act="udelask" data-id="' + user.id + '">' + ic("trash") + "<span>Удалить</span></button>") +
      "</div>") +
    (editing
      ? '<div class="edit"><div class="row"><span class="muted small">Дневной лимит: <b>' +
        S.editVal + '</b></span><div class="step"><button data-act="limd" data-v="-5" aria-label="Меньше">−</button>' +
        '<button data-act="limd" data-v="5" aria-label="Больше">+</button></div></div>' +
        '<div class="chips">' + limitChips([0, 10, 20, 50, 100, 200]).map(function (value) {
          return '<button class="chip ' + (S.editVal === value ? "on" : "") + '" data-act="limset" data-v="' + value + '">' + value + "</button>";
        }).join("") + '</div><div class="row g"><button class="ghost" data-act="limcancel">Отмена</button><button class="ghost go" data-act="limsave">Сохранить</button></div></div>'
      : "") + "</div>";
}

var DEF_SCOPES = [
  ["standard", "Новым и со стандартным", "Новым участникам и тем, у кого стоял прежний стандартный лимит. Лимиты, которые вы ставили вручную, останутся."],
  ["new", "Только новым", "Только новым участникам и новым ключам. У тех, кто уже есть, лимит не изменится."],
  ["all", "Всем", "Всем участникам сразу — даже тем, кому вы ставили лимит вручную."]
];

function limitChips(base) {
  var list = base.slice();
  if (list.indexOf(S.defLimit) < 0) list.push(S.defLimit);
  return list.sort(function (a, b) { return a - b; });
}

function defaultLimitCard() {
  var scope = DEF_SCOPES.filter(function (item) { return item[0] === S.defScope; })[0] || DEF_SCOPES[0];
  return '<div class="card"><div class="row"><h3>Лимит по умолчанию</h3><span class="badge m">' + esc(S.defLimit) + " в день</span></div>" +
    '<p class="muted small">Столько генераций в день получает каждый новый участник — при выдаче доступа и по новому ключу.</p>' +
    (S.defOpen
      ? '<div class="edit"><div class="row"><span class="muted small">Новый лимит: <b>' + esc(S.defVal) + '</b></span><div class="step">' +
        '<button data-act="defd" data-v="-5" aria-label="Меньше">−</button><button data-act="defd" data-v="5" aria-label="Больше">+</button></div></div>' +
        '<div class="chips">' + [5, 10, 20, 30, 50, 100].map(function (value) {
          return '<button class="chip ' + (S.defVal === value ? "on" : "") + '" data-act="defset" data-v="' + value + '">' + value + "</button>";
        }).join("") + "</div>" +
        '<p class="muted small" style="margin:12px 0 6px">Кому поменять</p><div class="chips scope">' + DEF_SCOPES.map(function (item) {
          return '<button class="chip ' + (S.defScope === item[0] ? "on" : "") + '" data-act="defscope" data-v="' + item[0] + '">' + item[1] + "</button>";
        }).join("") + '</div><p class="muted small" style="margin-top:8px">' + esc(scope[2]) + "</p>" +
        '<div class="row g"><button class="ghost" data-act="defcancel">Отмена</button><button class="ghost go" data-act="defsave">Сохранить</button></div></div>'
      : '<button class="btn" data-act="defopen">' + ic("edit") + "Изменить</button>") + "</div>";
}

function adminUsers() {
  var query = S.userQuery.trim().toLowerCase();
  var users = (S.users || []).filter(function (user) {
    return !query || String(user.n).toLowerCase().indexOf(query) >= 0 || String(user.id).indexOf(query) >= 0;
  });
  var members = S.users.filter(function (u) { return u.plan === "member"; }).length;
  var trials = S.users.filter(function (u) { return u.plan === "trial" && !u.banned; }).length;
  var banned = S.users.filter(function (u) { return u.banned; }).length;
  return tiles([["Участников", members], ["На пробе", trials], ["Забанено", banned], ["Всего", S.users.length]]) +
    defaultLimitCard() +
    '<div class="card"><h3>Выдать полный доступ</h3><form id="grant-form" class="form"><div class="two">' +
    '<input name="query" required placeholder="@username / ID" aria-label="Пользователь">' +
    '<input name="limit" type="number" min="1" max="5000" placeholder="Лимит/день: ' + esc(S.defLimit) + '" aria-label="Лимит генераций в день"></div>' +
    '<button class="btn main" type="submit">' + ic("plus") + "Выдать</button></form>" +
    '<p class="muted small">По @username — если человек уже нажимал /start. Иначе — по ID или создайте ключ.</p></div>' +
    '<div class="card"><h3>Пользователи</h3><input id="user-q" value="' + esc(S.userQuery) + '" placeholder="Поиск по @username или ID" autocomplete="off">' +
    '<div class="ulist">' + (users.length ? users.map(userRow).join("") : '<p class="muted">Никого не найдено.</p>') + "</div></div>";
}

function adminKeys() {
  return '<div class="card"><h3>Новый ключ доступа</h3><form id="key-create" class="form">' +
    '<label>Для кого (необязательно)<input name="for_user" placeholder="@username или ID" maxlength="64"></label>' +
    '<div class="two"><label>Генераций в день<input name="limit" type="number" min="0" max="5000" value="' + esc(S.defLimit) + '"></label>' +
    '<label>Бонус генераций<input name="bonus" type="number" min="0" max="1000" value="0"></label></div>' +
    '<div class="two"><label>Активаций<input name="uses" type="number" min="1" max="1000" value="1"></label>' +
    '<label>Заметка<input name="note" maxlength="120" placeholder="например, оплатил"></label></div>' +
    '<button class="btn main" type="submit">' + ic("key") + "Создать ключ</button></form>" +
    (S.newKey ? '<div class="card" style="margin-bottom:0"><p class="muted small">Ключ создан. Пользователь вводит его в приложении или командой /key.</p><div class="row g"><span class="code">' + esc(S.newKey) +
      '</span><button class="ghost" style="flex:none" data-act="copykey" data-v="' + esc(S.newKey) + '">' + ic("copy") + "Копировать</button></div></div>" : "") +
    "</div>" +
    '<div class="card"><h3>Ключи</h3>' + (S.keys.length ? S.keys.map(function (key) {
      return '<div class="usr"><div class="row"><span class="code">' + esc(key.code) + '</span><button class="chip mini" data-act="delkey" data-v="' + esc(key.code) + '">' + ic("trash") + "</button></div>" +
        '<p class="muted small">' + (key.for_user ? "для " + esc(key.for_user) + " · " : "для любого · ") +
        (key.daily_limit ? "лимит " + key.daily_limit + " · " : "") + (key.bonus ? "+" + key.bonus + " генераций · " : "") +
        "осталось активаций " + key.uses_left + (key.used_by ? " · активировали: " + esc(key.used_by) : "") +
        (key.note ? " · " + esc(key.note) : "") + "</p></div>";
    }).join("") : '<p class="muted">Ключей пока нет.</p>') + "</div>";
}

function libForm(item) {
  item = item || { category: S.purposes[0] ? S.purposes[0].id : "first", title: "", body: "", free: false };
  return '<form id="lib-form" data-id="' + (item.id || "") + '" class="form">' +
    '<select name="category" aria-label="Категория">' + S.purposes.map(function (p) {
      return '<option value="' + esc(p.id) + '"' + (p.id === item.category ? " selected" : "") + ">" + esc(p.title) + "</option>";
    }).join("") + "</select>" +
    '<input name="title" value="' + esc(item.title) + '" maxlength="80" required placeholder="Название скрипта" aria-label="Название">' +
    '<textarea name="body" rows="9" maxlength="4000" required placeholder="Текст скрипта. Пометки вроде [Имя] пользователь заменит сам.">' + esc(item.body) + "</textarea>" +
    '<label class="chk"><input type="checkbox" name="free"' + (item.free ? " checked" : "") + '>Открыт для пробного доступа</label>' +
    '<div class="tools"><button class="main" type="submit">Сохранить</button><button type="button" data-act="lcancel">Отмена</button></div></form>';
}

function adminLibrary() {
  var list = S.adminLib || [];
  return '<div class="card"><div class="row"><h3 style="margin:0">Библиотека <span class="muted">' + list.length + "</span></h3>" +
    '<button class="chip mini" data-act="lnew">' + ic("plus") + (S.libNew ? "Закрыть" : "Добавить") + "</button></div>" +
    (S.libNew ? '<div style="margin-top:12px">' + libForm(null) + "</div>" : "") + "</div>" +
    '<div class="card scr-list">' + (list.length ? list.map(function (item) {
      if (S.libEdit === item.id) return '<div class="scr">' + libForm(item) + "</div>";
      return '<div class="scr"><div class="scr-head"><b>' + esc(item.title) + '</b><span class="tag">' + esc(purposeTitle(item.category)) + "</span></div>" +
        (item.free ? '<p class="meta">Открыт для пробного доступа</p>' : "") +
        '<p class="scr-text clamp">' + esc(item.body) + "</p>" +
        '<div class="tools"><button data-act="ledit" data-id="' + item.id + '">' + ic("edit") + "Изменить</button>" +
        (S.libDel === item.id
          ? '<button class="danger" data-act="ldel" data-id="' + item.id + '">' + ic("trash") + "Точно удалить?</button>"
          : '<button class="danger" data-act="ldelask" data-id="' + item.id + '">' + ic("trash") + "Удалить</button>") + "</div></div>";
    }).join("") : '<p class="muted">Библиотека пуста. Добавьте первый скрипт.</p>') + "</div>";
}

function adminRequests() {
  var items = S.requests || [];
  return '<div class="card"><h3>Последние запросы</h3>' + (items.length ? items.map(function (r) {
    return '<div class="req"><div class="row"><b>' + esc(r.who) + '</b><span class="badge' + (r.source === "ai" ? " m" : "") + '">' + (r.source === "ai" ? "Нейросеть" : "Шаблон") + "</span></div>" +
      '<p class="muted small">' + esc(r.purpose_title) + (r.niche ? " · " + esc(r.niche) : "") + " · " + esc(SHORT_CH[r.channel] || r.channel) + " · " + esc(new Date(r.created_at * 1000).toLocaleString("ru-RU")) + "</p></div>";
  }).join("") : '<p class="muted">Запросов пока нет.</p>') + "</div>" +
    '<p class="muted small">Тексты скриптов не хранятся — виден только запрос: кто, для чего и какая ниша.</p>';
}

/*__COPIED_ADMIN__*/

/* Поиск в админке: обновляем только список, а поле ввода не трогаем —
   иначе на Android-клавиатурах ломается набор (буквы двоятся или пропадают). */
function refreshAdminList(input) {
  var tmp = document.createElement("div");
  tmp.innerHTML = vAdmin();
  var fresh = tmp.querySelector("#" + input.id);
  var freshList = fresh && fresh.parentNode.querySelector(".ulist");
  var list = input.parentNode.querySelector(".ulist");
  if (freshList && list) list.innerHTML = freshList.innerHTML;
}

function vAdmin() {
  if (!S.admin) return '<section class="screen"><div class="card empty">Нет доступа.</div></section>';
  var views = {
    overview: adminOverview, users: adminUsers, members: adminMembers, library: adminLibrary,
    keys: adminKeys, broadcast: broadcastCard, requests: adminRequests, errors: adminErrors
  };
  return '<section class="screen"><h2>Админ-панель</h2><div class="atabs-grid">' + ADMIN_TABS.map(function (item) {
    return '<button class="chip ' + (S.atab === item[0] ? "on" : "") + '" data-act="atab" data-v="' + item[0] + '">' + item[1] + "</button>";
  }).join("") + "</div>" + (views[S.atab] || adminOverview)() + "</section>";
}

/* ---------- Отрисовка ---------- */

function render(keepScroll) {
  var oldScroll = window.scrollY;
  var views = { home: vHome, library: vLibrary, create: vCreate, saved: vSaved, faq: vFaq, admin: vAdmin };
  if (S.tab === "admin" && !S.admin) S.tab = "home";
  var strips = keepScroll ? saveStrips($("#app")) : {};
  $("#app").classList.toggle("still", Boolean(keepScroll));
  $("#app").innerHTML = views[S.tab]();
  restoreStrips(strips, $("#app"));
  $("#tabs").innerHTML = TABS.filter(function (tab) {
    return tab[0] !== "admin" || S.admin;
  }).map(function (tab) {
    return '<button class="' + (S.tab === tab[0] ? "on" : "") +
      '" data-act="tab" data-v="' + tab[0] + '">' + ic(tab[2]) + "<span>" + tab[1] + "</span></button>";
  }).join("");
  document.querySelectorAll(".num").forEach(function (element) {
    var value = Number(element.dataset.to) || 0;
    if (keepScroll) element.textContent = String(value);
    else countUp(element, value);
  });
  window.scrollTo(0, keepScroll ? oldScroll : 0);
}

function adminAction(path, body, message) {
  return api(path, { method: "POST", body: JSON.stringify(body) }).then(function (result) {
    return loadAdmin().then(function () {
      render(true);
      toast((result && result.message) || message);
    });
  }).catch(function (error) { toast(error.message); });
}

function findIn(list, id) {
  return list.filter(function (item) { return String(item.id) === String(id); })[0];
}

function openTab(value) {
  S.tab = value;
  if (value === "admin") {
    render();
    loadAdmin().then(function () { render(true); }).catch(function (error) { S.tab = "home"; render(); toast(error.message); });
  } else if (value === "library") {
    render();
    loadLibrary().then(function () { if (S.tab === "library") render(true); }).catch(function (error) { toast(error.message); });
  } else if (value === "saved") {
    render();
    loadSaved().then(function () { if (S.tab === "saved") render(true); }).catch(function (error) { toast(error.message); });
  } else if (value === "home") {
    render();
    loadMe().then(function () { if (S.tab === "home") render(true); }).catch(function () {});
  } else {
    render();
  }
}

function clickHandler(event) {
  var target = event.target;
  if (target.id === "sheet") { closeSheet(); return; }
  if (target.closest("[data-fmt]")) return;

  if (target.closest("#theme")) {
    hap();
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    return;
  }

  var link = target.closest(".ct a,.contact,a[data-ext]");
  if (link && tg) {
    if (/^https?:/.test(link.href)) {
      event.preventDefault();
      openLink(link.href);
    }
    return;
  }

  var stripButton = target.closest(".hs-btn");
  if (stripButton) {
    var track = stripButton.parentNode.querySelector(".hs-track");
    if (track) track.scrollBy({ left: Number(stripButton.dataset.hs) * Math.max(120, track.clientWidth * 0.7), behavior: "smooth" });
    return;
  }

  var button = target.closest("[data-act]");
  if (!button || button.disabled) return;
  hap();
  var action = button.dataset.act;
  var value = button.dataset.v;
  var id = button.dataset.id ? decodeURIComponent(button.dataset.id) : "";

  if (action === "tab") {
    openTab(value);
  } else if (action === "close") {
    closeSheet();
  } else if (action === "offer") {
    showOffer(S.access && S.access.trial_message);
  } else if (action === "libcat") {
    S.libCat = value;
    render(true);
  } else if (action === "lopen") {
    S.libOpen[id] = !S.libOpen[id];
    render(true);
  } else if (action === "lcopy") {
    var item = findIn(S.lib, id);
    if (item && !item.locked) copyText(item.body);
  } else if (action === "lsave") {
    var libItemData = findIn(S.lib, id);
    if (!libItemData || libItemData.locked) return;
    api("/api/saved", {
      method: "POST",
      body: JSON.stringify({ title: libItemData.title, body: libItemData.body, purpose: libItemData.category })
    }).then(function () { return loadSaved(); }).then(function () { toast("Сохранено во вкладке «Мои»."); })
      .catch(function (error) { toast(error.message); });
  } else if (action === "hint") {
    syncForm();
    S.form.niche = value;
    render(true);
  } else if (action === "purpose") {
    syncForm();
    S.form.purpose = value;
    render(true);
  } else if (action === "channel") {
    syncForm();
    S.form.channel = value;
    render(true);
  } else if (action === "tone") {
    syncForm();
    S.form.tone = value;
    render(true);
  } else if (action === "gen") {
    doGenerate(0);
  } else if (action === "genmore") {
    doGenerate((S.genVariant || 0) + 1);
  } else if (action === "editreq") {
    S.genState = "form";
    render();
  } else if (action === "copygen") {
    if (S.gen) copyText(S.gen.text);
  } else if (action === "savegen") {
    saveGenerated();
  } else if (action === "sopen") {
    S.savedOpen[id] = !S.savedOpen[id];
    render(true);
  } else if (action === "scopy") {
    var script = findIn(S.saved, id);
    if (script) copyText(script.body);
  } else if (action === "sedit") {
    S.savedEdit = Number(id);
    render(true);
  } else if (action === "scancel") {
    S.savedEdit = null;
    render(true);
  } else if (action === "sdel") {
    api("/api/saved/" + encodeURIComponent(id), { method: "DELETE" }).then(function () {
      return loadSaved();
    }).then(function () { render(true); toast("Скрипт удалён."); }).catch(function (error) { toast(error.message); });
  } else if (action === "atab") {
    S.atab = value;
    S.newKey = "";
    S.libNew = false;
    S.libEdit = null;
    render(true);
    loadAdmin().then(function () { render(true); }).catch(function (error) { toast(error.message); });
  } else if (action === "udelask") {
    S.delConfirm = Number(id);
    render(true);
    clearTimeout(S.delTimer);
    S.delTimer = setTimeout(function () { if (S.delConfirm === Number(id)) { S.delConfirm = null; if (S.tab === "admin") render(true); } }, 4000);
  } else if (action === "udel") {
    S.delConfirm = null;
    api("/api/admin/users/" + encodeURIComponent(id), { method: "DELETE" }).then(function () {
      return loadAdmin();
    }).then(function () { render(true); toast("Пользователь удалён и заблокирован в боте."); }).catch(function (error) { toast(error.message); });
  } else if (action === "bimg") {
    var file = $("#bc-file");
    if (file) file.click();
  } else if (action === "bimgdel") {
    S.bcImage = "";
    render(true);
  } else if (action === "edit") {
    var user = findIn(S.users, id);
    if (!user) return;
    S.editId = S.editId === user.id ? null : user.id;
    S.editVal = user.lim;
    render(true);
  } else if (action === "defopen") {
    S.defOpen = true; S.defVal = S.defLimit; S.defScope = "standard";
    render(true);
  } else if (action === "defcancel") {
    S.defOpen = false;
    render(true);
  } else if (action === "defd") {
    S.defVal = Math.max(0, Math.min(5000, S.defVal + Number(value)));
    render(true);
  } else if (action === "defset") {
    S.defVal = Number(value);
    render(true);
  } else if (action === "defscope") {
    S.defScope = value;
    render(true);
  } else if (action === "defsave") {
    button.disabled = true;
    api("/api/admin/settings/limit", { method: "POST", body: JSON.stringify({ limit: S.defVal, scope: S.defScope }) }).then(function (result) {
      S.defOpen = false;
      S.defLimit = Number(result.default_limit);
      return loadAdmin().then(function () { render(true); toast(result.message); });
    }).catch(function (error) { button.disabled = false; toast(error.message); });
  } else if (action === "limd") {
    S.editVal = Math.max(0, Math.min(5000, S.editVal + Number(value)));
    render(true);
  } else if (action === "limset") {
    S.editVal = Number(value);
    render(true);
  } else if (action === "limcancel") {
    S.editId = null;
    render(true);
  } else if (action === "limsave") {
    var editId = S.editId;
    S.editId = null;
    adminAction("/api/admin/users/" + encodeURIComponent(editId) + "/limit", { limit: S.editVal }, "Лимит обновлён.");
  } else if (action === "access") {
    adminAction("/api/admin/users/" + encodeURIComponent(id) + "/access", { approved: value === "1" },
      value === "1" ? "Полный доступ выдан." : "Полный доступ закрыт.");
  } else if (action === "bonus") {
    adminAction("/api/admin/users/" + encodeURIComponent(id) + "/bonus", { amount: Number(value) }, "Генерации добавлены.");
  } else if (action === "ban") {
    adminAction("/api/admin/users/" + encodeURIComponent(id) + "/ban", { banned: value === "1" },
      value === "1" ? "Пользователь заблокирован." : "Пользователь разблокирован.");
  } else if (action === "copykey" || action === "copyval") {
    copyText(value);
  } else if (action === "delkey") {
    api("/api/admin/keys/" + encodeURIComponent(value), { method: "DELETE" }).then(function () {
      return loadAdmin();
    }).then(function () { render(true); toast("Ключ удалён."); }).catch(function (error) { toast(error.message); });
  } else if (action === "lnew") {
    S.libNew = !S.libNew;
    S.libEdit = null;
    render(true);
  } else if (action === "ledit") {
    S.libEdit = Number(id);
    S.libNew = false;
    render(true);
  } else if (action === "lcancel") {
    S.libEdit = null;
    S.libNew = false;
    render(true);
  } else if (action === "ldelask") {
    S.libDel = Number(id);
    render(true);
    clearTimeout(S.libDelTimer);
    S.libDelTimer = setTimeout(function () { if (S.libDel === Number(id)) { S.libDel = null; if (S.tab === "admin") render(true); } }, 4000);
  } else if (action === "ldel") {
    S.libDel = null;
    api("/api/admin/library/" + encodeURIComponent(id), { method: "DELETE" }).then(function () {
      return Promise.all([loadAdmin(), loadLibrary()]);
    }).then(function () { render(true); toast("Скрипт удалён из библиотеки."); }).catch(function (error) { toast(error.message); });
  } else if (action === "refresh") {
    refreshAll().then(function () { toast("Данные обновлены."); }).catch(function (error) { toast(error.message); });
  }
}

document.addEventListener("click", clickHandler);
document.addEventListener("input", function (event) {
  var id = event.target.id;
  if (id === "g-details") {
    S.form.details = event.target.value;
    var count = $("#g-count");
    if (count) count.textContent = event.target.value.length + "/700";
  }
  if (id === "g-niche") S.form.niche = event.target.value;
  if (id === "bc-ed") S.bcHtml = event.target.innerHTML;
  if (id === "mem-q" || id === "user-q") {
    if (id === "mem-q") S.memberQuery = event.target.value; else S.userQuery = event.target.value;
    refreshAdminList(event.target);
  }
});
document.addEventListener("change", function (event) {
  if (event.target.id === "bc-file") {
    var file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { toast("Нужна картинка JPG, PNG или WEBP."); return; }
    shrinkImage(file).then(function (dataUrl) {
      S.bcImage = dataUrl;
      var ed = $("#bc-ed");
      if (ed) S.bcHtml = ed.innerHTML;
      render(true);
    }).catch(function () { toast("Не удалось открыть картинку."); });
  }
});
document.addEventListener("toggle", function (event) {
  var key = event.target.dataset && event.target.dataset.intro;
  if (key) S.intro[key] = event.target.open;
}, true);
document.addEventListener("keydown", function (event) {
  if (event.key === "Escape" && $("#sheet").classList.contains("show")) closeSheet();
});

document.addEventListener("submit", function (event) {
  var form = event.target;
  var id = form.id;
  if (!id) return;
  event.preventDefault();
  if (id === "key-form") {
    var code = formValue(form, "code").toUpperCase();
    if (code.length < 4) { toast("Введите ключ доступа."); return; }
    api("/api/key", { method: "POST", body: JSON.stringify({ code: code }) }).then(function (result) {
      closeSheet();
      return loadMe().then(function () { return loadLibrary().catch(function () {}); }).then(function () { render(); toast(result.message || "Ключ активирован."); });
    }).catch(function (error) { toast(error.message); });
  } else if (id === "saved-form") {
    var payload = { title: formValue(form, "title"), body: formValue(form, "body") };
    if (!payload.title || !payload.body) { toast("Заполните название и текст."); return; }
    api("/api/saved/" + encodeURIComponent(form.dataset.id), { method: "PUT", body: JSON.stringify(payload) }).then(function () {
      S.savedEdit = null;
      return loadSaved().then(function () { render(true); toast("Скрипт сохранён."); });
    }).catch(function (error) { toast(error.message); });
  } else if (id === "lib-form") {
    var data = {
      category: formValue(form, "category"), title: formValue(form, "title"), body: formValue(form, "body"),
      free: Boolean(form.querySelector('input[name="free"]').checked)
    };
    if (!data.title || !data.body) { toast("Заполните название и текст."); return; }
    var editingId = form.dataset.id;
    api("/api/admin/library" + (editingId ? "/" + encodeURIComponent(editingId) : ""), {
      method: editingId ? "PUT" : "POST", body: JSON.stringify(data)
    }).then(function () {
      S.libNew = false;
      S.libEdit = null;
      return Promise.all([loadAdmin(), loadLibrary()]).then(function () { render(true); toast("Библиотека обновлена."); });
    }).catch(function (error) { toast(error.message); });
  } else if (id === "grant-form") {
    var limit = formValue(form, "limit");
    adminAction("/api/admin/grant", { query: formValue(form, "query"), limit: limit ? Number(limit) : null }, "Доступ выдан.");
  } else if (id === "key-create") {
    api("/api/admin/keys", {
      method: "POST",
      body: JSON.stringify({
        for_user: formValue(form, "for_user"), limit: Number(formValue(form, "limit") || 0),
        bonus: Number(formValue(form, "bonus") || 0), uses: Number(formValue(form, "uses") || 1), note: formValue(form, "note")
      })
    }).then(function (result) {
      S.newKey = result.code;
      return loadAdmin().then(function () { render(true); toast("Ключ создан."); });
    }).catch(function (error) { toast(error.message); });
  } else if (id === "broadcast-form") {
    var ed = $("#bc-ed");
    var text = ed ? editorToTelegram(ed).replace(/\n{3,}/g, "\n\n").trim() : "";
    if (!text && !S.bcImage) { toast("Добавьте текст или картинку."); return; }
    var sendButton = form.querySelector('button[type="submit"]');
    if (sendButton) sendButton.disabled = true;
    api("/api/admin/broadcast", { method: "POST", body: JSON.stringify({ text: text, image: S.bcImage || "" }) }).then(function (result) {
      S.bcHtml = "";
      S.bcImage = "";
      render(true);
      toast(result.message || "Рассылка запущена.");
    }).catch(function (error) {
      if (sendButton) sendButton.disabled = false;
      toast(error.message);
    });
  }
});

function boot() {
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (_) {}
    setTheme(window.ccTheme ? window.ccTheme() : (tg.colorScheme === "light" ? "light" : "dark"));
  }
  refreshAll().then(appReady).catch(function (error) {
    appReady();
    var app = $("#app");
    var banned = error.detail && error.detail.code === "banned";
    app.innerHTML = '<section class="screen"><div class="card"><h2>' + (banned ? "Доступ закрыт" : "Не удалось открыть приложение") + "</h2>" +
      '<p class="muted">' + esc(error.message) + '</p><p class="muted small">' +
      (banned ? "" : error.status === 401
        ? "Откройте Mini App через бота в Telegram. Если окно было открыто долго, закройте его и откройте снова."
        : "Проверьте соединение и снова откройте приложение.") +
      "</p>" + (banned ? "" : '<button class="ghost" data-act="refresh">Повторить</button>') + "</div></section>";
    $("#tabs").innerHTML = "";
  });
}

setTheme(window.ccTheme ? window.ccTheme() : "dark");
render();
boot();
