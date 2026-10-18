"use strict";

var tg = window.Telegram && window.Telegram.WebApp;
var COUNTRIES = [
  { code: "RU", title: "Россия", cities: ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"] },
  { code: "UA", title: "Украина", cities: ["Киев", "Харьков", "Одесса"] },
  { code: "BY", title: "Беларусь", cities: ["Минск", "Гомель"] },
  { code: "KZ", title: "Казахстан", cities: ["Алматы", "Астана"] },
  { code: "UZ", title: "Узбекистан", cities: ["Ташкент", "Самарканд"] },
  { code: "KG", title: "Кыргызстан", cities: ["Бишкек", "Ош"] },
  { code: "AM", title: "Армения", cities: ["Ереван"] },
  { code: "AZ", title: "Азербайджан", cities: ["Баку"] },
  { code: "GE", title: "Грузия", cities: ["Тбилиси", "Батуми"] },
  { code: "MD", title: "Молдова", cities: ["Кишинёв"] },
  { code: "PL", title: "Польша", cities: ["Warszawa", "Kraków"] },
  { code: "LT", title: "Литва", cities: ["Vilnius", "Kaunas"] },
  { code: "DE", title: "Германия", cities: ["Berlin", "München"] },
  { code: "AE", title: "ОАЭ", cities: ["Dubai", "Abu Dhabi"] }
];
var DEFAULT_NICHES = [
  { id: 0, title: "Барбершопы" }, { id: 1, title: "Салоны красоты" },
  { id: 6, title: "Маникюр и ногти" }, { id: 2, title: "Автосервисы" },
  { id: 3, title: "Стоматологии" }, { id: 4, title: "Фитнес и спортзалы" },
  { id: 7, title: "Кофейни и кафе" }, { id: 8, title: "Рестораны" },
  { id: 9, title: "Ветклиники" }, { id: 10, title: "Языковые и детские школы" },
  { id: 5, title: "Своя ниша" }
];
var CUSTOM_NICHE = 5;
var STATUS_NAMES = {
  "new": "Новый", "written": "Написал", "replied": "Ответил",
  "rejected": "Отказ", "client": "Клиент"
};
var FILTERS = [
  ["all", "Все"], ["new", "Новые"], ["written", "Написал"],
  ["replied", "Ответил"], ["rejected", "Отказ"], ["client", "Клиенты"]
];
var KINDS = [["first", "Первое"], ["short", "Короткое"], ["detailed", "Подробное"], ["call", "Звонок"], ["followup", "Повторное"]];
var TABS = [
  ["search", "Поиск", "search"], ["leads", "Лиды", "list"],
  ["scripts", "Скрипты", "doc"], ["stats", "Статистика", "chart"],
  ["faq", "Вопросы", "help"], ["admin", "Админ", "shield"]
];
var ADMIN_TABS = [["users", "Пользователи"], ["members", "Участники"], ["keys", "Ключи"], ["leads", "Все лиды"], ["overview", "Статистика"], ["blocked", "Чёрный список"], ["errors", "Ошибки"]];
var SUPPORT_TELEGRAM = "SUN9ISE";
var JOIN_URL = "/#join"; // тарифы C&C Family в общем мини-аппе
var NOT_FOUND = "не найдено";
var leads = [];
var S = {
  tab: "search", country: "RU", city: "", niche: 0, custom: "",
  flt: "all", count: 15, used: 0, limit: 35, filter: "all",
  admin: false, name: "", username: "", stats: {}, access: null, niches: DEFAULT_NICHES,
  users: [], editId: null, editVal: 35, loading: false, defLimit: 35, defVal: 35, defScope: "standard", defOpen: false,
  progress: null, requestSeq: 0, shown: 0, open: {},
  scriptNiche: 0, scripts: [], myScripts: [], scrMode: "niche", myKind: "all", myQuery: "", scriptEdit: null, scriptOpen: {}, scrIntro: true,
  genLead: null, genKind: "first", genVariant: 0, sheetSaved: false, sheetNiche: "",
  atab: "users", keys: [], adminLeads: [], adminQuery: "", overview: null, blocked: [], errors: null, userQuery: "",
  trialOffer: null, newKey: "",
  picker: null, members: [], memberQuery: "", delConfirm: null, bcHtml: "", bcImage: "",
  dispFound: 0, dispChecked: 0, finalFound: null, finishFrom: 0, tipIndex: 0, qOpen: false
};
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
var isTrial = function () { return S.access && S.access.plan === "trial"; };
var trialOver = function () { return isTrial() && S.access.searches_left <= 0; };
var remaining = function () {
  if (isTrial()) return S.access.searches_left > 0 ? S.access.trial_leads : 0;
  return Math.max(0, S.limit - S.used);
};
var COUNTS = [5, 10, 15];
var countOptions = function (rest) {
  if (isTrial()) return rest > 0 ? [S.access.trial_leads] : [];
  var values = COUNTS.filter(function (value) { return value <= rest; });
  if (rest > 0 && rest < 15 && values.indexOf(rest) < 0) values.push(rest);
  return values.sort(function (a, b) { return a - b; });
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
function pickBtn(key, value, label) {
  return '<button type="button" class="pick' + (S.picker === key ? " open" : "") + '" data-act="pick" data-v="' + key + '"' +
    (label ? ' aria-label="' + esc(label) + '"' : "") + "><span>" + esc(value) + '</span><i class="chv">' + SVG_DOWN + "</i></button>";
}

function currentCountry() {
  return COUNTRIES.filter(function (item) { return item.code === S.country; })[0] || COUNTRIES[0];
}

function pickerOptions(key) {
  if (key === "country") {
    return { title: "Страна", items: COUNTRIES.map(function (item) { return [item.code, item.title, item.code]; }), value: S.country };
  }
  if (key === "city") {
    var cities = currentCountry().cities || [];
    return {
      title: "Город — " + currentCountry().title,
      items: [["", "Все крупные города", ""]].concat(cities.map(function (name) { return [name, name, ""]; })),
      value: S.city
    };
  }
  if (key === "niche") {
    return {
      title: "Ниша",
      items: S.niches.map(function (item) { return [String(item.id), item.title, ""]; }),
      value: String(S.niche)
    };
  }
  return {
    title: "Ниша",
    items: S.niches.filter(function (item) { return item.id !== CUSTOM_NICHE; }).map(function (item) { return [String(item.id), item.title, ""]; }),
    value: String(S.scriptNiche)
  };
}

function normalizeSearch(text) {
  return String(text || "").toLowerCase().replace(/ё/g, "е").trim();
}

function openPicker(key) {
  var data = pickerOptions(key);
  S.picker = key;
  document.querySelectorAll(".pick").forEach(function (node) { node.classList.toggle("open", node.dataset.v === key); });
  var searchable = data.items.length > 12;
  openSheet('<div class="top"><h2>' + esc(data.title) + '</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' + ic("x") + "</button></div>" +
    (searchable ? '<input id="psearch" class="psearch" placeholder="Поиск" autocomplete="off" aria-label="Поиск по списку">' : "") +
    '<div class="plist" id="plist">' + data.items.map(function (item) {
      var on = String(item[0]) === String(data.value);
      return '<button type="button" class="' + (on ? "on" : "") + '" data-act="pickset" data-k="' + key + '" data-v="' + esc(item[0]) +
        '" data-s="' + esc(normalizeSearch(item[1] + " " + item[2])) + '"><span>' + esc(item[1]) + "</span>" +
        (item[2] ? "<small>" + esc(item[2]) + "</small>" : "") + '<i class="ok">' + SVG_CHECK + "</i></button>";
    }).join("") + '</div><p class="pempty" id="pempty" hidden>Ничего не найдено</p>');
  var active = document.querySelector("#plist .on");
  if (active && active.scrollIntoView) active.scrollIntoView({ block: "center" });
}

function applyPick(key, value) {
  if (key === "country") {
    if (S.country !== value) S.city = "";
    S.country = value;
  } else if (key === "city") {
    S.city = value;
  } else if (key === "niche") {
    S.niche = Number(value);
  } else if (key === "sniche") {
    S.scriptNiche = Number(value);
    S.scripts = [];
    S.scriptEdit = null;
    S.scriptOpen = {};
    loadScripts().then(function () { if (S.tab === "scripts") render(true); }).catch(function (error) { toast(error.message); });
  }
  closeSheet();
  render(true);
}
var nicheTitle = function (id) {
  var found = S.niches.filter(function (item) { return item.id === id; })[0];
  return found ? found.title : "";
};
var leadsToView = function (lead) {
  return {
    id: lead.id,
    name: lead.name || "Без названия",
    country: lead.country || "",
    city: lead.city || "",
    phone: lead.phone || "",
    site: lead.site || "none",
    url: lead.url || "",
    c: lead.c || {},
    reasons: Array.isArray(lead.reasons) ? lead.reasons : [],
    hot: Number(lead.hot) || 0,
    status: lead.status || "new",
    need: lead.need || "",
    explain: lead.explain || "",
    info: lead.info || {},
    niche: lead.niche || "",
    source: lead.source || ""
  };
};

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

function loadMe() {
  return api("/api/me").then(function (me) {
    S.name = me.name || "";
    S.username = me.username || "";
    S.admin = Boolean(me.is_admin);
    S.limit = Number(me.limit) || 0;
    S.used = Number(me.used) || 0;
    S.access = me.access || null;
    if (me.access && me.access.join) JOIN_URL = me.access.join;
    if (me.access && me.access.contact) SUPPORT_TELEGRAM = me.access.contact;
    if (Array.isArray(me.niches) && me.niches.length) S.niches = me.niches;
    if (Array.isArray(me.countries) && me.countries.length) COUNTRIES = me.countries;
    if (S.tab === "admin" && !S.admin) S.tab = "search";
    return me;
  });
}

function loadLeads() {
  return api("/api/leads?status=all&limit=1000").then(function (data) {
    leads = (data.leads || []).map(leadsToView);
    return leads;
  });
}

function loadStats() {
  return api("/api/stats").then(function (stats) {
    S.stats = stats || {};
    return S.stats;
  });
}

function loadScripts() {
  return Promise.all([
    api("/api/scripts?niche=" + encodeURIComponent(S.scriptNiche)),
    api("/api/scripts?own=1")
  ]).then(function (res) {
    S.scripts = res[0].scripts || [];
    S.myScripts = res[1].scripts || [];
    return S.scripts;
  });
}
function findScript(id) {
  return (S.scripts || []).concat(S.myScripts || []).filter(function (item) { return String(item.id) === String(id); })[0];
}

function refreshAll() {
  return loadMe().then(function () {
    return Promise.all([loadLeads(), loadStats()]);
  }).then(function () {
    if (S.tab === "admin" && S.admin) return loadAdmin();
  }).then(function () { render(); });
}

/* ---------- Поиск ---------- */

function accessCard() {
  if (trialOver()) return trialOfferCard(S.access.trial_message);
  if (isTrial()) {
    return '<div class="card access"><div class="row"><span>Пробный доступ</span><b>' +
      S.access.searches_left + " " + plural(S.access.searches_left, "запрос", "запроса", "запросов") +
      '</b></div><p class="muted small">До ' + S.access.trial_leads +
      ' лидов за запрос. Дальше — в команде C&amp;C Family или по ключу.</p></div>';
  }
  var rest = remaining();
  var usedPercent = S.limit ? Math.min(100, Math.round(S.used / S.limit * 100)) : 0;
  return '<div class="card"><div class="row"><span>Лимит на сегодня</span><b>' +
    S.used + " / " + S.limit + '</b></div><div class="bar"><i style="width:' +
    usedPercent + '%"></i></div><p class="muted small">Осталось ' + rest +
    '. Обновление по времени сервера.</p></div>';
}

function trialOfferCard(message) {
  var text = message || ("Пробный доступ закончился.\nЧтобы продолжить получать лиды и пользоваться Parser C&C, вступите в команду C&C Family,\nподробности можно узнать у @" + SUPPORT_TELEGRAM + ".");
  return '<div class="card offer"><p>' + esc(text) + '</p><div class="btns">' +
    '<a class="btn main" data-ext href="' + esc(JOIN_URL) + '" target="_blank" rel="noopener">' + ic("users") + "Вступить в команду</a>" +
    '<a class="btn" data-ext href="https://t.me/' + esc(SUPPORT_TELEGRAM) + '" target="_blank" rel="noopener">' + ic("plus") + "Докупить запросы</a>" +
    '<a class="btn" data-ext href="https://t.me/' + esc(SUPPORT_TELEGRAM) + '" target="_blank" rel="noopener">' + ic("send") + "Написать @" + esc(SUPPORT_TELEGRAM) + "</a></div>" +
    '<form id="key-form" class="keyform"><input name="code" placeholder="Ключ доступа CC-…" autocomplete="off" maxlength="64" aria-label="Ключ доступа">' +
    '<button class="btn" type="submit">' + ic("key") + "Ввести</button></form></div>";
}

function plural(n, one, few, many) {
  var mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

function vSearch() {
  var rest = remaining();
  var options = countOptions(rest);
  if (options.indexOf(S.count) < 0) S.count = options.indexOf(15) >= 0 ? 15 : (options[0] || 0);
  var hello = S.name ? "Привет, " + esc(S.name) : "Привет";
  var country = currentCountry();
  return '<section class="screen"><div class="hello">' + hello +
    '<small>Найди бизнесы, которым может быть нужен сайт или ТГ-бот</small></div>' +
    accessCard() +
    '<button class="fire" data-act="demand">' + ic("fire") +
    '<span>Какие ниши сейчас требуют сайт/бот?<small>Оценка спроса по нишам</small></span>' +
    ic("chev", "chev") + "</button>" +
    "<h3>Страна</h3>" + pickBtn("country", country.title, "Страна") +
    "<h3>Город или регион</h3>" + pickBtn("city", S.city || "Все крупные города", "Город") +
    "<h3>Ниша</h3>" + pickBtn("niche", nicheTitle(S.niche) || "Выберите нишу", "Ниша") +
    (S.niche === CUSTOM_NICHE
      ? '<input id="cn" value="' + esc(S.custom) +
        '" placeholder="Слово из названия, например шиномонтаж" maxlength="80">'
      : "") +
    '<h3>Сколько</h3><div class="seg">' +
    (options.length
      ? options.map(function (value) {
        return '<button class="' + (S.count === value ? "on" : "") +
          '" data-act="count" data-v="' + value + '">' + value + "</button>";
      }).join("")
      : '<button disabled>' + (isTrial() ? "Пробный доступ закончился" : "Лимит исчерпан") + "</button>") +
    '</div><p class="count-tip">Совет: ищите по 5 бизнесов в разных городах — так больше шансов найти клиента.</p>' +
    '<button class="cta" data-act="go" ' +
    (rest > 0 && S.count && !S.loading ? "" : "disabled") +
    '>Найти ' + (S.count || "") + " " + plural(S.count || 0, "бизнес", "бизнеса", "бизнесов") + "</button></section>";
}

var TIPS = [
  "Собираю организации из открытых карт…",
  "Отбрасываю закрытые и переехавшие бизнесы.",
  "Проверяю, что номер телефона настоящий и по нему можно позвонить.",
  "Убираю бизнесы, которые уже выданы другим участникам.",
  "Каждый найденный бизнес закрепится только за вами.",
  "Совет: в первом сообщении коротко представьтесь и сразу назовите пользу для бизнеса.",
  "Совет: перед звонком откройте бизнес на карте и посмотрите отзывы — будет о чём поговорить.",
  "Готовые тексты для первого сообщения — во вкладке «Скрипты».",
  "Кнопка «Скрипт» в карточке напишет текст под конкретный бизнес.",
  "Отмечайте статусы лидов — так видно, сколько из них стали клиентами.",
  "Совет: если не ответили, напишите повторно через 2–3 дня — это нормально.",
  "В небольших городах конкуренция за клиентов обычно ниже."
];
var DISCLAIMER = "Бот может ошибаться: данные на картах обновляются не сразу, поэтому название, адрес или номер иногда бывают устаревшими. " +
  "Если номер не отвечает — откройте бизнес на карте и проверьте актуальные контакты.";

function loadingView() {
  var progress = S.progress || { found: 0, checked: 0, total: 1 };
  return '<section class="screen center"><div class="beat"><i class="bird"></i></div>' +
    "<h2>Ищу и проверяю бизнесы</h2>" +
    '<div class="glow"><i id="pb" style="width:' + Math.max(3, S.shown) + '%"></i></div>' +
    '<p class="counts"><span>Найдено <b id="pfound">' + S.dispFound + "</b> из " + progress.total +
    '</span><span>Проверено <b id="pchecked">' + S.dispChecked + "</b></span></p>" +
    '<p class="tipline" id="ptip">' + esc(TIPS[S.tipIndex % TIPS.length]) + "</p>" +
    '<p class="muted small loadnote">Каждый клиент проверяется вживую, поэтому поиск занимает 1–5 минут.' +
    '<button class="qbtn" data-act="qinfo" aria-label="Важно знать" aria-expanded="' + (S.qOpen ? "true" : "false") + '">?</button></p>' +
    '<p class="qpop" id="qpop"' + (S.qOpen ? "" : " hidden") + ">" + esc(DISCLAIMER) + "</p></section>";
}

function paintLoading() {
  var bar = $("#pb"), found = $("#pfound"), checked = $("#pchecked");
  if (bar) bar.style.width = S.shown.toFixed(1) + "%";
  if (found) found.textContent = S.dispFound;
  if (checked) checked.textContent = S.dispChecked;
}

function stopLoadingLoop() {
  if (S.loop) clearInterval(S.loop);
  S.loop = null;
}

/* Плавная анимация поиска: «найдено» растёт по одному, полоска доходит до конца ровно тогда,
   когда счётчик дошёл до итога (например, 50 из 50). */
function startLoadingLoop() {
  stopLoadingLoop();
  var last = performance.now();
  var acc = 0;
  var tipAt = last;
  var finished = false;
  if (!S.startedAt) S.startedAt = last;
  S.loop = setInterval(function () {
    var now = performance.now();
    var dt = Math.min(200, now - last);
    last = now;
    var progress = S.progress;
    if (!progress) return;
    var total = Math.max(1, progress.total);
    var finishing = S.finalFound != null;
    var target = finishing ? S.finalFound : Math.min(progress.found, total);
    var stepMs = finishing ? Math.max(22, Math.min(110, 1100 / Math.max(1, target - S.dispFound))) : 150;
    acc += dt;
    while (acc >= stepMs && S.dispFound < target) { S.dispFound += 1; acc -= stepMs; }
    if (S.dispFound >= target) acc = 0;
    // «Проверено»: растёт неравномерно и доходит до своего итога (50–150) ровно к концу поиска.
    var elapsed = (now - S.startedAt) / 1000;
    var checkGoal;
    if (finishing) {
      var share = S.finalFound ? S.dispFound / S.finalFound : 1;
      checkGoal = Math.round(S.checkFrom + (S.checkTarget - S.checkFrom) * Math.min(1, share));
      if (S.dispFound >= target) checkGoal = S.checkTarget;
    } else {
      checkGoal = Math.floor(S.checkTarget * 0.88 * (1 - Math.exp(-elapsed / S.checkTau)));
    }
    S.checkGoal = Math.max(S.checkGoal || 0, checkGoal);
    if (S.dispChecked < S.checkGoal && Math.random() < (finishing ? 0.9 : S.checkPace)) {
      S.dispChecked += Math.max(1, Math.ceil((S.checkGoal - S.dispChecked) / (finishing ? 3 : 8)));
    }
    if (Math.random() < 0.02) S.checkPace = 0.15 + Math.random() * 0.6;
    if (finishing) {
      var part = S.finalFound ? S.dispFound / S.finalFound : 1;
      S.shown = Math.max(S.shown, S.finishFrom + (100 - S.finishFrom) * part);
    } else {
      S.shown += (90 - S.shown) * 0.00004 * dt;
      S.shown = Math.max(S.shown, 6 + S.dispFound / total * 82);
    }
    if (now - tipAt > 3800) {
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
    paintLoading();
    if (finishing && !finished && S.dispFound >= S.finalFound && S.dispChecked >= S.checkTarget) {
      finished = true;
      S.shown = 100;
      paintLoading();
      stopLoadingLoop();
      setTimeout(function () { if (S.onFinish) S.onFinish(); }, 450);
    }
  }, 40);
}

function doneText(found, total) {
  if (found >= total) return "Поиск завершён. Новых лидов: " + found + ".";
  if (!found) return "Новых бизнесов с телефоном здесь не нашлось. Попробуйте другой город или нишу.";
  return "Нашлось " + found + " из " + total + ": больше новых бизнесов с телефоном здесь нет. Попробуйте другой город или нишу.";
}

function go() {
  if (S.loading) return;
  var count = Number(S.count);
  if (!count || count > remaining()) {
    toast(isTrial() ? "Пробный доступ закончился." : "Доступно лидов на сегодня: " + remaining() + ".");
    return;
  }
  if (S.niche === CUSTOM_NICHE && !S.custom.trim()) {
    toast("Введите слово для своей ниши.");
    return;
  }

  var requestNumber = ++S.requestSeq;
  var payload = {
    country: S.country,
    city: S.city.trim(),
    niche: S.niche,
    custom: S.custom.trim(),
    flt: S.flt,
    count: count
  };
  S.loading = true;
  S.shown = 3;
  S.dispFound = 0;
  S.dispChecked = 0;
  S.finalFound = null;
  S.onFinish = null;
  S.qOpen = false;
  S.tipIndex = 0;
  S.startedAt = performance.now();
  S.checkTarget = 50 + Math.floor(Math.random() * 101);
  S.checkTau = 6 + Math.random() * 10;
  S.checkPace = 0.3 + Math.random() * 0.5;
  S.checkGoal = 0;
  S.checkFrom = 0;
  S.progress = { found: 0, checked: 0, total: count };
  render();
  startLoadingLoop();

  function stop(message, tab) {
    stopLoadingLoop();
    S.loading = false;
    S.tab = tab || "search";
    render();
    if (message) toast(message);
  }

  api("/api/search", { method: "POST", body: JSON.stringify(payload) })
    .then(function (result) {
      S.progress.total = Number(result.count) || count;
      var misses = 0;
      function poll() {
        if (requestNumber !== S.requestSeq) return;
        api("/api/jobs/" + encodeURIComponent(result.job_id)).then(function (job) {
          S.progress = {
            found: Number(job.found) || 0,
            checked: Number(job.checked) || 0,
            total: Number(job.total) || count
          };
          if (job.status === "done") {
            var found = Number(job.found) || 0;
            S.trialOffer = job.trial_over || null;
            var ready = Promise.all([loadMe(), loadLeads(), loadStats()]);
            S.onFinish = function () {
              ready.then(function () {
                S.filter = "all";
                stop(doneText(found, Number(job.total) || count), found ? "leads" : "search");
                if (S.trialOffer) showTrialOffer(S.trialOffer);
              }).catch(function (error) { stop(error.message); });
            };
            if (S.dispFound > found) S.dispFound = found;
            S.finishFrom = S.shown;
            S.checkFrom = S.dispChecked;
            S.finalFound = found;
            return;
          }
          if (job.status === "error") {
            stop(job.error || "Поиск завершился с ошибкой.");
            return;
          }
          misses = 0;
          setTimeout(poll, 900);
        }).catch(function (error) {
          // Короткий обрыв связи не прерывает поиск: он идёт на сервере, пробуем ещё.
          if (requestNumber !== S.requestSeq) return;
          misses += 1;
          if (misses <= 8 && (!error.status || error.status >= 500)) setTimeout(poll, 1500 * Math.min(misses, 4));
          else stop(error.message);
        });
      }
      poll();
    })
    .catch(function (error) {
      if (error.detail && error.detail.code === "trial_over") {
        stop("");
        loadMe().then(function () { render(); showTrialOffer(error.detail); });
        return;
      }
      stop(error.message);
    });
}

function showTrialOffer(detail) {
  openSheet('<div class="top"><h2>C&amp;C Family</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' +
    ic("x") + "</button></div>" + trialOfferCard(detail && detail.message));
}

/* ---------- Ниши со спросом ---------- */

function showDemand() {
  var head = '<div class="top"><h2>Каким нишам сейчас нужен сайт или бот</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' + ic("x") + "</button></div>";
  openSheet(head + '<div class="dots"><i></i><i></i><i></i></div>');
  api("/api/demand?country=" + encodeURIComponent(S.country)).then(function (data) {
    var items = data.items || [];
    var note = data.source === "ai"
      ? "Оценка нейросети по нашим нишам для выбранной страны. Обновляется раз в сутки."
      : "Оценка по опыту продаж сайтов и ботов в этих нишах.";
    setSheetBody(head + '<p class="lead-note">' + esc(note) + "</p>" +
      items.map(function (item, index) {
        return '<div class="dm"><div class="dm-top"><span class="dm-n">' + (index + 1) + '</span><b>' + esc(item.niche) +
          '</b><span class="score">' + esc(item.score) + "/10</span></div>" +
          '<p class="dm-why">' + esc(item.why) + "</p>" +
          (item.offer ? '<p class="dm-offer"><span>Что предложить:</span> ' + esc(item.offer) + "</p>" : "") +
          (item.id != null ? '<button class="btn small" data-act="pickniche" data-v="' + esc(item.id) + '">' + ic("search") + "Искать в этой нише</button>" : "") +
          "</div>";
      }).join(""));
  }).catch(function (error) {
    closeSheet();
    toast(error.message);
  });
}

/* ---------- Лиды ---------- */

function safeHttpLink(value) {
  try {
    var url = new URL(String(value || ""));
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch (_) { return ""; }
}

function leadPhones(lead) {
  var info = lead.info || {};
  var list = Array.isArray(info.phones) && info.phones.length ? info.phones : (lead.phone ? [lead.phone] : []);
  return list.filter(function (value, index) { return value && list.indexOf(value) === index; });
}

function telLink(phone, cls) {
  var dialable = String(phone || "").replace(/[^\d+]/g, "");
  return '<a class="' + (cls || "tel") + '" href="tel:' + esc(dialable) + '">' + ic("phone") + esc(phone) + "</a>";
}

function leadCard(lead, index) {
  var status = lead.status || "new";
  var phones = leadPhones(lead);
  var open = Boolean(S.open[lead.id]);
  var c = lead.c || {};
  var map = safeHttpLink(c.map || "");
  var address = c.address || (lead.info && lead.info.address) || "";
  return '<article class="card lead" style="--i:' + index + '">' +
    '<div class="lhead"><b class="lname">' + esc(lead.name) + "</b>" +
    '<button class="lx" data-act="leaddelask" data-id="' + encodeURIComponent(lead.id) + '" aria-label="Удалить лид">' + ic("x") + "</button></div>" +
    '<p class="meta">' + esc(lead.niche || "") + (lead.niche ? " · " : "") + esc(lead.city) + "</p>" +
    (address ? '<p class="addr">' + esc(address) + "</p>" : "") +
    '<div class="phones">' + (phones.length
      ? telLink(phones[0]) + (phones.length > 1
        ? '<button class="more-ph' + (open ? " on" : "") + '" data-act="phones" data-id="' + encodeURIComponent(lead.id) +
          '" aria-label="Другие номера">+' + (phones.length - 1) + ic("chev", "down") + "</button>"
        : "")
      : '<span class="meta">Телефон не указан на карте</span>') + "</div>" +
    (open && phones.length > 1 ? '<div class="ph-list">' + phones.slice(1).map(function (phone) { return telLink(phone, "tel alt"); }).join("") + "</div>" : "") +
    '<div class="acts">' +
    (map ? '<a class="btn main" data-ext href="' + esc(map) + '" target="_blank" rel="noopener">' + ic("pin") + "Открыть на карте</a>" : "") +
    '<button class="btn" data-act="leadscript" data-id="' + encodeURIComponent(lead.id) + '">' + ic("spark") + "Скрипт</button></div>" +
    '<div class="st">' + ["written", "replied", "rejected", "client"].map(function (key) {
      return '<button class="' + (status === key ? "on" : "") +
        '" data-act="status" data-id="' + encodeURIComponent(lead.id) +
        '" data-v="' + key + '">' + STATUS_NAMES[key] + "</button>";
    }).join("") + "</div></article>";
}

function vLeads() {
  var filtered = leads.filter(function (lead) {
    return S.filter === "all" || lead.status === S.filter;
  });
  return '<section class="screen"><div class="top"><h2>Лиды <small>' +
    esc(S.stats.found == null ? leads.length : S.stats.found) +
    '</small></h2><button class="icon-btn" data-act="export" aria-label="Скачать Excel">' +
    ic("download") + "</button></div>" +
    hstrip("filters", FILTERS.map(function (item) {
      return '<button class="chip ' + (S.filter === item[0] ? "on" : "") +
        '" data-act="filter" data-v="' + item[0] + '">' + item[1] + "</button>";
    }).join("")) +
    (isTrial() && leads.length ? trialMini() : "") +
    (filtered.length
      ? filtered.map(leadCard).join("")
      : '<div class="empty">' + ic("list") + "<p>" +
        (leads.length ? "В этом фильтре пока пусто" : "Здесь пока пусто") + "</p></div>") +
    (leads.length >= 1000
      ? '<p class="muted small" style="text-align:center">Показаны последние 1000 лидов. Полный список можно выгрузить в Excel.</p>'
      : "") +
    (leads.length ? sourceNote() : "") +
    "</section>";
}

function sourceNote() {
  var used = {};
  leads.forEach(function (lead) {
    used[lead.source || "osm"] = true;
    ((lead.info && lead.info.sources) || []).forEach(function (item) {
      var t = String(item.t || "");
      if (t.indexOf("Google") === 0) used.google = true;
      else if (t === "2ГИС") used.dgis = true;
      else used.osm = true;
    });
  });
  var parts = [];
  if (used.osm || used.geoapify) parts.push('<a data-ext href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>');
  if (used.google) parts.push("Google Maps");
  if (used.dgis) parts.push("2ГИС");
  parts.push("сайты самих компаний");
  return '<p class="muted small srcnote">Данные организаций: ' + parts.join(", ") + ".</p>";
}

function trialMini() {
  if (!trialOver()) return "";
  return '<div class="card offer"><div class="row"><b>Пробный доступ закончился</b></div>' +
    '<p class="muted small">Лиды остаются у вас. Чтобы искать дальше — вступите в C&amp;C Family.</p>' +
    '<div class="btns"><button class="btn main" data-act="offer">Подробнее</button></div></div>';
}

function generateLeadScript(lead, kind, variant) {
  kind = kind || "first";
  variant = variant || 0;
  S.genLead = lead.id;
  S.genKind = kind;
  S.genVariant = variant;
  var head = '<div class="top"><h2>Скрипт для «' + esc(lead.name) + '»</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' +
    ic("x") + "</button></div>" + hstrip("kinds", KINDS.map(function (item) {
      return '<button class="chip ' + (kind === item[0] ? "on" : "") + '" data-act="leadkind" data-id="' +
        encodeURIComponent(lead.id) + '" data-v="' + item[0] + '">' + item[1] + "</button>";
    }).join(""), "kinds");
  openSheet(head + '<div class="dots"><i></i><i></i><i></i></div><p class="meta center-text">Пишу скрипт для этого бизнеса…</p>');
  var seq = S.sheetSeq;
  api("/api/leads/" + encodeURIComponent(lead.id) + "/script", {
    method: "POST", body: JSON.stringify({ kind: kind, variant: variant })
  }).then(function (result) {
    if (seq !== S.sheetSeq) return; // окно уже закрыли или открыли другое
    S.sheetText = result.text || "";
    S.sheetSaved = false;
    S.sheetNiche = lead.niche;
    setSheetBody(head + copyCard(result.text) + genTools("leadmore", kind));
  }).catch(function (error) {
    if (seq !== S.sheetSeq) return;
    closeSheet();
    toast(error.message);
  });
}

function copyCard(text) {
  return '<div class="card tapcopy" data-act="copygen" role="button" tabindex="0" aria-label="Скопировать текст"><pre id="gen-text">' + esc(text) + "</pre></div>" +
    '<p class="copyhint">Нажми на текст, чтобы скопировать</p>';
}

function genTools(moreAction, kind) {
  return '<div class="tools"><button data-act="' + moreAction + '" data-v="' + kind + '">' + ic("spark") + "Ещё вариант</button>" +
    '<button id="save-gen" data-act="savegen" data-v="' + kind + '"' + (S.sheetSaved ? " disabled" : "") + ">" +
    ic("doc") + (S.sheetSaved ? "Сохранено" : "Сохранить в мои скрипты") + "</button></div>";
}

/* ---------- Скрипты ---------- */

function scrModeSwitch() {
  var mine = (S.myScripts || []).length;
  return '<div class="seg scr-mode"><button class="' + (S.scrMode !== "mine" ? "on" : "") + '" data-act="scrmode" data-v="niche">По нишам</button>' +
    '<button class="' + (S.scrMode === "mine" ? "on" : "") + '" data-act="scrmode" data-v="mine">Мои скрипты' + (mine ? " · " + mine : "") + "</button></div>";
}

function vMyScripts() {
  var all = S.myScripts || [];
  var kind = S.myKind || "all", q = (S.myQuery || "").trim().toLowerCase();
  var list = all.filter(function (item) {
    return (kind === "all" || item.kind === kind) &&
      (!q || (item.title + " " + item.body).toLowerCase().indexOf(q) >= 0);
  });
  var groups = [];
  list.forEach(function (item) {
    var g = groups.filter(function (x) { return x.niche === item.niche; })[0];
    if (!g) groups.push(g = { niche: item.niche, items: [] });
    g.items.push(item);
  });
  var kinds = [["all", "Все"]].concat(KINDS.filter(function (k) { return all.some(function (i) { return i.kind === k[0]; }); }));
  return '<section class="screen"><h2>Скрипты</h2>' + scrModeSwitch() +
    '<div class="card lib-head"><b class="lib-title">' + ic("doc") + "Библиотека моих скриптов</b>" +
    '<p class="meta">Всё, что ты изменил или сохранил из генератора, — по всем нишам в одном месте. ' +
    all.length + " " + plural(all.length, "скрипт", "скрипта", "скриптов") + ".</p></div>" +
    (all.length ? '<input id="my-q" class="lib-q" type="search" placeholder="Поиск по моим скриптам" value="' + esc(S.myQuery || "") + '">' +
      '<div class="chips lib-kinds">' + kinds.map(function (k) {
        return '<button class="chip' + (kind === k[0] ? " on" : "") + '" data-act="mykind" data-v="' + k[0] + '">' + esc(k[1]) + "</button>";
      }).join("") + "</div>" : "") +
    (list.length ? groups.map(function (g) {
      return '<div class="lib-niche"><b>' + esc(nicheTitle(g.niche) || "Без ниши") + "</b><span>" + g.items.length + "</span></div>" +
        '<div class="card scr-list">' + g.items.map(scriptItem).join("") + "</div>";
    }).join("") :
      '<div class="card lib-empty">' + ic("doc") + "<b>" + (all.length ? "Ничего не нашлось" : "Пока пусто") + "</b><p class=\"meta\">" +
      (all.length ? "Попробуй другое слово или тип скрипта." : "Нажми «Изменить» у любого скрипта или «Сохранить в мои скрипты» после генерации — он появится здесь.") +
      '</p>' + (all.length ? "" : '<button class="cta" data-act="scrmode" data-v="niche">К скриптам по нишам</button>') + "</div>") +
    "</section>";
}

function vScripts() {
  if (S.scrMode === "mine") return vMyScripts();
  var niches = S.niches.filter(function (item) { return item.id !== CUSTOM_NICHE; });
  var list = S.scripts || [];
  return '<section class="screen"><h2>Скрипты</h2>' + scrModeSwitch() +
    '<details class="intro"' + (S.scrIntro ? " open" : "") + ' data-intro="scripts"><summary>' + ic("info") + "Что можно делать на этой странице" + PM + "</summary>" +
    '<div class="intro-body">' +
    "<p>Здесь готовые тексты, с которых удобно начать общение с бизнесом.</p>" +
    '<ul class="steps">' +
    "<li><b>Выберите нишу</b> — для каждой есть 5 скриптов: первое сообщение, короткое, подробное, звонок и повторное.</li>" +
    "<li><b>Скопируйте</b> и замените [Название] и [Ваше имя] на свои данные.</li>" +
    "<li><b>Измените</b> любой скрипт под себя — он сохранится как ваш.</li>" +
    "<li><b>Сгенерируйте новый</b> вариант, если нужен другой текст.</li>" +
    "</ul>" +
    '<p class="meta">Для конкретного бизнеса нажмите «Скрипт» в карточке лида — текст напишется с его названием.</p>' +
    (S.admin ? '<p class="meta">Вы администратор: правка стандартного скрипта меняет его для всех.</p>' : "") +
    "</div></details>" +
    "<h3>Ниша</h3>" + pickBtn("sniche", nicheTitle(S.scriptNiche) || (niches[0] || {}).title || "", "Ниша") +
    '<div class="card scr-list">' + (list.length ? list.map(scriptItem).join("") : '<div class="dots"><i></i><i></i><i></i></div>') + "</div>" +
    '<div class="card"><h3>Сгенерировать новый</h3><p class="meta">Новый вариант для ниши «' +
    esc(nicheTitle(S.scriptNiche)) + '». Каждое нажатие — другой текст.</p><div class="tools">' + KINDS.map(function (item) {
      return '<button data-act="genniche" data-v="' + item[0] + '">' + ic("spark") + item[1] + "</button>";
    }).join("") + "</div></div></section>";
}

function scriptItem(item) {
  var editing = S.scriptEdit === item.id;
  var open = Boolean(S.scriptOpen[item.id]);
  var kindName = (KINDS.filter(function (k) { return k[0] === item.kind; })[0] || [0, item.kind])[1];
  if (editing) {
    return '<div class="scr"><form id="script-form" data-id="' + item.id + '" data-niche="' + item.niche + '" data-kind="' + esc(item.kind) + '" class="form">' +
      '<input name="title" value="' + esc(item.title) + '" maxlength="80" required aria-label="Название">' +
      '<textarea name="body" rows="9" maxlength="4000" required>' + esc(item.body) + "</textarea>" +
      '<div class="tools"><button class="main" type="submit">Сохранить</button><button type="button" data-act="scancel">Отмена</button></div>' +
      (!item.own && !S.admin ? '<p class="meta">Сохранится ваша копия, стандартный скрипт останется.</p>' : "") +
      "</form></div>";
  }
  return '<div class="scr"><div class="scr-head"><b>' + esc(item.title) + '</b><span class="tag' + (item.own ? " own" : "") + '">' +
    (item.own ? "Мой" : esc(kindName)) + "</span></div>" +
    '<p class="scr-text' + (open ? "" : " clamp") + '">' + esc(item.body) + "</p>" +
    '<div class="tools"><button class="main" data-act="scopy" data-id="' + item.id + '">' + ic("copy") + "Копировать</button>" +
    '<button data-act="sedit" data-id="' + item.id + '">' + ic("edit") + "Изменить</button>" +
    '<button data-act="sopen" data-id="' + item.id + '">' + (open ? "Свернуть" : "Читать полностью") + "</button>" +
    (item.own || S.admin ? '<button data-act="sdel" data-id="' + item.id + '">' + ic("trash") + "Удалить</button>" : "") +
    "</div></div>";
}

function generateNicheScript(kind, variant) {
  var title = nicheTitle(S.scriptNiche);
  variant = variant || 1;
  S.genVariant = variant;
  var head = '<div class="top"><h2>Новый скрипт: ' + esc(title) + '</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' + ic("x") + "</button></div>";
  openSheet(head + '<div class="dots"><i></i><i></i><i></i></div>');
  var seq = S.sheetSeq;
  api("/api/scripts/generate", {
    method: "POST", body: JSON.stringify({ niche: S.scriptNiche, kind: kind, variant: variant })
  }).then(function (result) {
    if (seq !== S.sheetSeq) return;
    S.sheetText = result.text || "";
    S.sheetSaved = false;
    S.sheetNiche = title;
    setSheetBody(head + copyCard(result.text) + genTools("nichemore", kind));
  }).catch(function (error) { if (seq !== S.sheetSeq) return; closeSheet(); toast(error.message); });
}

function saveGenerated(kind) {
  if (S.sheetSaved) return;
  var niche = (S.niches.filter(function (item) { return item.title === S.sheetNiche; })[0] || {}).id;
  if (niche == null || niche === CUSTOM_NICHE) niche = S.scriptNiche;
  var kindName = (KINDS.filter(function (k) { return k[0] === kind; })[0] || [0, "Скрипт"])[1];
  S.sheetSaved = true;
  var button = $("#save-gen");
  if (button) { button.disabled = true; button.innerHTML = ic("doc") + "Сохранено"; }
  api("/api/scripts", {
    method: "POST",
    body: JSON.stringify({ niche: niche, kind: kind, title: kindName + " — мой вариант", body: S.sheetText || "" })
  }).then(function () {
    toast("Сохранено во вкладке «Скрипты».");
    if (S.scriptNiche === niche) loadScripts().then(function () { if (S.tab === "scripts") render(true); });
  }).catch(function (error) {
    S.sheetSaved = false;
    if (button) { button.disabled = false; button.innerHTML = ic("doc") + "Сохранить в мои скрипты"; }
    toast(error.message);
  });
}

/* ---------- Статистика и FAQ ---------- */

function vStats() {
  var stats = S.stats || {};
  var total = Number(stats.found) || 0;
  var contacted = Number(stats.contacted) || 0;
  var replied = Number(stats.replied) || 0;
  var clients = Number(stats.clients) || 0;
  var rows = [["Найдено", total], ["Связались", contacted], ["Ответили", replied], ["Клиенты", clients]];
  var percentage = function (value) { return total ? Math.round(value / total * 100) : 0; };
  return '<section class="screen"><h2>Статистика</h2><div class="grid">' +
    rows.map(function (row) {
      return '<div class="card tile"><small class="muted">' + row[0] +
        '</small><b class="num" data-to="' + row[1] + '">' + row[1] + "</b></div>";
    }).join("") + '</div><div class="card"><h3>Воронка</h3>' +
    rows.map(function (row) {
      return '<div class="fn"><span>' + row[0] + '</span><div class="bar"><i style="width:' +
        percentage(row[1]) + '%"></i></div><em>' + percentage(row[1]) + "%</em></div>";
    }).join("") + '</div><div class="card"><div class="row"><span>Ответили от найденных</span><b>' +
    percentage(replied) + '%</b></div><div class="row g"><span>Клиенты от найденных</span><b>' +
    percentage(clients) + "%</b></div></div>" +
    '<p class="muted small">Статистика показывает только отмеченные вручную результаты. Она не предсказывает будущие продажи.</p></section>';
}

function faqItem(question, answer) {
  return "<details><summary><span>" + question + "</span>" + PM + "</summary><div class=\"faq-a\">" + answer + "</div></details>";
}

function vFaq() {
  var steps = [
    ["Выберите страну, город и нишу", "Город выбирается из списка. Вариант «Все крупные города» ищет сразу по нескольким большим городам страны."],
    ["Нажмите «Найти»", "Парсер найдёт бизнесы на карте и проверит, что у них есть телефон. Каждый бизнес достаётся только вам."],
    ["Откройте бизнес на карте", "Кнопка «Открыть на карте» покажет его карточку: сайт, соцсети, отзывы и часы работы."],
    ["Напишите или позвоните", "Нажмите «Скрипт» — получите готовый текст с названием бизнеса."],
    ["Отмечайте результат", "Статусы «Написал», «Ответил», «Отказ», «Клиент» помогают не потеряться и видеть свою воронку."]
  ];
  var keys = [
    ["Как найти клиентов?", "Выберите нишу и город и нажмите «Найти». Начните с ниш из кнопки <b>«Какие ниши требуют сайт/бот?»</b> на главной — там самые подходящие."],
    ["Как связаться с бизнесом?", "У каждого лида есть телефон из карточки на карте. Если номеров несколько, нажмите на <b>стрелочку</b> рядом с номером. Сайт, соцсети и отзывы смотрите по кнопке <b>«Открыть на карте»</b>."],
    ["Могу ли я получить того же клиента, что и другой участник?", "Нет. Каждый бизнес закрепляется <b>только за одним человеком</b>. Повторные поиски тоже не выдают уже полученных."],
    ["Что такое пробный доступ?", "Каждому доступен <b>1 запрос до 10 лидов</b>. Если ничего не нашлось, запрос не списывается."],
    ["Как получить полный доступ?", "Вступите в команду C&amp;C Family — подробности у @SUN9ISE. Если вам выдали ключ, введите его на главной или отправьте боту: <b>/key КОД</b>."],
    ["Что писать бизнесу?", "Во вкладке <b>«Скрипты»</b> есть готовые тексты по нишам. В карточке лида кнопка «Скрипт» пишет текст под конкретный бизнес. «Ещё вариант» даёт другой текст."],
    ["Какую нишу выбрать?", "Кнопка с огоньком на главной показывает, каким нишам сейчас больше всего нужен сайт или бот и что им предложить."],
    ["Зачем отмечать статусы?", "Чтобы видеть, кому уже написали, кто ответил и кто стал клиентом. Это же видно во вкладке «Статистика»."],
    ["Как выгрузить лиды?", "На вкладке «Лиды» нажмите кнопку загрузки — Excel-файл придёт в чат с ботом."],
    ["Что такое лимит?", "Для участников — сколько лидов можно получить за день. Если поиск нашёл меньше, остаток возвращается."],
    ["В каких странах работает?", "14 стран: Россия, Украина, Беларусь, Казахстан, Узбекистан, Кыргызстан, Армения, Азербайджан, Грузия, Молдова, Польша, Литва, Германия, ОАЭ. В каждой — от 60 до 150 городов, от крупных к небольшим."],
    ["Номер не отвечает или данные устарели", "Бизнесы иногда меняют номера, а карты обновляются не сразу. Откройте бизнес на карте — там обычно актуальный телефон."]
  ];
  return '<section class="screen"><h2>Вопросы</h2>' +
    '<div class="card howto"><h3>Как пользоваться</h3><ol class="howto-steps">' +
    steps.map(function (step) { return "<li><b>" + esc(step[0]) + "</b><span>" + esc(step[1]) + "</span></li>"; }).join("") +
    "</ol></div>" +
    '<div class="card faq"><h3>Частые вопросы</h3>' +
    keys.map(function (item) { return faqItem(esc(item[0]), item[1]); }).join("") +
    "</div><a class=\"contact\" data-ext href=\"https://t.me/" + esc(SUPPORT_TELEGRAM) +
    "\" target=\"_blank\" rel=\"noopener\">" + ic("send") +
    "Написать @" + esc(SUPPORT_TELEGRAM) + "</a>" +
    '<p class="meta center-text" style="margin:10px 0 4px">Поддержка</p></section>';
}

/* ---------- Админ ---------- */

function loadAdmin() {
  if (!S.admin) return Promise.reject(new Error("Только для администратора."));
  var loaders = {
    users: function () {
      return Promise.all([api("/api/admin/users"), api("/api/admin/settings")]).then(function (r) {
        S.users = r[0].users || [];
        S.defLimit = Number(r[1].default_limit);
        if (!S.defOpen) S.defVal = S.defLimit;
      });
    },
    keys: function () {
      return Promise.all([api("/api/admin/keys"), api("/api/admin/settings")]).then(function (r) {
        S.keys = r[0].keys || [];
        S.defLimit = Number(r[1].default_limit);
      });
    },
    members: function () { return api("/api/admin/members").then(function (d) { S.members = d.members || []; }); },
    leads: function () {
      return api("/api/admin/leads?q=" + encodeURIComponent(S.adminQuery)).then(function (d) { S.adminLeads = (d.leads || []).map(function (l) { var v = leadsToView(l); v.owner = l.owner; return v; }); });
    },
    overview: function () { return api("/api/admin/overview").then(function (d) { S.overview = d; }); },
    blocked: function () { return api("/api/admin/blocked").then(function (d) { S.blocked = d.items || []; }); },
    errors: function () { return api("/api/admin/overview").then(function (d) { S.errors = d.errors; S.overview = d; }); }
  };
  return (loaders[S.atab] || loaders.users)();
}

function userRow(user) {
  var editing = S.editId === user.id;
  var badge = user.banned ? '<span class="badge b">Бан</span>' :
    user.plan === "member" ? '<span class="badge m">' + (user.is_admin ? "Владелец" : "Участник") + "</span>" :
    '<span class="badge">Проба ' + user.trial_used + "/" + (Number(user.trial_used || 0) + Number(user.trial_left || 0)) + "</span>";
  return '<div class="usr"><div class="row"><b>' + esc(user.n) + "</b>" + badge + "</div>" +
    '<p class="muted small">ID ' + esc(user.id) + (user.plan === "member" ? " · сегодня " + user.t + "/" + user.lim : " · осталось запросов " + esc(user.trial_left)) +
    " · лидов " + user.f + " · клиенты " + user.k + (user.bonus ? " · бонус " + user.bonus : "") + "</p>" +
    (user.is_admin ? "" : '<div class="urow">' +
      '<button class="' + (user.approved ? "" : "main") + '" data-act="access" data-id="' + user.id + '" data-v="' + (user.approved ? "0" : "1") + '">' +
        ic(user.approved ? "x" : "key") + "<span>" + (user.approved ? "Закрыть доступ" : "Выдать доступ") + "</span></button>" +
      '<button data-act="edit" data-id="' + user.id + '">' + ic("edit") + "<span>Лимит</span></button>" +
      '<button data-act="ban" data-id="' + user.id + '" data-v="' + (user.banned ? "0" : "1") + '">' + ic("ban") + "<span>" + (user.banned ? "Разбанить" : "Забанить") + "</span></button>" +
      (S.delConfirm === user.id
        ? '<button class="danger" data-act="udel" data-id="' + user.id + '">' + ic("trash") + "<span>Точно удалить?</span></button>"
        : '<button class="danger" data-act="udelask" data-id="' + user.id + '">' + ic("trash") + "<span>Удалить</span></button>") +
      "</div>") +
    (editing
      ? '<div class="edit"><div class="row"><span class="muted small">Дневной лимит: <b>' +
        S.editVal + '</b></span><div class="step"><button data-act="limd" data-v="-10" aria-label="Меньше">−</button>' +
        '<button data-act="limd" data-v="10" aria-label="Больше">+</button></div></div>' +
        '<div class="chips">' + limitChips([0, 35, 70, 100, 150, 200]).map(function (value) {
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
    '<p class="muted small">Столько лидов в день получает каждый новый участник — при выдаче доступа и по новому ключу.</p>' +
    (S.defOpen
      ? '<div class="edit"><div class="row"><span class="muted small">Новый лимит: <b>' + esc(S.defVal) + '</b></span><div class="step">' +
        '<button data-act="defd" data-v="-5" aria-label="Меньше">−</button><button data-act="defd" data-v="5" aria-label="Больше">+</button></div></div>' +
        '<div class="chips">' + [10, 20, 35, 50, 70, 100, 150].map(function (value) {
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
  return '<div class="grid">' + [["Участников", members], ["На пробе", trials], ["Забанено", banned], ["Всего", S.users.length]].map(function (row) {
      return '<div class="card tile"><small class="muted">' + row[0] + '</small><b class="num" data-to="' + row[1] + '">' + row[1] + "</b></div>";
    }).join("") + "</div>" +
    defaultLimitCard() +
    '<div class="card"><h3>Выдать полный доступ</h3><form id="grant-form" class="form"><div class="two">' +
    '<input name="query" required placeholder="@username / ID" aria-label="Пользователь">' +
    '<input name="limit" type="number" min="1" max="5000" placeholder="Лимит/день: ' + esc(S.defLimit) + '" aria-label="Лимит лидов в день"></div>' +
    '<button class="btn main" type="submit">' + ic("plus") + "Выдать</button></form>" +
    '<p class="muted small">По @username — если человек уже нажимал /start. Иначе — по ID или создайте ключ.</p></div>' +
    '<div class="card"><h3>Пользователи</h3><input id="user-q" value="' + esc(S.userQuery) + '" placeholder="Поиск по @username или ID" autocomplete="off">' +
    '<div class="ulist">' + (users.length ? users.map(userRow).join("") : '<p class="muted">Никого не найдено.</p>') + "</div></div>" +
    broadcastCard();
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

function adminKeys() {
  return '<div class="card"><h3>Новый ключ доступа</h3><form id="key-create" class="form">' +
    '<label>Для кого (необязательно)<input name="for_user" placeholder="@username или ID" maxlength="64"></label>' +
    '<div class="two"><label>Лимит лидов в день<input name="limit" type="number" min="0" max="5000" value="' + esc(S.defLimit) + '"></label>' +
    '<label>Бонус запросов<input name="bonus" type="number" min="0" max="1000" value="0"></label></div>' +
    '<div class="two"><label>Активаций<input name="uses" type="number" min="1" max="1000" value="1"></label>' +
    '<label>Заметка<input name="note" maxlength="120" placeholder="например, оплатил"></label></div>' +
    '<button class="btn main" type="submit">' + ic("key") + "Создать ключ</button></form>" +
    (S.newKey ? '<div class="card" style="margin-bottom:0"><p class="muted small">Ключ создан. Пользователь вводит его в приложении или командой /key.</p><div class="row g"><span class="code">' + esc(S.newKey) +
      '</span><button class="ghost" style="flex:none" data-act="copykey" data-v="' + esc(S.newKey) + '">' + ic("copy") + "Копировать</button></div></div>" : "") +
    "</div>" +
    '<div class="card"><h3>Ключи</h3>' + (S.keys.length ? S.keys.map(function (key) {
      return '<div class="usr"><div class="row"><span class="code">' + esc(key.code) + '</span><button class="chip mini" data-act="delkey" data-v="' + esc(key.code) + '">' + ic("trash") + "</button></div>" +
        '<p class="muted small">' + (key.for_user ? "для " + esc(key.for_user) + " · " : "для любого · ") +
        (key.daily_limit ? "лимит " + key.daily_limit + " · " : "") + (key.bonus ? "+" + key.bonus + " запросов · " : "") +
        "осталось активаций " + key.uses_left + (key.used_by ? " · активировали: " + esc(key.used_by) : "") +
        (key.note ? " · " + esc(key.note) : "") + "</p></div>";
    }).join("") : '<p class="muted">Ключей пока нет.</p>') + "</div>";
}

function adminLeads() {
  return '<div class="card"><form id="aleads-form" class="keyform"><input name="q" value="' + esc(S.adminQuery) +
    '" placeholder="Название, город, телефон или @username"><button class="btn" type="submit">' + ic("search") + "</button></form></div>" +
    (S.adminLeads.length ? S.adminLeads.map(function (lead) {
      return '<div class="card"><div class="row"><b>' + esc(lead.name) + '</b><span class="badge">' + esc(lead.hot) + "</span></div>" +
        '<p class="muted small">' + esc(lead.country) + " · " + esc(lead.city) + (lead.niche ? " · " + esc(lead.niche) : "") +
        " · " + esc(STATUS_NAMES[lead.status] || lead.status) + " · у " + esc(lead.owner) + "</p>" +
        (lead.phone ? '<p class="small">' + esc(lead.phone) + "</p>" : "") +
        (lead.explain ? '<p class="why">' + esc(lead.explain) + "</p>" : "") +
        '<div class="urow"><button data-act="blocklead" data-id="' + lead.id + '">' + ic("ban") + " В чёрный список</button></div></div>";
    }).join("") : '<div class="empty"><p>Лидов не найдено</p></div>');
}

function table(rows, headers) {
  if (!rows || !rows.length) return '<p class="muted">Пока нет данных.</p>';
  return '<div style="overflow-x:auto"><table class="tbl"><tr>' + headers.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr>" +
    rows.map(function (row) {
      return "<tr><td>" + esc(row.name) + "</td><td>" + esc(row.leads) + "</td><td>" + esc(row.clients || 0) + "</td><td>" + esc(row.avg || 0) + "</td></tr>";
    }).join("") + "</table></div>";
}

function adminOverview() {
  var o = S.overview;
  if (!o) return '<div class="dots"><i></i><i></i><i></i></div>';
  return '<div class="grid">' + [["Пользователей", o.users.total], ["Участников", o.users.members], ["Пробу использовали", o.users.trial_used], ["Пробу не начали", o.users.trial_left],
      ["Лидов выдано", o.leads.total], ["Связались", o.leads.contacted], ["Клиентов", o.leads.clients], ["Забанено", o.users.banned]].map(function (row) {
      return '<div class="card tile"><small class="muted">' + row[0] + '</small><b class="num" data-to="' + (row[1] || 0) + '">' + (row[1] || 0) + "</b></div>";
    }).join("") + "</div>" +
    '<div class="card"><h3>По нишам</h3>' + table(o.niches, ["Ниша", "Лиды", "Клиенты", "Приор."]) + "</div>" +
    '<div class="card"><h3>По городам</h3>' + table(o.cities, ["Город", "Лиды", "Клиенты", "Приор."]) + "</div>" +
    '<div class="card"><h3>Внешние сервисы</h3><p class="muted small">Geoapify сегодня: ' + esc(o.api.geoapify_day) +
    " кредитов · нейросеть сегодня: " + esc(o.api.ai_day) + " запросов · Google за месяц: " + esc(o.api.google_month) + " · 2ГИС за месяц: " + esc(o.api.dgis_month || 0) + "</p></div>";
}

function adminBlocked() {
  return '<div class="card"><h3>Добавить бизнес</h3><form id="block-form" class="keyform"><input name="text" required placeholder="Телефон, сайт, email или @telegram">' +
    '<button class="btn" type="submit">' + ic("ban") + "</button></form>" +
    '<p class="muted small">Такой бизнес больше никому не выдаётся. Лид можно добавить и из вкладки «Все лиды».</p></div>' +
    '<div class="card"><h3>Чёрный список</h3>' + (S.blocked.length ? S.blocked.map(function (item) {
      return '<div class="usr"><div class="row"><b>' + esc(item.label) + '</b><button class="chip mini" data-act="unblock" data-v="' + esc(item.label) + '">Убрать</button></div></div>';
    }).join("") : '<p class="muted">Пусто.</p>') + "</div>";
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
  var views = { users: adminUsers, members: adminMembers, keys: adminKeys, leads: adminLeads, overview: adminOverview, blocked: adminBlocked, errors: adminErrors };
  return '<section class="screen"><h2>Админ-панель</h2><div class="atabs-grid">' + ADMIN_TABS.map(function (item) {
      return '<button class="chip ' + (S.atab === item[0] ? "on" : "") + '" data-act="atab" data-v="' + item[0] + '">' + item[1] + "</button>";
    }).join("") + "</div>" + (views[S.atab] || adminUsers)() + "</section>";
}

/* ---------- Отрисовка ---------- */

function countUp(element, value) {
  var start = performance.now();
  (function frame(now) {
    var progress = Math.min(1, (now - start) / 700);
    element.textContent = Math.round(value * (1 - Math.pow(1 - progress, 3)));
    if (progress < 1) requestAnimationFrame(frame);
  })(start);
}

function render(keepScroll) {
  var oldScroll = window.scrollY;
  var views = {
    "search": S.loading ? loadingView : vSearch,
    "leads": vLeads,
    "scripts": vScripts,
    "stats": vStats,
    "faq": vFaq,
    "admin": vAdmin
  };
  if (S.tab === "admin" && !S.admin) S.tab = "search";
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
  if (S.picker) {
    S.picker = null;
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

function saveLeadStatus(lead, nextStatus) {
  var previous = lead.status;
  lead.status = nextStatus;
  render(true);
  api("/api/leads/" + encodeURIComponent(lead.id) + "/status", {
    method: "POST", body: JSON.stringify({ status: nextStatus })
  }).then(function () {
    return loadStats();
  }).then(function () {
    if (S.tab === "leads") render(true);
    toast("Статус лида обновлён.");
  }).catch(function (error) {
    lead.status = previous;
    render(true);
    toast(error.message);
  });
}

function askDeleteLead(lead) {
  openSheet('<div class="top"><h2>Удалить лид?</h2><button class="icon-btn" data-act="close" aria-label="Закрыть">' + ic("x") + "</button></div>" +
    '<p class="del-q">«' + esc(lead.name) + "»" + (lead.city ? " · " + esc(lead.city) : "") + "</p>" +
    '<p class="muted small">Лид пропадёт из списка, и этот бизнес больше не попадёт в поиск. Вернуть его будет нельзя.</p>' +
    '<div class="del-btns"><button class="btn" data-act="close">Отмена</button>' +
    '<button class="btn danger" data-act="leaddel" data-id="' + encodeURIComponent(lead.id) + '">' + ic("trash") + "Удалить</button></div>");
}

function deleteLead(lead, button) {
  if (button) button.disabled = true;
  api("/api/leads/" + encodeURIComponent(lead.id), { method: "DELETE" }).then(function () {
    leads = leads.filter(function (item) { return item.id !== lead.id; });
    delete S.open[lead.id];
    if (S.stats && S.stats.found) S.stats.found = Math.max(0, Number(S.stats.found) - 1);
    closeSheet();
    if (S.tab === "leads") render(true);
    toast("Лид удалён.");
    loadStats().then(function () { if (S.tab === "leads") render(true); }).catch(function () {});
  }).catch(function (error) {
    if (button) button.disabled = false;
    toast(error.message);
  });
}

function adminAction(path, body, message) {
  return api(path, { method: "POST", body: JSON.stringify(body) }).then(function (result) {
    return loadAdmin().then(function () {
      render(true);
      toast((result && result.message) || message);
    });
  }).catch(function (error) { toast(error.message); });
}

function findLead(id) {
  return leads.filter(function (item) { return String(item.id) === String(id); })[0];
}

function clickHandler(event) {
  var target = event.target;
  if (target.closest(".hot") == null) {
    document.querySelectorAll(".hot.open").forEach(function (node) { node.classList.remove("open"); });
  }
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
    S.tab = value;
    if (S.tab === "admin") {
      render();
      loadAdmin().then(function () { render(true); }).catch(function (error) { S.tab = "search"; render(); toast(error.message); });
    } else if (S.tab === "scripts") {
      if (S.scriptNiche === CUSTOM_NICHE) S.scriptNiche = 0;
      render();
      loadScripts().then(function () { if (S.tab === "scripts") render(true); }).catch(function (error) { toast(error.message); });
    } else {
      render();
    }
  } else if (action === "niche") {
    S.niche = Number(value);
    render(true);
  } else if (action === "flt") {
    S.flt = value;
    render(true);
  } else if (action === "count") {
    S.count = Number(value);
    render(true);
  } else if (action === "filter") {
    S.filter = value;
    render(true);
  } else if (action === "go") {
    go();
  } else if (action === "demand") {
    showDemand();
  } else if (action === "pickniche") {
    S.niche = Number(value);
    closeSheet();
    S.tab = "search";
    render();
    toast("Ниша выбрана: " + nicheTitle(S.niche) + ".");
  } else if (action === "close") {
    closeSheet();
  } else if (action === "offer") {
    showTrialOffer(S.trialOffer || { message: S.access && S.access.trial_message });
  } else if (action === "status") {
    var lead = findLead(id);
    if (lead) saveLeadStatus(lead, lead.status === value ? "new" : value);
  } else if (action === "leaddelask") {
    var delLead = findLead(id);
    if (delLead) askDeleteLead(delLead);
  } else if (action === "leaddel") {
    var goneLead = findLead(id);
    if (goneLead) deleteLead(goneLead, button);
  } else if (action === "phones") {
    S.open[id] = !S.open[id];
    render(true);
  } else if (action === "leadscript" || action === "leadkind") {
    var scriptLead = findLead(id);
    if (scriptLead) generateLeadScript(scriptLead, action === "leadkind" ? value : "first", 0);
  } else if (action === "leadmore") {
    var moreLead = findLead(S.genLead);
    if (moreLead) generateLeadScript(moreLead, value, (S.genVariant || 0) + 1);
  } else if (action === "nichemore") {
    generateNicheScript(value, (S.genVariant || 1) + 1);
  } else if (action === "copygen") {
    copyText(S.sheetText || "");
  } else if (action === "pick") {
    openPicker(value);
  } else if (action === "pickset") {
    applyPick(button.dataset.k, value);
  } else if (action === "qinfo") {
    S.qOpen = !S.qOpen;
    var pop = $("#qpop");
    if (pop) pop.hidden = !S.qOpen;
    button.setAttribute("aria-expanded", S.qOpen ? "true" : "false");
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
  } else if (action === "savegen") {
    saveGenerated(value);
  } else if (action === "export") {
    api("/api/export", { method: "POST" }).then(function (data) {
      toast(data.message || "Excel-файл придёт в чат с ботом.");
    }).catch(function (error) { toast(error.message); });
  } else if (action === "scrmode") {
    S.scrMode = value;
    S.scriptEdit = null;
    render(true);
    window.scrollTo(0, 0);
    loadScripts().then(function () { if (S.tab === "scripts") render(true); }).catch(function () {});
  } else if (action === "mykind") {
    S.myKind = value;
    render(true);
  } else if (action === "sopen") {
    S.scriptOpen[id] = !S.scriptOpen[id];
    render(true);
  } else if (action === "scopy") {
    var script = findScript(id);
    if (script) copyText(script.body);
  } else if (action === "sedit") {
    S.scriptEdit = Number(id);
    render(true);
  } else if (action === "scancel") {
    S.scriptEdit = null;
    render(true);
  } else if (action === "sdel") {
    api("/api/scripts/" + encodeURIComponent(id), { method: "DELETE" }).then(function () {
      return loadScripts();
    }).then(function () { render(true); toast("Скрипт удалён."); }).catch(function (error) { toast(error.message); });
  } else if (action === "genniche") {
    generateNicheScript(value, 1);
  } else if (action === "atab") {
    S.atab = value;
    S.newKey = "";
    render(true);
    loadAdmin().then(function () { render(true); }).catch(function (error) { toast(error.message); });
  } else if (action === "edit") {
    var user = S.users.filter(function (item) { return String(item.id) === id; })[0];
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
    adminAction("/api/admin/users/" + encodeURIComponent(id) + "/bonus", { amount: Number(value) }, "Запросы добавлены.");
  } else if (action === "ban") {
    adminAction("/api/admin/users/" + encodeURIComponent(id) + "/ban", { banned: value === "1" },
      value === "1" ? "Пользователь заблокирован." : "Пользователь разблокирован.");
  } else if (action === "copykey" || action === "copyval") {
    copyText(value);
  } else if (action === "delkey") {
    api("/api/admin/keys/" + encodeURIComponent(value), { method: "DELETE" }).then(function () {
      return loadAdmin();
    }).then(function () { render(true); toast("Ключ удалён."); }).catch(function (error) { toast(error.message); });
  } else if (action === "blocklead") {
    adminAction("/api/admin/blocked", { lead_id: Number(id) }, "Бизнес добавлен в чёрный список.");
  } else if (action === "unblock") {
    adminAction("/api/admin/unblock", { label: value }, "Убрано из чёрного списка.");
  } else if (action === "tip") {
    var wasOpen = button.classList.contains("open");
    document.querySelectorAll(".hot.open").forEach(function (node) { node.classList.remove("open"); });
    if (!wasOpen) button.classList.add("open");
  } else if (action === "refresh") {
    refreshAll().then(function () { toast("Данные обновлены."); }).catch(function (error) { toast(error.message); });
  }
}

document.addEventListener("click", clickHandler);
document.addEventListener("input", function (event) {
  if (event.target.id === "city") S.city = event.target.value;
  if (event.target.id === "cn") S.custom = event.target.value;
  if (event.target.id === "my-q") {
    S.myQuery = event.target.value;
    clearTimeout(S.myQT);
    S.myQT = setTimeout(function () {
      var pos = event.target.selectionStart;
      render(true);
      var input = $("#my-q");
      if (input) { input.focus(); try { input.setSelectionRange(pos, pos); } catch (e) {} }
    }, 250);
  }
  if (event.target.id === "psearch") {
    var query = normalizeSearch(event.target.value);
    var shown = 0;
    document.querySelectorAll("#plist button").forEach(function (node) {
      var match = !query || node.dataset.s.indexOf(query) >= 0;
      node.hidden = !match;
      if (match) shown += 1;
    });
    var empty = $("#pempty");
    if (empty) empty.hidden = shown > 0;
  }
  if (event.target.id === "bc-ed") S.bcHtml = event.target.innerHTML;
  if (event.target.id === "mem-q" || event.target.id === "user-q") {
    if (event.target.id === "mem-q") S.memberQuery = event.target.value; else S.userQuery = event.target.value;
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

/* Картинку для рассылки уменьшаем в браузере: до 1600 px по большей стороне, JPEG. */
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
document.addEventListener("toggle", function (event) {
  if (event.target.dataset && event.target.dataset.intro === "scripts") S.scrIntro = event.target.open;
}, true);
document.addEventListener("keydown", function (event) {
  if (event.key === "Escape" && $("#sheet").classList.contains("show")) closeSheet();
});

function formValue(form, name) {
  return String(new FormData(form).get(name) || "").trim();
}

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
      return loadMe().then(function () { render(); toast(result.message || "Ключ активирован."); });
    }).catch(function (error) { toast(error.message); });
  } else if (id === "script-form") {
    var payload = {
      niche: form.dataset.niche !== undefined && form.dataset.niche !== "" ? Number(form.dataset.niche) : S.scriptNiche, kind: form.dataset.kind || "first",
      title: formValue(form, "title"), body: formValue(form, "body")
    };
    if (!payload.title || !payload.body) { toast("Заполните название и текст."); return; }
    api("/api/scripts/" + encodeURIComponent(form.dataset.id), { method: "PUT", body: JSON.stringify(payload) }).then(function (result) {
      S.scriptEdit = null;
      return loadScripts().then(function () {
        render(true);
        toast(result.copy ? "Сохранено как ваш скрипт." : "Скрипт сохранён.");
      });
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
  } else if (id === "aleads-form") {
    S.adminQuery = formValue(form, "q");
    loadAdmin().then(function () { render(true); }).catch(function (error) { toast(error.message); });
  } else if (id === "block-form") {
    adminAction("/api/admin/blocked", { text: formValue(form, "text") }, "Добавлено в чёрный список.");
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

function appReady() {
  if (typeof window.__appReady === "function") window.__appReady();
}

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
