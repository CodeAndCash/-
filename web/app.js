/* C&C Family — мини-апп. Без фреймворков: быстро открывается и не лагает. */
(function () {
"use strict";

var tg = window.Telegram && window.Telegram.WebApp;
var BIRD = '<svg viewBox="2 2 251 252" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M97.2 6.2 L107.0 65.2 L158.0 106.0 L182.8 90.0Z M5.8 5.8 L15.0 45.0 L54.0 80.2 L52.8 81.0 L21.5 65.2 L28.0 94.2 L71.5 129.2 L35.5 119.0 L43.0 151.2 L96.5 176.2 L121.5 169.2 L105.5 179.0 L97.0 186.8 L65.0 249.5 L132.5 187.8 L180.5 150.8 L205.5 135.8 L230.5 124.8 L248.2 123.8 L239.2 113.5 L226.2 103.0 L214.0 95.0 L207.8 93.0 L192.0 95.0 L166.0 109.2 L165.5 110.5 L176.2 120.0 L176.2 121.8Z"/></svg>';
var S = {
  boot: null,          // ответ /api/bootstrap
  cache: {},           // списки и страницы материалов
  eval: null,          // раздел «Оценка работ»
  files: [],           // выбранные файлы на оценку
  admin: { tab: "overview", users: null, q: "", filter: "all", payments: null, pstatus: "", kind: "lesson" },
  slide: 0,
  waitingPay: 0
};

// ---------- Мелочи ----------

function $(sel, root) { return (root || document).querySelector(sel); }
function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function ic(name, cls) {
  var body = (window.ICONS || {})[name] || "";
  return '<span class="ic' + (cls ? " " + cls : "") + '" aria-hidden="true"><svg viewBox="0 0 24 24">' + body + "</svg></span>";
}
function plural(n, one, few, many) {
  var a = Math.abs(n) % 10, b = Math.abs(n) % 100;
  if (a === 1 && b !== 11) return one;
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return few;
  return many;
}
function money(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " ₽"; }
function fmtDate(ts) {
  var m = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  var d = new Date(ts * 1000);
  return d.getDate() + " " + m[d.getMonth()];
}
function haptic(kind) {
  try { if (tg && tg.HapticFeedback) kind === "ok" ? tg.HapticFeedback.notificationOccurred("success") : tg.HapticFeedback.impactOccurred("light"); } catch (e) {}
}
function toast(text) {
  var t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(function () { t.classList.remove("show"); }, Math.max(2600, String(text).length * 55));
}
function openLink(url) {
  try {
    if (tg && /^https:\/\/t\.me\//.test(url)) return tg.openTelegramLink(url);
    if (tg && /^https?:/.test(url)) return tg.openLink(url);
  } catch (e) {}
  window.open(url, "_blank", "noopener");
}
function chatWith(username, text) {
  openLink("https://t.me/" + username + (text ? "?text=" + encodeURIComponent(text) : ""));
}
function copyText(text) {
  var done = function () { toast("Скопировано"); haptic(); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
  } else fallbackCopy(text, done);
}
function fallbackCopy(text, done) {
  var a = document.createElement("textarea");
  a.value = text; a.style.position = "fixed"; a.style.opacity = "0";
  document.body.appendChild(a); a.select();
  try { document.execCommand("copy"); done(); } catch (e) { toast("Выдели текст и скопируй вручную"); }
  document.body.removeChild(a);
}

// ---------- Сервер ----------

function api(path, opts) {
  opts = opts || {};
  var headers = { "X-Init-Data": tg && tg.initData ? tg.initData : "" };
  if (opts.body && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  return fetch(path, { method: opts.method || "GET", headers: headers, body: opts.body })
    .catch(function () { throw new Error("Нет связи с сервером. Проверь интернет и попробуй ещё раз."); })
    .then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) {
          var d = data.detail, msg = d;
          if (d && typeof d === "object" && !Array.isArray(d)) msg = d.message;
          if (Array.isArray(d)) msg = "Проверь, что всё заполнено правильно.";
          var err = new Error(msg || "Ошибка сервера: " + r.status);
          err.status = r.status; err.detail = d;
          throw err;
        }
        return data;
      });
    });
}

function me() { return S.boot ? S.boot.me : {}; }
function resident() { return !!(S.boot && S.boot.me.access.resident); }
function isAdmin() { return !!(S.boot && S.boot.me.access.admin); }
function links() { return S.boot ? S.boot.links : { support: "", personal: "", bot: "" }; }

// ---------- Тема ----------

function setTheme(theme, save) {
  document.documentElement.dataset.theme = theme;
  var bg = theme === "light" ? "#f2f2f4" : "#0e0f11";
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = bg;
  try { if (tg) { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); if (tg.setBottomBarColor) tg.setBottomBarColor(bg); } } catch (e) {}
  if (save) {
    try { localStorage.setItem("cc_theme", theme); } catch (e) {}
    api("/api/prefs", { method: "POST", body: { theme: theme } }).catch(function () {});
  }
}
function theme() { return document.documentElement.dataset.theme || "dark"; }

// ---------- Маршруты ----------

var ROOTS = { "": 1, categories: 1, profile: 1 };
function route() {
  var h = location.hash.replace(/^#\/?/, "");
  if (h.indexOf("=") >= 0 || h.indexOf("tgWebApp") >= 0) h = "";   // служебный хвост Telegram
  var parts = h.split("/");
  return { name: parts[0] || "", arg: parts.slice(1).join("/") };
}
function go(hash) {
  if (("#" + hash) === location.hash || (hash === "" && !location.hash)) { render(); return; }
  S.depth = (S.depth || 0) + 1;
  location.hash = hash;
}

window.addEventListener("hashchange", function () { closeSheet(); render(); window.scrollTo(0, 0); });

function updateBack() {
  if (!tg || !tg.BackButton) return;
  var r = route();
  try { ROOTS[r.name] ? tg.BackButton.hide() : tg.BackButton.show(); } catch (e) {}
}
function goBack() {
  if ($("#sheet").classList.contains("show")) { closeSheet(); return; }
  if (S.depth > 0) { S.depth--; history.back(); return; }
  var n = route().name;
  if (n === "item" || n === "list" || n === "course" || n === "marathon" || n === "eval") location.replace("#categories");
  else if (n === "admin") location.replace("#profile");
  else location.replace("#");
}

// ---------- Нижнее меню ----------

var NAV = [
  ["", "home", "Главная"],
  ["categories", "grid", "Категории"],
  ["profile", "user", "Профиль"]
];
function navActive() {
  var n = route().name;
  if (n === "categories" || n === "course" || n === "list" || n === "item" || n === "marathon" || n === "eval") return "categories";
  if (n === "profile" || n === "admin") return "profile";
  return "";
}
function renderNav() {
  var on = navActive();
  $("#nav").innerHTML = NAV.map(function (n) {
    return '<button data-nav="' + n[0] + '" class="' + (n[0] === on ? "on" : "") + '" aria-label="' + n[2] + '">' + ic(n[1]) + "<span class=\"lbl\">" + n[2] + "</span></button>";
  }).join("");
}
function openModule(name) {
  // Парсер — отдельная страница того же приложения, вход Telegram сохраняется.
  try { sessionStorage.setItem("cc_return", location.hash || "#"); } catch (e) {}
  location.href = "/" + name + "/";
}

// ---------- Разметка уроков ----------

function inline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" data-ext>$1</a>');
}
function md(text) {
  var src = esc(text || "").replace(/\r/g, "");
  var blocks = [];
  src = src.replace(/```[a-z]*\n?([\s\S]*?)```/g, function (_, code) {
    blocks.push(code.replace(/\n$/, ""));
    return "\n@@CODE" + (blocks.length - 1) + "@@\n";
  });
  var out = [], list = null, para = [];
  function flushPara() { if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; } }
  function flushList() { if (list) { out.push("<" + list.tag + ">" + list.items.map(function (i) { return "<li>" + inline(i) + "</li>"; }).join("") + "</" + list.tag + ">"); list = null; } }
  src.split("\n").forEach(function (line) {
    var t = line.trim(), m;
    if (!t) { flushPara(); flushList(); return; }
    if ((m = /^@@CODE(\d+)@@$/.exec(t))) {
      flushPara(); flushList();
      out.push('<pre class="has-copy"><button class="copy" data-copy="' + m[1] + '">Скопировать</button><code>' + blocks[+m[1]] + "</code></pre>");
      return;
    }
    if ((m = /^#{2,3}\s+(.+)/.exec(t))) { flushPara(); flushList(); out.push("<h2>" + inline(m[1]) + "</h2>"); return; }
    if ((m = /^&gt;\s?(.*)/.exec(t))) { flushPara(); flushList(); out.push("<blockquote>" + inline(m[1]) + "</blockquote>"); return; }
    if ((m = /^[-•]\s+(.+)/.exec(t))) { flushPara(); if (!list || list.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; } list.items.push(m[1]); return; }
    if ((m = /^\d+[.)]\s+(.+)/.exec(t))) { flushPara(); if (!list || list.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; } list.items.push(m[1]); return; }
    flushList(); para.push(t);
  });
  flushPara(); flushList();
  S.codeBlocks = blocks.map(function (b) { var d = document.createElement("textarea"); d.innerHTML = b; return d.value; });
  return out.join("");
}

// ---------- Общие куски ----------

function avatar(big) {
  var m = me();
  var letter = esc((m.name || "C").trim().charAt(0).toUpperCase());
  return '<span class="ava' + (big ? " big" : "") + '">' + (m.photo ? '<img src="' + esc(m.photo) + '" alt="" referrerpolicy="no-referrer">' : letter) + "</span>";
}
function kindName(kind, free) {
  var k = { lesson: "Курс", material: "Материалы", prompt: "Промпты", resource: "Подборка", agent: "AI-офис", marathon: "Марафон", post: "Пост" }[kind] || "C&C";
  return k + (free ? ", бесплатно" : ", для резидентов");
}
function badge(icon, big) {
  return '<div class="badge3' + (big ? " big" : "") + '"><i class="strap"></i><i class="clip"></i><div class="card3">' +
    '<i class="slot"></i>' + ic(icon || "code") + '<b class="mark">C&amp;C</b><span class="fine">C&amp;C FAMILY · ВАЙБКОДИНГ<br>ЗАКРЫТОЕ СООБЩЕСТВО</span></div></div>';
}
function badgeArt(item, locked) {
  return '<div class="art' + (locked ? " locked" : "") + '">' + badge(item.icon) +
    (locked ? '<span class="lockmark">' + ic("lock") + "Для резидентов</span>" : "") + "</div>";
}
function logo(cls) { return '<span class="ava logo' + (cls ? " " + cls : "") + '">' + BIRD + "</span>"; }
function empty(icon, text, action) {
  return '<div class="empty">' + ic(icon) + "<p>" + esc(text) + "</p>" + (action || "") + "</div>";
}
function membersText(n) { return n > 0 ? n + " " + plural(n, "участник", "участника", "участников") : "Закрытое сообщество"; }

// ---------- Главная ----------

// Заставка — короткое видео (петля 6 секунд). Если видео не загрузилось, под ним та же анимация на CSS.
var CAN_MP4 = (function () { try { return !!document.createElement("video").canPlayType('video/mp4; codecs="avc1.4D401F"'); } catch (e) { return false; } })();
function video(name) {
  if (!CAN_MP4) return "";
  return '<video class="slide-video" src="media/' + name + '.mp4?v=1" poster="media/' + name + '_poster.jpg?v=1" autoplay muted loop playsinline preload="auto" aria-hidden="true"></video>';
}

function slides() {
  var c = S.boot.counts, n = S.boot.community.members;
  var join = resident() ? "community" : "join";
  var s1 = '<div class="slide s-logo"><div class="capsule"><span class="bird">' + BIRD + "</span><b>C&amp;C Family</b></div>" + video("intro") +
    '<div class="slide-foot"><span>' + membersText(n) + '</span><button class="pill" data-go="' + join + '">Открыть</button></div></div>';
  var s2 = '<div class="slide s-badge">' + badge("cap", true) +
    '<div class="slide-foot"><span>Курс с нуля<small>' + c.modules + " " + plural(c.modules, "модуль", "модуля", "модулей") + ", " + c.lesson + " " + plural(c.lesson, "урок", "урока", "уроков") + "</small></span>" +
    '<button class="pill" data-go="course">Открыть</button></div></div>';
  var s3 = '<div class="slide s-badge alt">' + badge("doc", true) +
    '<div class="slide-foot"><span>Материалы<small>Чек-листы, промпты, AI-офис</small></span>' +
    '<button class="pill" data-go="list/material">Открыть</button></div></div>';
  return '<div class="hero"><span class="counter" id="counter">1 / 3</span><div class="slides drag" id="slides">' + s1 + s2 + s3 +
    '</div><div class="dots" id="dots"><i class="on"></i><i></i><i></i></div></div>';
}

// Карусель картинок (подборки с сайтами): листается пальцем и мышью, счётчик 1/3.
function gallery(media, id) {
  if (!media || !media.length) return "";
  return '<div class="gal"><div class="gal-track drag" data-gal="' + id + '">' + media.map(function (m) {
    return '<img src="' + esc(m) + '" alt="" loading="lazy" draggable="false">';
  }).join("") + "</div>" + (media.length > 1 ? '<span class="gal-count">1 / ' + media.length + "</span>" : "") + "</div>";
}

function lessonPost(l) {
  return '<article class="post">' + logo() + "<div>" +
    '<div class="post-meta"><b>C&amp;C</b>' + kindName("lesson", l.free) + "</div>" +
    "<h3>" + esc(l.title) + "</h3>" + badgeArt(l, l.locked) +
    '<button class="pill" data-item="' + l.id + '">' + (l.locked ? "Что внутри" : l.done ? "Перечитать" : "Читать") + "</button></div></article>";
}
function pickPost(p) {
  return '<article class="post">' + logo() + "<div>" +
    '<div class="post-meta"><b>C&amp;C</b>Подборка' + (p.locked ? ", для резидентов" : "") + "</div>" +
    "<h3>" + esc(p.title) + "</h3>" + (p.subtitle ? '<p class="post-text">' + esc(p.subtitle) + "</p>" : "") +
    gallery(p.media, p.id) +
    '<button class="pill" data-item="' + p.id + '">Читать</button></div></article>';
}
function homeFeed() {
  var lessons = S.boot.lessons;
  var free = lessons.filter(function (l) { return l.free; });
  var closed = lessons.filter(function (l) { return !l.free; }).slice(0, 3);
  var list = free.slice(0, 6).concat(closed);
  var picks = (S.boot.picks || []).filter(function (p) { return p.media && p.media.length; });
  var out = [], k = 0;
  list.forEach(function (l, i) {
    out.push(lessonPost(l));
    if (i % 2 === 1 && picks[k]) out.push(pickPost(picks[k++]));
  });
  while (picks[k]) out.push(pickPost(picks[k++]));
  return out.join("");
}

function bindGalleries() {
  document.querySelectorAll(".gal-track").forEach(function (t) {
    var count = t.parentNode.querySelector(".gal-count");
    if (!count) return;
    var n = t.children.length;
    t.addEventListener("scroll", function () {
      var i = Math.round(t.scrollLeft / Math.max(1, t.clientWidth));
      count.textContent = (i + 1) + " / " + n;
    }, { passive: true });
  });
}

function nextLesson() {
  var ls = S.boot.lessons;
  return ls.filter(function (l) { return !l.locked && !l.done; })[0] || ls[0];
}

function viewHome() {
  var m = me();
  var nl = nextLesson();
  var started = S.boot.lessons.some(function (l) { return l.done; });
  return '<section class="view">' +
    '<div class="hello"><b>Привет, ' + esc(m.name) + "</b>" + avatar() + "</div>" +
    "<h1>Сообщество C&amp;C</h1><p class=\"lead\">Сайты, боты и первые клиенты вместе с нейросетями</p>" +
    slides() +
    '<div class="cta-row"><button class="btn glow" data-item="' + (nl ? nl.id : "") + '">' + ic("bolt") + (started ? "Продолжить курс" : "Начать с первого урока") + "</button></div>" +
    '<div class="chips drag">' +
      '<button class="chip" data-go="course">Курс</button>' +
      '<button class="chip" data-nav="@parser">Парсер</button>' +
      '<button class="chip" data-go="list/agent">AI-офис</button>' +
      '<button class="chip" data-go="marathon">Марафон</button>' +
      '<button class="chip" data-go="eval">Оценка работ</button>' +
      '<button class="chip" data-go="list/prompt">Промпты</button>' +
      '<button class="chip" data-go="list/material">Материалы</button>' +
    "</div>" +
    "<h2>Свежее в C&amp;C</h2>" + homeFeed() +
    "</section>";
}

function bindSlides() {
  var box = $("#slides");
  if (!box) return;
  var counter = $("#counter"), dots = document.querySelectorAll("#dots i");
  var step = function () { var f = box.firstElementChild; return f ? f.offsetWidth + 10 : box.clientWidth; };
  var update = function () {
    var i = Math.max(0, Math.min(2, Math.round(box.scrollLeft / step())));
    if (i === S.slide) return;
    S.slide = i;
    counter.textContent = (i + 1) + " / 3";
    dots.forEach(function (d, k) { d.classList.toggle("on", k === i); });
  };
  box.addEventListener("scroll", function () { window.requestAnimationFrame(update); }, { passive: true });
  box.addEventListener("touchstart", function () { S.userSlid = true; }, { passive: true });
  dots.forEach(function (d, k) { d.addEventListener("click", function () { S.userSlid = true; box.scrollTo({ left: k * step(), behavior: "smooth" }); }); });
  S.slide = 0;
  S.userSlid = false;
  clearInterval(S.slideTimer);
  S.slideTimer = setInterval(function () {
    if (S.userSlid || !document.body.contains(box) || document.hidden) return;
    var next = (S.slide + 1) % 3;
    box.scrollTo({ left: next * step(), behavior: "smooth" });
  }, 20000);
}

// ---------- Категории ----------

function viewCategories() {
  var c = S.boot.counts, mara = S.boot.marathon;
  var tile = function (go, icon, title, sub, cls, flag) {
    return '<button class="tile' + (cls ? " " + cls : "") + '" ' + go + '><div class="tile-top">' + ic(icon) + ic("arrow", "arr") + "</div><div><h3>" + title + "</h3><p>" + sub + "</p></div>" + (flag || "") + "</button>";
  };
  var lockFlag = resident() ? "" : '<span class="flag">' + ic("lock") + "часть закрыта</span>";
  return '<section class="view"><h1>Категории</h1><p class="lead">Курс, инструменты и материалы C&amp;C</p><div class="tiles">' +
    tile('data-go="course"', "cap", "Курс", c.modules + " " + plural(c.modules, "модуль", "модуля", "модулей") + ", " + c.lesson + " " + plural(c.lesson, "урок", "урока", "уроков"), "wide", lockFlag) +
    tile('data-nav="@parser"', "parser", "Парсер", "Клиенты с карт по нише и городу, скрипты для переписки", "tall") +
    tile('data-go="eval"', "gallery", "Оценка работ", "Пришли сайт, команда разберёт") +
    tile('data-go="marathon"', "run", "Марафон", "Первый заказ за " + mara.total + " " + plural(mara.total, "день", "дня", "дней") + ", бесплатно") +
    tile('data-go="list/material"', "doc", "Материалы", "Чек-листы, бриф, разборы") +
    tile('data-go="list/prompt"', "magic", "Промпты", c.prompt + " " + plural(c.prompt, "промпт", "промпта", "промптов") + " под задачи") +
    tile('data-go="list/resource"', "palette", "Ресурсы", "Референсы, шрифты, иконки") +
    tile('data-go="list/agent"', "users", "AI-офис", (c.agent || 0) + " " + plural(c.agent || 0, "помощник", "помощника", "помощников") + " с готовыми ролями") +
    "</div></section>";
}

// ---------- Курс и разделы (как у SGX) ----------

var SECTIONS = {
  lesson: { title: "Курс", icon: "cap", unit: ["урок", "урока", "уроков"], numbers: "Курс в цифрах",
    lead: "Вайбкодинг с нуля: от первого промпта до сайта, за который платят. Сайты, боты, поиск клиентов и сдача работы." },
  material: { title: "Материалы", icon: "doc", unit: ["материал", "материала", "материалов"], numbers: "Раздел в цифрах",
    lead: "Бриф, чек-лист сдачи, конструктор цены, штрафы и разборы реальных задач." },
  prompt: { title: "Промпты", icon: "magic", unit: ["промпт", "промпта", "промптов"], numbers: "Раздел в цифрах",
    lead: "Проверенные постановки задач: копируй, подставляй своё и получай результат с первого раза." },
  agent: { title: "AI-офис", icon: "users", unit: ["помощник", "помощника", "помощников"], numbers: "Раздел в цифрах",
    lead: "Помощники с готовыми ролями. Вставь роль в проект Claude или ChatGPT — и у тебя есть продажник, верстальщик и тестировщик." },
  resource: { title: "Ресурсы", icon: "palette", unit: ["подборка", "подборки", "подборок"], numbers: "Раздел в цифрах",
    lead: "Где брать референсы, компоненты, шрифты, иконки, цвета и анимации." }
};
function pad2(n) { return n < 10 ? "0" + n : String(n); }
function sectionItems(kind) {
  if (kind === "lesson") return S.boot.lessons;
  return S.cache["list:" + kind];
}
function viewSection(kind) {
  var meta = SECTIONS[kind];
  if (!meta) return viewNotFound();
  var items = sectionItems(kind);
  if (!items) {
    api("/api/content?kind=" + kind).then(function (d) { S.cache["list:" + kind] = d.items; render(); }).catch(showError);
    return '<section class="view"><h1>' + meta.title + '</h1><div class="skel" style="height:240px;margin-top:16px"></div></section>';
  }
  var groups = [];
  items.forEach(function (l) {
    var name = l.module || meta.title, g = groups[groups.length - 1];
    if (!g || g.name !== name) groups.push(g = { name: name, items: [] });
    g.items.push(l);
  });
  var free = items.filter(function (l) { return l.free; });
  var locked = items.filter(function (l) { return l.locked; });
  var done = items.filter(function (l) { return l.done; }).length;
  var u = meta.unit, R = resident();
  var sub = (groups.length > 1 ? groups.length + " " + plural(groups.length, "модуль", "модуля", "модулей") + ", " : "") +
    items.length + " " + plural(items.length, u[0], u[1], u[2]) + (free.length && !R ? ", " + free.length + " бесплатно" : "");
  var where = function (l) {
    var g = groups.filter(function (x) { return x.items.indexOf(l) >= 0; })[0];
    return (kind === "lesson" ? "Урок " + (g.items.indexOf(l) + 1) + ", " : "") + (g.name === meta.title ? (l.subtitle || "") : g.name);
  };
  var numbers = '<div class="card nums"><h3>' + meta.numbers + '</h3><div class="nums-row">' +
    (groups.length > 1 ? '<div><b>' + groups.length + "</b><span>" + plural(groups.length, "модуль", "модуля", "модулей") + "</span></div>" : "") +
    "<div><b>" + items.length + "</b><span>" + plural(items.length, u[0], u[1], u[2]) + "</span></div>" +
    (R ? "<div><b>" + done + "</b><span>пройдено</span></div>" : "<div><b>" + free.length + "</b><span>бесплатно</span></div>") + "</div>" +
    '<div class="segs">' + items.map(function (l) { return '<i class="' + (l.done ? "d" : !l.locked ? "f" : "") + '"></i>'; }).join("") + "</div>" +
    '<p class="muted small">' + (R ? "Пройдено " + done + " из " + items.length : free.length + " из " + items.length + " открыты бесплатно") + "</p></div>";
  var start = !R && free.length ? "<h2>Начать бесплатно</h2><div class=\"cards\">" + free.map(function (l) {
    return '<button class="lcard" data-item="' + l.id + '"><span class="sq">' + ic(l.done ? "check" : "doc") + '</span><span class="row-text"><b>' + esc(l.title) + "</b><span>" + esc(where(l)) + "</span></span></button>";
  }).join("") + "</div>" : "";
  var more = !R && locked.length ? '<div class="card more"><h3>Ещё ' + locked.length + " " + plural(locked.length, u[0], u[1], u[2]) + ' для резидентов</h3><p class="muted">Полная программа открывается сразу после оплаты. Список ниже.</p><button class="btn main" data-go="join">Получить доступ</button></div>' : "";
  var list = groups.map(function (g) {
    return "<h2>" + esc(g.name) + '</h2><div class="cards">' + g.items.map(function (l, k) {
      var st = l.done ? "Пройдено" : l.locked ? "Для резидентов" : l.free && !R ? "Бесплатно" : (l.minutes ? l.minutes + " мин" : "Открыто");
      return '<button class="nrow' + (l.locked ? " lock" : "") + (l.done ? " done" : "") + '" data-item="' + l.id + '"><span class="num">' + pad2(k + 1) + '</span><span class="row-text"><b>' + esc(l.title) + "</b><span>" + st + '</span></span><span class="row-end">' + ic(l.done ? "check" : l.locked ? "lock" : "play") + "</span></button>";
    }).join("") + "</div>";
  }).join("");
  return '<section class="view section"><h1>' + meta.title + '</h1><p class="lead">' + sub + "</p>" +
    '<div class="art big">' + badge(meta.icon, true) + "</div>" +
    '<p class="sec-lead">' + meta.lead + "</p>" + numbers + start + more + list + "</section>";
}
function lessonRow(l) {
  var end = l.done ? ic("check") : l.locked ? ic("lock") : (l.minutes ? l.minutes + " мин" : ic("chev"));
  return '<button class="row' + (l.done ? " done" : "") + '" data-item="' + l.id + '"><span class="ava">' + ic(l.done ? "check" : (l.icon || "doc")) + '</span><span class="row-text"><b>' + esc(l.title) + "</b><span>" + esc(l.subtitle) + '</span></span><span class="row-end">' + end + "</span></button>";
}

// ---------- Страница материала ----------

function viewItem(id) {
  var item = S.cache["item:" + id];
  if (!item) {
    api("/api/content/" + id).then(function (d) { S.cache["item:" + id] = d; render(); }).catch(showError);
    return '<section class="view"><div class="skel" style="height:24px;width:60%;margin-top:22px"></div><div class="skel" style="height:190px;margin-top:18px"></div><div class="skel" style="height:220px;margin-top:18px"></div></section>';
  }
  var head = '<div class="crumbs"><span class="ava">' + ic(item.icon || "code") + "</span><b>C&amp;C</b>" + kindName(item.kind, item.free) +
    (item.minutes ? " · " + item.minutes + " мин" : "") + "</div><h1>" + esc(item.title) + "</h1>" +
    (item.subtitle ? '<p class="lead">' + esc(item.subtitle) + "</p>" : "");
  if (item.locked) {
    var reason = item.closed_reason;
    return '<section class="view lesson">' + head + badgeArt(item, true) +
      (item.intro ? '<div class="md"><p>' + inline(esc(item.intro)) + "</p></div>" : "") +
      (item.outline && item.outline.length ? "<h2>Что внутри</h2><ul class=\"outline\">" + item.outline.map(function (o) { return "<li>" + ic("lock") + esc(o) + "</li>"; }).join("") + "</ul>" : "") +
      '<p class="blurred">Здесь продолжение: пошаговые действия, примеры и готовые формулировки, которые можно сразу применить в работе с клиентом.</p>' +
      (reason ? '<div class="locked-card">' + ic("calendar") + "<h3>" + esc(reason) + "</h3><p>Марафон идёт по дню в день: так задания успевают сработать.</p><button class=\"btn main\" data-go=\"marathon\">К марафону</button></div>"
        : '<div class="locked-card">' + ic("lock") + "<h3>" + (item.kind === "lesson" ? "Урок для резидентов" : "Открыто резидентам") + "</h3><p>Откроется сразу после оплаты вместе с курсом, парсером, AI-офисом и закрытой группой.</p><button class=\"btn main\" data-go=\"join\">Стать резидентом</button></div>") +
      "</section>";
  }
  var next = item.next;
  var nextBlock = next ? '<p class="next-hint">' + (item.kind === "lesson" ? "В следующем уроке: " : "Дальше: ") + esc(next.subtitle || next.title).replace(/^./, function (c) { return c.toLowerCase(); }) + ".</p>" : "";
  return '<section class="view lesson">' + head + (item.media && item.media.length ? gallery(item.media, item.id) : badgeArt(item, false)) +
    '<div class="md">' + md(item.body) + "</div>" +
    nextBlock +
    '<button class="btn" data-act="done" data-id="' + item.id + '">' + (item.done ? ic("check") + "Пройдено" : "Отметить пройденным") + "</button>" +
    '<button class="btn" data-act="share" data-id="' + item.id + '">Переслать</button>' +
    (next ? '<button class="btn main" data-item="' + next.id + '"><span class="ell">Дальше: ' + esc(next.title) + "</span></button>" :
      item.kind === "lesson" ? '<button class="btn main" data-go="course">К списку уроков</button>' : "") +
    "</section>";
}

// ---------- Марафон ----------

function viewMarathon() {
  var m = S.boot.marathon;
  var pct = m.total ? Math.round(m.done / m.total * 100) : 0;
  var cur = m.current;
  return '<section class="view"><h1>Марафон «Первый заказ»</h1><p class="lead">' + m.total + " " + plural(m.total, "день", "дня", "дней") + " по 20–40 минут. Бесплатно для всех. Новый день открывается на следующий день после выполненного.</p>" +
    '<div class="mara-head"><div class="ringp" style="--p:' + pct + '"><b>' + m.done + "/" + m.total + "</b></div><div>" +
    (cur ? "<h3>День " + cur.day + ": " + esc(cur.title) + '</h3><p class="muted small" style="margin:0">' + (cur.open ? "Открыт, можно начинать" : esc(cur.reason)) + "</p>" :
      "<h3>Марафон пройден</h3><p class=\"muted small\" style=\"margin:0\">Повторяй эту неделю, пока не возьмёшь заказ.</p>") + "</div></div>" +
    (cur && cur.open ? '<div class="cta-row"><button class="btn glow" data-item="' + cur.id + '">' + ic("bolt") + "Открыть день " + cur.day + "</button></div>" : "") +
    '<h2>Все дни</h2><div class="rows">' + m.days.map(function (d) {
      var now = cur && cur.id === d.id;
      return '<button class="row day' + (d.done ? " done" : "") + (!d.open ? " lock" : "") + (now ? " now" : "") + '" data-item="' + d.id + '"><span class="ava">' + (d.done ? ic("check") : d.day) + '</span><span class="row-text"><b>' + esc(d.title) + "</b><span>" + esc(d.open || d.done ? d.subtitle : d.reason) + '</span></span><span class="row-end">' + (d.open ? ic("chev") : ic("lock")) + "</span></button>";
    }).join("") + "</div></section>";
}

// ---------- Оценка работ ----------

function viewEval() {
  var e = S.eval;
  if (!e) {
    api("/api/eval").then(function (d) { S.eval = d; render(); }).catch(showError);
    return '<section class="view"><h1>Оценка работ</h1><div class="skel" style="height:300px;margin-top:18px"></div></section>';
  }
  var q = e.quota;
  var status = { "new": "в очереди", work: "смотрим", done: "готово", rejected: "отклонено" };
  var thumbs = S.files.map(function (f, i) {
    return '<div class="thumb">' + (f.type.indexOf("video") === 0 ? '<video src="' + f.url + '" muted playsinline></video>' : '<img src="' + f.url + '" alt="">') +
      '<button data-act="unfile" data-i="' + i + '" aria-label="Убрать">' + ic("close") + "</button></div>";
  }).join("");
  var canAdd = S.files.length < e.max_files;
  return '<section class="view"><h1>Оценка работ</h1><p class="lead">Пришли скриншоты или видео сайта — команда разберёт по пяти пунктам и подскажет, что улучшить. Ответ придёт в чат с ботом.</p>' +
    '<div class="card"><div class="kv" style="border:0;padding:0"><span>Доступно оценок</span><b>' + q.available + "</b></div>" +
    (q.credits ? '<p class="muted small" style="margin:6px 0 0">Бесплатных: ' + q.free_left + ", от тарифа: " + q.credits + "</p>" : "") + "</div>" +
    (q.available > 0 ?
      '<input type="file" id="files" accept="image/*,video/*" multiple hidden>' +
      (S.files.length ? '<div class="thumbs">' + thumbs + (canAdd ? '<button class="thumb add" data-act="pick" aria-label="Добавить">' + ic("plus") + "</button>" : "") + "</div>" :
        '<button class="drop" data-act="pick">' + ic("gallery_add") + "<b>Выбрать скриншоты или видео</b><span>До " + e.max_files + " файлов: главный экран, пару страниц и вид с телефона</span></button>") +
      '<label class="field"><span>Ссылка на сайт, если есть</span><input class="input" id="ev-url" inputmode="url" placeholder="mysite.ru" value="' + esc(S.evUrl || "") + '"></label>' +
      '<label class="field"><span>Что важно оценить</span><textarea class="input" id="ev-comment" placeholder="Например: понятно ли, куда нажать, чтобы записаться">' + esc(S.evComment || "") + "</textarea></label>" +
      '<div class="upbar" id="upbar" hidden><i></i></div>' +
      '<div class="cta-row"><button class="btn main" data-act="send-eval"' + (S.files.length ? "" : " disabled") + ">Отправить на оценку</button></div>"
      : '<div class="locked-card">' + ic("gallery") + "<h3>Оценки закончились</h3><p>Резиденты получают " + "новые оценки с каждой оплатой тарифа.</p>" + (resident() ? '<button class="btn" data-act="support">Написать в поддержку</button>' : '<button class="btn main" data-go="join">Стать резидентом</button>') + "</div>") +
    (e.reviews.length ? '<h2>Мои заявки</h2><div class="rows">' + e.reviews.map(function (r) {
      return '<div class="row"><span class="ava">' + ic("gallery") + '</span><span class="row-text"><b>Заявка #' + r.id + "</b><span>" + esc(r.url || "без ссылки") + "</span></span>" +
        '<span class="status' + (r.status === "done" ? " done" : "") + '">' + (status[r.status] || r.status) + (r.status === "done" && r.total != null ? " · " + r.total + "/10" : "") + "</span></div>";
    }).join("") + "</div>" : "") +
    "</section>";
}

function addFiles(list) {
  var max = S.eval ? S.eval.max_files : 10;
  Array.prototype.forEach.call(list, function (f) {
    if (S.files.length >= max) return;
    if (!/^(image|video)\//.test(f.type)) { toast("Подходят только картинки и видео"); return; }
    if (f.size > 20 * 1024 * 1024) { toast("«" + f.name + "» больше 20 МБ"); return; }
    S.files.push({ file: f, type: f.type, url: URL.createObjectURL(f) });
  });
  render();
}

function sendEval() {
  saveEvalFields();
  var total = S.files.reduce(function (s, f) { return s + f.file.size; }, 0);
  if (total > 60 * 1024 * 1024) { toast("Вместе файлы больше 60 МБ — убери пару"); return; }
  var fd = new FormData();
  S.files.forEach(function (f) { fd.append("files", f.file, f.file.name); });
  fd.append("url", S.evUrl || "");
  fd.append("comment", S.evComment || "");
  var btn = $('[data-act="send-eval"]'), bar = $("#upbar");
  btn.disabled = true; btn.textContent = "Отправляю…";
  bar.hidden = false;
  var x = new XMLHttpRequest();
  x.open("POST", "/api/eval/submit");
  x.setRequestHeader("X-Init-Data", tg && tg.initData ? tg.initData : "");
  x.upload.onprogress = function (e) { if (e.lengthComputable) bar.firstChild.style.width = Math.round(e.loaded / e.total * 100) + "%"; };
  x.onload = function () {
    var data = {};
    try { data = JSON.parse(x.responseText); } catch (e) {}
    if (x.status >= 200 && x.status < 300) {
      haptic("ok");
      S.files.forEach(function (f) { URL.revokeObjectURL(f.url); });
      S.files = []; S.evUrl = ""; S.evComment = ""; S.eval = null;
      toast("Заявка #" + data.id + " отправлена. Ответ придёт в чат с ботом");
      render();
    } else {
      var d = data.detail; toast((d && d.message) || d || "Не получилось отправить");
      btn.disabled = false; btn.textContent = "Отправить на оценку"; bar.hidden = true;
    }
  };
  x.onerror = function () { toast("Нет связи с сервером"); btn.disabled = false; btn.textContent = "Отправить на оценку"; bar.hidden = true; };
  x.send(fd);
}
function saveEvalFields() {
  var u = $("#ev-url"), c = $("#ev-comment");
  if (u) S.evUrl = u.value.trim();
  if (c) S.evComment = c.value.trim();
}

// ---------- Сообщество и тарифы ----------

// «Что входит» как у SGX: столбцы — тарифы с ценой, строки — что даёт каждый. Цены и сроки — из админки.
function accessWord(t) {
  if (!t.days) return "навсегда";
  if (t.days === 30) return "пока платишь";
  return t.days + " " + plural(t.days, "день", "дня", "дней");
}
function priceShort(t) {
  return money(t.price) + (t.days === 30 ? "/мес" : "");
}
function compareTable(tariffs) {
  var on = function (t) { return t.id === S.tariff ? " on" : ""; };
  var yes = function (t) { return '<td class="' + on(t).trim() + '">' + ic("check") + "</td>"; };
  var no = function (t) { return '<td class="no' + on(t) + '">—</td>'; };
  var row = function (label, cell) { return "<tr><td>" + label + "</td>" + tariffs.map(cell).join("") + "</tr>"; };
  return '<div class="card"><table class="compare"><thead><tr><th></th>' + tariffs.map(function (t) {
      return '<th class="' + on(t).trim() + '">' + priceShort(t) + "</th>";
    }).join("") + "</tr></thead><tbody>" +
    row("Курс, парсер, AI-офис, материалы", yes) +
    row("Закрытая группа резидентов", yes) +
    row("Доступ", function (t) { return '<td class="word' + on(t) + '">' + accessWord(t) + "</td>"; }) +
    row("Наставник до первого кейса", function (t) { return t.id === "mentor" ? yes(t) : no(t); }) +
    "</tbody></table></div>";
}

function tariffCard(t) {
  var per = t.days ? " / " + (t.days === 30 ? "месяц" : t.days + " " + plural(t.days, "день", "дня", "дней")) : " навсегда";
  var tag = !t.active ? '<span class="tariff-tag">' + ic("lock") + "Закрыто" + "</span>" :
    t.id === "mentor" ? '<span class="tariff-tag">' + (t.seats_left > 0 ? "Мест на неделе: " + t.seats_left : "Мест нет до понедельника") + "</span>" :
    (t.badge ? '<span class="tariff-tag">' + esc(t.badge) + "</span>" : "");
  var sel = S.tariff === t.id && t.available;
  return '<button class="tariff' + (sel ? " sel" : "") + (!t.available ? " off" : "") + '" data-tariff="' + t.id + '">' +
    '<div class="tariff-head"><span>' + esc(t.title) + "</span>" + tag + "</div>" +
    '<div class="price">' + (t.active ? money(t.price) : "Скоро откроется") + (t.active ? "<small>" + per + "</small>" : "") + "</div>" +
    '<div class="muted small">' + esc(t.subtitle) + "</div>" +
    "<ul>" + (t.features || []).map(function (f) { return "<li>" + ic("check") + "<span>" + esc(f) + "</span></li>"; }).join("") + "</ul>" +
    (t.note ? '<p class="note">' + esc(t.note) + "</p>" : "") + "</button>";
}

function payButtons() {
  var t = (S.boot.tariffs || []).filter(function (x) { return x.id === S.tariff; })[0];
  if (!t || !t.available) return "";
  var m = S.boot.methods;
  var out = "";
  if (m.indexOf("card") >= 0 && t.card) out += '<button class="btn main" data-pay="card">Оплатить картой · ' + money(t.price) + "</button>";
  if (m.indexOf("crypto") >= 0) out += '<button class="btn" data-pay="crypto">Оплатить криптой</button>';
  if (m.indexOf("stars") >= 0 && t.stars) out += '<button class="btn" data-pay="stars">Оплатить звёздами · ' + t.stars + " ⭐</button>";
  if (!out) out = '<button class="btn main" data-act="pay-support">Оплатить</button>';
  return out;
}

function viewCommunity(scrollTo) {
  var c = S.boot.counts, n = S.boot.community.members, tariffs = S.boot.tariffs;
  if (!S.tariff) S.tariff = (tariffs.filter(function (t) { return t.available; })[0] || tariffs[0]).id;
  var a = me().access;
  var inside = [
    ["cap", "Курс с нуля", c.lesson + " уроков: от первого промпта до сайта, за который платят"],
    ["parser", "Парсер клиентов", "Бизнесы с телефонами по нише и городу и скрипты для переписки"],
    ["users", "AI-офис", (c.agent || 0) + " помощников с готовыми ролями для Claude и ChatGPT"],
    ["gallery", "Оценка работ", "Команда разбирает твой сайт и говорит, что улучшить"],
    ["run", "Марафон", "Первый заказ за " + c.marathon + " дней, по заданию в день"],
    ["magic", "Промпты", "Проверенные постановки задач для сайтов и ботов"],
    ["doc", "Материалы", "Бриф, чек-лист сдачи, конструктор цены"],
    ["users", "Закрытая группа", "Резиденты, вопросы, разборы и новости"]
  ];
  var reviews = S.boot.reviews || [];
  var html = '<section class="view">' +
    '<div class="hero" style="margin-top:14px"><div class="slides"><div class="slide s-logo"><div class="capsule"><span class="bird">' + BIRD + "</span><b>C&amp;C Family</b></div>" + video("intro") +
    '<div class="slide-foot"><span>' + membersText(n) + "</span>" + (a.resident ? '<span class="pill">Ты резидент</span>' : '<button class="pill" data-act="to-tariffs">Оплатить</button>') + "</div></div></div></div>" +
    "<h1>C&amp;C Family</h1><p class=\"lead\">Закрытое сообщество про вайбкодинг и нейросети. Учишься с нуля, собираешь сайты и ботов вместе с агентами и продаёшь их местному бизнесу.</p>" +
    "<h2>Что внутри</h2><div class=\"tiles inside\">" + inside.map(function (t) {
      return '<div class="tile"><div class="tile-top">' + ic(t[0]) + "</div><div><h3>" + t[1] + "</h3><p>" + t[2] + "</p></div></div>";
    }).join("") + "</div>" +
    "<h2>Как это работает</h2><div class=\"steps\">" +
      step("cap", "Учишься", "Курс, словарь и промпты с нуля") + arrow() +
      step("code", "Собираешь", "Сайты и боты вместе с нейросетью") + arrow() +
      step("parser", "Находишь клиентов", "Парсер приносит бизнесы без сайта") + arrow() +
      step("chat", "Пишешь по скриптам", "Готовые сообщения и разговор о цене") + arrow() +
      '<div class="step goal">' + ic("wallet") + "<div><b>Проект, за который платят</b><span>Сайт или бот для реального бизнеса</span></div></div>" +
    "</div>" +
    (reviews.length ? '<h2>Отзывы</h2><div class="reviews">' + reviews.map(function (r) {
      return '<div class="review"><p>' + esc(r.text) + "</p><b>" + esc(r.name) + "</b><span>" + esc(r.role) + "</span></div>";
    }).join("") + "</div>" : "") +
    "<h2>Кому зайдёт</h2><ul class=\"checks\">" +
      check("Только заходишь в нейросети и не хочешь месяцами сидеть на туториалах") +
      check("Фрилансеру, которому надоело работать за копейки") +
      check("Дизайнеру или маркетологу, который хочет собирать продукты сам") +
      check("Тому, кто уже пробует вайбкодить, но не понимает, как продавать") +
    "</ul>" +
    '<h2>Чего не обещаем</h2><div class="card"><p style="margin:0">Сеньором за неделю ты не станешь, и деньги сами не придут. C&amp;C даёт систему: что делать, в каком порядке и где брать клиентов. Дальше — твои руки и регулярность.</p></div>' +
    '<h2>Что входит</h2><div id="compare">' + compareTable(tariffs) + "</div>" +
    '<h2 id="tariffs">Тарифы</h2>' +
    (a.resident ? '<div class="card ring"><h3>Ты резидент</h3><p class="muted" style="margin:0">' + (a.forever ? "Доступ навсегда." : a.until ? "Доступ до " + fmtDate(a.until) + ". Продлить можно ниже — дни добавятся." : "Доступ через закрытую группу.") + "</p></div>" : "") +
    tariffs.map(tariffCard).join("") +
    '<div id="paybox">' + payButtons() + "</div>" +
    '<button class="paid-row" data-act="check-access"><span class="ava">' + ic("check") + '</span><span><b>Я уже оплатил</b><span>Проверим оплату и участие в группе, доступ откроется сразу</span></span><span class="chevr">' + ic("chev") + "</span></button>" +
    "<h2>Бесплатно до оплаты</h2><div class=\"tags\">" + S.boot.lessons.filter(function (l) { return l.free; }).map(function (l) {
      return '<button class="chip" data-item="' + l.id + '">' + esc(l.title) + "</button>";
    }).join("") + '<button class="chip" data-go="marathon">Марафон «Первый заказ»</button></div>' +
    "</section>";
  if (scrollTo) setTimeout(function () { var el = $("#tariffs"); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }, 80);
  return html;
}
function step(icon, title, sub) { return '<div class="step">' + ic(icon) + "<div><b>" + title + "</b><span>" + sub + "</span></div></div>"; }
function arrow() { return '<div class="step-arrow">' + ic("arrow") + "</div>"; }
function stat(v, label) { return '<div class="stat"><b>' + esc(v) + "</b><span>" + label + "</span></div>"; }
function check(t) { return "<li>" + ic("check") + "<span>" + t + "</span></li>"; }

function pay(method) {
  var t = S.tariff;
  var btn = $('[data-pay="' + method + '"]');
  if (btn) btn.disabled = true;
  api("/api/checkout", { method: "POST", body: { tariff: t, method: method } }).then(function (res) {
    if (btn) btn.disabled = false;
    S.waitingPay = Date.now();
    if (res.kind === "invoice" && tg && tg.openInvoice) {
      tg.openInvoice(res.url, function (status) {
        if (status === "paid") { haptic("ok"); toast("Оплата прошла, открываю доступ"); waitAccess(); }
        else if (status === "failed") toast("Платёж не прошёл. Попробуй ещё раз или напиши в поддержку");
      });
    } else {
      openLink(res.url);
      toast("После оплаты вернись сюда — доступ откроется сам");
    }
  }).catch(function (e) { if (btn) btn.disabled = false; toast(e.message); });
}

function waitAccess(tries) {
  tries = tries || 0;
  api("/api/access/check", { method: "POST" }).then(function (r) {
    if (r.access.resident) { S.waitingPay = 0; return reloadBoot().then(function () { toast("Доступ открыт. Ссылка в группу — в чате с ботом"); }); }
    if (tries < 10) setTimeout(function () { waitAccess(tries + 1); }, 3000);
  }).catch(function () {});
}

document.addEventListener("visibilitychange", function () {
  // Вернулся из CryptoBot — проверяем оплату.
  if (!document.hidden && S.waitingPay && Date.now() - S.waitingPay < 30 * 60 * 1000 && !resident()) waitAccess(5);
});

// ---------- Профиль ----------

function viewProfile() {
  var m = me(), a = m.access;
  var status = a.admin ? "Админ" : a.resident ? "Резидент" : "Гость";
  var accessText = a.resident ?
    (a.forever ? "Доступ навсегда." : a.until ? "Доступ до " + fmtDate(a.until) + "." : "Доступ через закрытую группу.") + " Все уроки, парсер и скрипты открыты." :
    "Открытые уроки, марафон и бесплатные материалы уже доступны. Полный доступ — у резидентов сообщества.";
  return '<section class="view"><h1>Профиль</h1>' +
    '<div class="me">' + avatar(true) + "<div><b>" + esc(m.name + (m.last_name ? " " + m.last_name : "")) + "</b><span>" + status + "</span></div></div>" +
    '<div class="card"><h3>Доступ к C&amp;C Family</h3><p class="muted">' + accessText + "</p>" +
    (a.resident ? '<button class="btn" data-go="community">Что входит</button>' : '<button class="btn main" data-go="join">Стать резидентом</button>') + "</div>" +
    "<h2>Настройки</h2>" +
    '<div class="set">' +
      '<button class="set-row" data-act="theme"><span class="t"><b>Тёмная тема</b><span>Цвет приложения</span></span><span class="switch' + (theme() === "dark" ? " on" : "") + '" role="switch" aria-checked="' + (theme() === "dark") + '"></span></button>' +
      '<button class="set-row" data-act="notify"><span class="t"><b>Уведомления</b><span>Бот напишет, когда выйдет урок, промпт или пост</span></span><span class="switch' + (m.notify ? " on" : "") + '" role="switch" aria-checked="' + !!m.notify + '"></span></button>' +
    "</div>" +
    '<div class="set">' +
      (a.resident && links().group && !a.group ? '<button class="set-row" data-act="group"><span class="ava">' + ic("users") + '</span><span class="t"><b>Закрытая группа</b><span>Подай заявку — бот одобрит сам</span></span>' + ic("chev") + "</button>" : "") +
      '<button class="set-row" data-act="check-access"><span class="ava">' + ic("check") + '</span><span class="t"><b>Проверить доступ</b><span>Если уже состоишь в закрытой группе или оплатил</span></span>' + ic("chev") + "</button>" +
      '<button class="set-row" data-act="support"><span class="ava">' + ic("chat") + '</span><span class="t"><b>Поддержка</b><span>Связаться с командой</span></span>' + ic("chev") + "</button>" +
      (a.admin ? '<button class="set-row" data-go="admin"><span class="ava">' + ic("settings") + '</span><span class="t"><b>Админка</b><span>Люди, оплаты, тарифы, материалы, рассылки</span></span>' + ic("chev") + "</button>" : "") +
    "</div>" +
    '<p class="credit">Иконки Solar, 480 Design, CC BY 4.0 · Шрифт Onest, OFL</p>' +
    "</section>";
}

function viewNotFound() {
  return '<section class="view">' + empty("question", "Такой страницы нет.", '<button class="btn main" data-go="">На главную</button>') + "</section>";
}

// ---------- Админка ----------

var ATABS = [["overview", "Обзор"], ["users", "Люди"], ["payments", "Оплаты"], ["tariffs", "Тарифы"], ["content", "Материалы"], ["broadcast", "Рассылка"], ["texts", "Тексты"], ["settings", "Ещё"]];

function viewAdmin(tab) {
  if (!isAdmin()) return viewNotFound();
  tab = tab || S.admin.tab;
  S.admin.tab = tab;
  var body = ({ overview: adminOverview, users: adminUsers, payments: adminPayments, tariffs: adminTariffs, content: adminContent,
    broadcast: adminBroadcast, texts: adminTexts, settings: adminSettings }[tab] || adminOverview)();
  return '<section class="view"><h1>Админка</h1><div class="atabs">' + ATABS.map(function (t) {
    return '<button class="chip' + (t[0] === tab ? " on" : "") + '" data-go="admin/' + t[0] + '">' + t[1] + "</button>";
  }).join("") + "</div>" + body + "</section>";
}

function loading(key, url, map) {
  if (S.admin[key] === undefined || S.admin[key] === null) {
    S.admin[key] = false;
    api(url).then(function (d) { S.admin[key] = map ? map(d) : d; render(); }).catch(function (e) { S.admin[key] = null; showError(e); });
  }
  return S.admin[key] ? S.admin[key] : null;
}
var SKEL = '<div class="skel" style="height:260px"></div>';

function adminOverview() {
  var d = loading("overview", "/api/admin/overview");
  if (!d) return SKEL;
  var max = Math.max.apply(null, d.days.map(function (x) { return x.new + x.paid; }).concat([1]));
  var conv = d.checkouts_month ? Math.round(d.buyers_month / d.checkouts_month * 100) : 0;
  return '<div class="stats">' +
    stat(d.users, "всего в боте, " + d.new_day + " за сутки") + stat(d.residents, "резидентов сейчас") +
    stat(money(d.revenue_month), "оплат за 30 дней (" + d.paid_month + ")") + stat(conv + "%", "открыли оплату → оплатили") +
    stat(d.active_day, "открывали приложение за сутки") + stat(d.members, "участников показываем") +
    "</div>" +
    '<div class="card" style="margin-top:10px"><h3>14 дней</h3><div class="bars">' + d.days.map(function (x) {
      return '<div><i class="p" style="height:' + (x.paid / max * 100) + '%"></i><i style="height:' + (x.new / max * 100) + '%"></i></div>';
    }).join("") + '</div><div class="legend"><span><i></i>новые</span><span><i class="p"></i>оплаты</span></div></div>' +
    '<div class="card"><h3>Как настроено</h3>' +
      '<div class="kv"><span>Оплата картой</span><b>' + (d.methods.indexOf("card") >= 0 ? "включена" : "не подключена") + "</b></div>" +
      '<div class="kv"><span>Оплата криптой</span><b>' + (d.methods.indexOf("crypto") >= 0 ? "включена" : "не подключена") + "</b></div>" +
      '<div class="kv"><span>Закрытая группа</span><b>' + (d.group ? "подключена" : "не указана") + "</b></div>" +
      '<div class="kv"><span>Всего оплат</span><b>' + money(d.revenue_all) + "</b></div>" +
    "</div>" +
    "<h2>Админки разделов</h2><div class=\"set\">" +
      '<button class="set-row" data-nav="@parser"><span class="ava">' + ic("parser") + '</span><span class="t"><b>Парсер и скрипты</b><span>Вкладка «Админ»: лимиты, ключи, лиды, скрипты</span></span>' + ic("chev") + "</button>" +
      '<button class="set-row" data-nav="@eval"><span class="ava">' + ic("gallery") + '</span><span class="t"><b>Оценка работ</b><span>Заявки, оценки, переписка</span></span>' + ic("chev") + "</button>" +
    "</div>";
}

function userRow(u) {
  var a = u.access;
  var st = a.admin ? "админ" : a.resident ? (a.forever ? "навсегда" : a.until ? "до " + fmtDate(a.until) : "группа") : u.banned ? "бан" : "гость";
  return '<button class="row" data-user="' + u.id + '"><span class="ava">' + (u.photo ? '<img src="' + esc(u.photo) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:12px">' : esc((u.name || u.username || "?").charAt(0))) + '</span><span class="row-text"><b>' + esc(u.name || "Без имени") + "</b><span>" + (u.username ? "@" + esc(u.username) + " · " : "") + u.id + (u.blocked_bot ? " · остановил бота" : "") + '</span></span><span class="status' + (a.resident ? " done" : "") + '">' + st + "</span></button>";
}
function adminUsers() {
  var d = loading("users", "/api/admin/users?q=" + encodeURIComponent(S.admin.q) + "&filter=" + S.admin.filter, function (x) { return x.users; });
  var filters = [["all", "Все"], ["residents", "Резиденты"], ["guests", "Гости"], ["banned", "Бан"]];
  return '<input class="input" id="user-q" placeholder="Имя, @username или ID" value="' + esc(S.admin.q) + '" enterkeyhint="search">' +
    '<div class="chips">' + filters.map(function (f) { return '<button class="chip' + (S.admin.filter === f[0] ? " on" : "") + '" data-ufilter="' + f[0] + '">' + f[1] + "</button>"; }).join("") + "</div>" +
    '<div style="height:12px"></div>' +
    (d === null ? SKEL : d.length ? '<div class="rows">' + d.map(userRow).join("") + "</div>" : empty("users", "Никого не нашли."));
}
function userSheet(id) {
  var u = (S.admin.users || []).filter(function (x) { return x.id === id; })[0];
  if (!u) return;
  var a = u.access;
  sheet('<h2>' + esc(u.name || "Без имени") + "</h2>" +
    '<div class="card"><div class="kv"><span>ID</span><b>' + u.id + "</b></div>" +
    (u.username ? '<div class="kv"><span>Username</span><b>@' + esc(u.username) + "</b></div>" : "") +
    '<div class="kv"><span>Доступ</span><b>' + (a.admin ? "админ" : a.resident ? (a.forever ? "навсегда" : a.until ? "до " + fmtDate(a.until) : "через группу") : "нет") + "</b></div>" +
    '<div class="kv"><span>Пришёл</span><b>' + fmtDate(u.created_at) + (u.source ? " · " + esc(u.source) : "") + "</b></div>" +
    '<div class="kv"><span>Бот</span><b>' + (u.blocked_bot ? "остановил" : u.started ? "запускал" : "не запускал") + "</b></div></div>" +
    "<h3>Выдать доступ</h3><div class=\"btns\">" +
      '<button class="btn" data-grant="30" data-uid="' + u.id + '">+30 дней</button>' +
      '<button class="btn" data-grant="90" data-uid="' + u.id + '">+90 дней</button>' +
      '<button class="btn" data-grant="0" data-uid="' + u.id + '">Навсегда</button>' +
    "</div>" +
    '<div class="btns">' +
      (a.resident && !a.admin ? '<button class="btn line" data-revoke="' + u.id + '">Закрыть доступ</button>' : "") +
      (!a.admin ? '<button class="btn line" data-ban="' + u.id + '" data-v="' + (u.banned ? 0 : 1) + '">' + (u.banned ? "Разбанить" : "Забанить") + "</button>" : "") +
      (u.username ? '<button class="btn line" data-chat="' + esc(u.username) + '">Написать</button>' : "") +
    "</div>");
}

function adminPayments() {
  var d = loading("payments", "/api/admin/payments?status=" + S.admin.pstatus, function (x) { return x.payments; });
  var f = [["", "Все"], ["paid", "Оплачены"], ["pending", "Ждут"], ["expired", "Истекли"]];
  var st = { paid: "оплачен", pending: "ждёт", expired: "истёк", cancelled: "отменён" };
  var mt = { card: "карта", crypto: "крипта", stars: "звёзды", manual: "вручную" };
  return '<div class="chips" style="margin-top:0">' + f.map(function (x) { return '<button class="chip' + (S.admin.pstatus === x[0] ? " on" : "") + '" data-pfilter="' + x[0] + '">' + x[1] + "</button>"; }).join("") + "</div><div style=\"height:12px\"></div>" +
    (d === null ? SKEL : d.length ? '<div class="rows">' + d.map(function (p) {
      var who = p.username ? "@" + p.username : (p.first_name || p.user_id);
      return '<div class="row"><span class="ava">' + ic(p.method === "crypto" ? "crypto" : "card") + '</span><span class="row-text"><b>' + (p.method === "stars" ? p.amount + " ⭐" : money(p.amount)) + " · " + esc(who) + "</b><span>" + esc(p.tariff) + " · " + (mt[p.method] || p.method) + " · " + fmtDate(p.created_at) + "</span></span>" +
        (p.status === "pending" ? '<button class="btn sm" data-confirm="' + p.id + '">Подтвердить</button>' : '<span class="status' + (p.status === "paid" ? " done" : "") + '">' + (st[p.status] || p.status) + "</span>") + "</div>";
    }).join("") + "</div>" : empty("wallet", "Оплат пока нет."));
}

function adminTariffs() {
  var d = loading("tariffs", "/api/admin/tariffs", function (x) { return x.tariffs; });
  if (!d) return SKEL;
  return d.map(function (t, i) {
    return '<div class="card" data-tform="' + i + '"><h3>' + (t.id === "mentor" ? "Тариф 2 · с наставником" : "Тариф 1 · материалы и инструменты") + "</h3>" +
      field("Название", "title", t.title) + field("Подзаголовок", "subtitle", t.subtitle) +
      '<div class="grid2">' + field("Цена, ₽", "price", t.price, "number") + field("Дней (0 — навсегда)", "days", t.days, "number") + "</div>" +
      '<div class="grid2">' + field("Цена в звёздах", "stars", t.stars || 0, "number") + field("Метка", "badge", t.badge || "") + "</div>" +
      (t.id === "mentor" ? field("Мест в неделю", "weekly_seats", t.weekly_seats || 0, "number") : "") +
      '<div class="grid2">' + field("Ссылка на товар в Tribute", "tribute_link", t.tribute_link || "") + field("ID товара или подписки в Tribute", "tribute_id", t.tribute_id || 0, "number") + "</div>" +
      '<label class="field"><span>Что входит — по строке на пункт</span><textarea class="input" data-f="features">' + esc((t.features || []).join("\n")) + "</textarea></label>" +
      field("Примечание под тарифом", "note", t.note || "") +
      '<label class="check"><span>' + (t.id === "mentor" ? "Открыт (иначе «Скоро» с замком)" : "Продаётся") + '</span><input type="checkbox" data-f="active"' + (t.active ? " checked" : "") + "></label>" +
      "</div>";
  }).join("") + '<button class="btn main" data-act="save-tariffs">Сохранить тарифы</button>';
}
function field(label, key, value, type) {
  return '<label class="field"><span>' + label + '</span><input class="input" data-f="' + key + '" type="' + (type || "text") + '" value="' + esc(value) + '"></label>';
}

var KINDS = [["lesson", "Уроки"], ["marathon", "Марафон"], ["material", "Материалы"], ["prompt", "Промпты"], ["agent", "AI-офис"], ["resource", "Ресурсы"], ["review", "Отзывы"]];
function adminContent() {
  var key = "content_" + S.admin.kind;
  var d = loading(key, "/api/admin/content?kind=" + S.admin.kind, function (x) { return x.items; });
  return '<div class="chips" style="margin-top:0">' + KINDS.map(function (k) { return '<button class="chip' + (S.admin.kind === k[0] ? " on" : "") + '" data-ckind="' + k[0] + '">' + k[1] + "</button>"; }).join("") + "</div>" +
    '<div class="cta-row"><button class="btn main" data-cedit="new">' + ic("plus") + (S.admin.kind === "review" ? "Добавить отзыв" : "Добавить") + "</button></div><div style=\"height:12px\"></div>" +
    (d === null || d === false ? SKEL : d.length ? '<div class="rows">' + d.map(function (c) {
      return '<button class="row" data-cedit="' + c.id + '"><span class="ava">' + ic(c.icon || "doc") + '</span><span class="row-text"><b>' + esc(c.title) + "</b><span>" +
        (c.module ? esc(c.module) + " · " : "") + (c.free ? "бесплатно" : "закрыто") + (c.published ? "" : " · скрыто") + " · №" + c.position + '</span></span><span class="row-end">' + ic("pen") + "</span></button>";
    }).join("") + "</div>" : empty("box", "Пока пусто."));
}
function renderMedia() {
  var box = $("#cmedia");
  if (!box) return;
  box.innerHTML = (S.cmedia || []).map(function (m, i) {
    return '<div class="thumb"><img src="' + esc(m) + '" alt=""><button type="button" data-act="cmedia-del" data-i="' + i + '" aria-label="Убрать">' + ic("close") + "</button></div>";
  }).join("");
}
function contentSheet(id) {
  var list = S.admin["content_" + S.admin.kind] || [];
  var c = id === "new" ? { kind: S.admin.kind, title: "", subtitle: "", module: "", body: "", icon: "", free: S.admin.kind === "review" || S.admin.kind === "marathon", position: (list.length + 1) * 10, published: true, minutes: 0 } :
    list.filter(function (x) { return String(x.id) === String(id); })[0];
  if (!c) return;
  var review = c.kind === "review";
  sheet('<h2>' + (id === "new" ? "Новый материал" : "Редактировать") + "</h2>" +
    '<div data-cform="' + (id === "new" ? "" : c.id) + '" data-kind="' + c.kind + '">' +
    field(review ? "Имя" : "Заголовок", "title", c.title) +
    field(review ? "Кто он (ниша, город)" : "Подзаголовок", "subtitle", c.subtitle) +
    (c.kind === "lesson" ? field("Модуль", "module", c.module) : "") +
    '<label class="field"><span>' + (review ? "Текст отзыва" : "Текст: ## подзаголовок, - список, **жирный**, `код`, > совет") + '</span><textarea class="input" data-f="body" style="min-height:240px">' + esc(c.body) + "</textarea></label>" +
    (review ? "" : '<div class="field"><span>Картинки — скриншоты сайтов, до 6 (показываются в ленте каруселью)</span><div class="thumbs" id="cmedia"></div>' +
      '<input type="file" id="cfile" accept="image/jpeg,image/png,image/webp" hidden><button class="btn" type="button" data-act="cmedia-add" style="margin-top:8px">' + ic("gallery_add") + "Добавить картинку</button></div>") +
    '<div class="grid2">' + field("Порядок", "position", c.position, "number") + (review ? "" : field("Минут", "minutes", c.minutes || 0, "number")) + "</div>" +
    (review ? "" : field("Иконка (code, rocket, bot, wallet, chat, palette…)", "icon", c.icon)) +
    (review || c.kind === "marathon" ? "" : '<label class="check"><span>Бесплатно для всех</span><input type="checkbox" data-f="free"' + (c.free ? " checked" : "") + "></label>") +
    '<label class="check"><span>Опубликовано</span><input type="checkbox" data-f="published"' + (c.published ? " checked" : "") + "></label>" +
    '<button class="btn main" data-act="save-content">Сохранить</button>' +
    (id !== "new" && !review ? '<button class="btn" data-cnotify="' + c.id + '">Разослать уведомление</button>' : "") +
    (id !== "new" ? '<button class="btn line" data-cdelete="' + c.id + '">Удалить</button>' : "") +
    "</div>");
  S.cmedia = (c.media || []).slice();
  renderMedia();
}

function adminBroadcast() {
  return '<div class="card"><p class="muted small" style="margin-top:0">Можно &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt; и ссылки &lt;a href="https://…"&gt;текст&lt;/a&gt;.</p>' +
    '<label class="field"><span>Текст</span><textarea class="input" id="bc-text" style="min-height:160px">' + esc(S.bcText || "") + "</textarea></label>" +
    '<input type="file" id="bc-file" accept="image/*" hidden>' +
    '<div class="btns"><button class="btn" data-act="bc-image">' + ic("gallery_add") + (S.bcImage ? "Картинка выбрана" : "Добавить картинку") + "</button>" + (S.bcImage ? '<button class="btn line" data-act="bc-noimage">Убрать</button>' : "") + "</div>" +
    '<label class="field"><span>Кому</span><select class="input" id="bc-aud"><option value="all">Всем, кто запускал бота</option><option value="residents">Резидентам</option><option value="guests">Гостям (без доступа)</option><option value="notify">С включёнными уведомлениями</option></select></label>' +
    '<label class="check"><span>Кнопка «Открыть C&amp;C» под сообщением</span><input type="checkbox" id="bc-btn" checked></label>' +
    '<button class="btn main" data-act="bc-send">Отправить</button></div>';
}

function adminTexts() {
  var d = loading("texts", "/api/admin/texts", function (x) { return x.texts; });
  if (!d) return SKEL;
  return d.map(function (t) {
    return '<div class="card" data-text="' + t.key + '"><h3>' + esc(t.title) + (t.changed ? ' <span class="status">изменён</span>' : "") + "</h3>" +
      (t.hint ? '<p class="muted small">' + esc(t.hint) + "</p>" : "") +
      '<textarea class="input" style="min-height:140px">' + esc(t.text) + "</textarea>" +
      '<div class="btns"><button class="btn" data-tsave="' + t.key + '">Сохранить</button><button class="btn line" data-ttest="' + t.key + '">Прислать мне</button>' +
      (t.changed ? '<button class="btn line" data-treset="' + t.key + '">Вернуть как было</button>' : "") + "</div></div>";
  }).join("");
}

function adminSettings() {
  var d = loading("settings", "/api/admin/settings");
  if (!d) return SKEL;
  return '<div class="card"><h3>Число участников</h3><p class="muted small">0 — считать автоматически: участники закрытой группы, а без группы — резиденты. Любое другое число покажется на главной как есть.</p>' +
    field("Показывать участников", "members_manual", d.members_manual, "number") +
    '<button class="btn main" data-act="save-settings" style="margin-top:12px">Сохранить</button></div>' +
    '<div class="card"><h3>Подключения</h3>' +
      '<div class="kv"><span>Адрес приложения</span><b>' + esc(d.public_url || "не задан") + "</b></div>" +
      '<div class="kv"><span>Бот</span><b>@' + esc(d.bot) + "</b></div>" +
      '<div class="kv"><span>ID группы</span><b>' + esc(d.group_id || "не задан") + "</b></div>" +
      '<div class="kv"><span>Поддержка</span><b>@' + esc(d.support) + "</b></div>" +
      '<div class="kv"><span>Оплата</span><b>' + (d.methods.length ? d.methods.join(", ") : "не подключена") + "</b></div>" +
      '<p class="muted small" style="margin:10px 0 0">Эти значения задаются в переменных Railway: GROUP_ID, SUPPORT_USERNAME, PAYMENT_PROVIDER_TOKEN, CRYPTO_PAY_TOKEN.</p>' +
    "</div>";
}

// ---------- Лист снизу ----------

function sheet(html) {
  $("#sheet").innerHTML = '<div class="grip"></div>' + html;
  $("#sheet").classList.add("show");
  $("#sheet-bg").classList.add("show");
  document.body.style.overflow = "hidden";
}
function closeSheet() {
  $("#sheet").classList.remove("show");
  $("#sheet-bg").classList.remove("show");
  document.body.style.overflow = "";
}

// ---------- Отрисовка ----------

function render() {
  if (!S.boot) return;
  var r = route();
  var html;
  switch (r.name) {
    case "": html = viewHome(); break;
    case "categories": html = viewCategories(); break;
    case "course": html = viewSection("lesson"); break;
    case "list": html = viewSection(r.arg); break;
    case "item": html = viewItem(r.arg); break;
    case "marathon": html = viewMarathon(); break;
    case "eval": html = viewEval(); break;
    case "community": html = viewCommunity(false); break;
    case "join": html = viewCommunity(true); break;
    case "profile": html = viewProfile(); break;
    case "admin": html = viewAdmin(r.arg); break;
    default: html = viewNotFound();
  }
  $("#app").innerHTML = html;
  renderNav();
  updateBack();
  if (r.name === "") bindSlides();
  bindGalleries();
  var bird = document.querySelectorAll("[data-bird]");
  bird.forEach(function (b) { b.innerHTML = BIRD; });
}

function showError(e) {
  if (e && e.status === 401) {
    $("#app").innerHTML = '<section class="view">' + empty("lock", "Открой приложение через бота в Telegram. Если окно было открыто долго — закрой и открой снова.") + "</section>";
    return;
  }
  toast(e && e.message ? e.message : "Что-то пошло не так");
}

// ---------- Действия ----------

function reloadBoot() {
  return api("/api/bootstrap").then(function (d) {
    S.boot = d; S.cache = {};
    try { sessionStorage.setItem("cc_boot", JSON.stringify(d)); } catch (e) {}
    render();
  });
}

function toggleDone(id) {
  var item = S.cache["item:" + id];
  var done = !(item && item.done);
  api("/api/content/" + id + "/done", { method: "POST", body: { done: done } }).then(function (r) {
    if (item) item.done = done;
    S.boot.lessons.forEach(function (l) { if (String(l.id) === String(id)) l.done = done; });
    if (r.marathon) S.boot.marathon = r.marathon;
    Object.keys(S.cache).forEach(function (k) { if (k.indexOf("list:") === 0) (S.cache[k] || []).forEach(function (l) { if (String(l.id) === String(id)) l.done = done; }); });
    haptic(done ? "ok" : "");
    if (done && item && item.kind === "marathon") toast("День закрыт. Следующий откроется завтра");
    else if (done) toast("Отмечено");
    render();
  }).catch(function (e) { toast(e.message); });
}

function share(id) {
  var item = S.cache["item:" + id];
  var url = "https://t.me/" + links().bot + "?startapp=item-" + id;
  var text = item ? item.title + " — в C&C Family" : "C&C Family";
  openLink("https://t.me/share/url?url=" + encodeURIComponent(url) + "&text=" + encodeURIComponent(text));
}

function checkAccess() {
  toast("Проверяю…");
  api("/api/access/check", { method: "POST" }).then(function (r) {
    toast(r.message);
    if (r.access.resident !== resident()) reloadBoot();
  }).catch(function (e) { toast(e.message); });
}

function readForm(root) {
  var out = {};
  root.querySelectorAll("[data-f]").forEach(function (el) {
    var k = el.getAttribute("data-f");
    out[k] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value || 0) : el.value;
  });
  return out;
}

document.addEventListener("click", function (ev) {
  var t = ev.target;
  var el;
  if ((el = t.closest("a[data-ext]"))) { ev.preventDefault(); openLink(el.href); return; }
  if ((el = t.closest("[data-copy]"))) { copyText(S.codeBlocks[+el.getAttribute("data-copy")] || ""); return; }
  if ((el = t.closest("[data-nav]"))) {
    var n = el.getAttribute("data-nav");
    haptic();
    if (n.charAt(0) === "@") openModule(n.slice(1)); else go(n);
    return;
  }
  if ((el = t.closest("[data-go]"))) { go(el.getAttribute("data-go")); return; }
  if ((el = t.closest("[data-item]"))) { if (el.getAttribute("data-item")) go("item/" + el.getAttribute("data-item")); return; }
  if ((el = t.closest("[data-tariff]"))) {
    var tid = el.getAttribute("data-tariff");
    var tt = S.boot.tariffs.filter(function (x) { return x.id === tid; })[0];
    if (tt && !tt.available) { toast(tt.active ? "Места на эту неделю закончились" : "Этот тариф скоро откроется"); return; }
    S.tariff = tid; haptic();
    document.querySelectorAll(".tariff").forEach(function (n) { n.classList.toggle("sel", n.getAttribute("data-tariff") === tid); });
    $("#paybox").innerHTML = payButtons();
    if ($("#compare")) $("#compare").innerHTML = compareTable(S.boot.tariffs);
    return;
  }
  if ((el = t.closest("[data-pay]"))) { pay(el.getAttribute("data-pay")); return; }
  if (t.closest("#sheet-bg")) { closeSheet(); return; }
  if ((el = t.closest("[data-user]"))) { userSheet(+el.getAttribute("data-user")); return; }
  if ((el = t.closest("[data-grant]"))) {
    var uid = +el.getAttribute("data-uid");
    el.disabled = true;
    api("/api/admin/users/" + uid + "/grant", { method: "POST", body: { days: +el.getAttribute("data-grant"), tariff: "base", notify: true } })
      .then(function () { toast("Доступ выдан, человеку пришло сообщение"); closeSheet(); S.admin.users = null; render(); })
      .catch(function (e) { el.disabled = false; toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-revoke]"))) {
    api("/api/admin/users/" + el.getAttribute("data-revoke") + "/revoke", { method: "POST" })
      .then(function () { toast("Доступ закрыт"); closeSheet(); S.admin.users = null; render(); }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-ban]"))) {
    api("/api/admin/users/" + el.getAttribute("data-ban") + "/ban", { method: "POST", body: { banned: el.getAttribute("data-v") === "1" } })
      .then(function () { toast("Готово"); closeSheet(); S.admin.users = null; render(); }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-chat]"))) { chatWith(el.getAttribute("data-chat")); return; }
  if ((el = t.closest("[data-ufilter]"))) { S.admin.filter = el.getAttribute("data-ufilter"); S.admin.users = null; render(); return; }
  if ((el = t.closest("[data-pfilter]"))) { S.admin.pstatus = el.getAttribute("data-pfilter"); S.admin.payments = null; render(); return; }
  if ((el = t.closest("[data-confirm]"))) {
    el.disabled = true;
    api("/api/admin/payments/" + el.getAttribute("data-confirm") + "/confirm", { method: "POST" })
      .then(function () { toast("Оплата подтверждена, доступ выдан"); S.admin.payments = null; render(); })
      .catch(function (e) { el.disabled = false; toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-ckind]"))) { S.admin.kind = el.getAttribute("data-ckind"); render(); return; }
  if ((el = t.closest("[data-cedit]"))) { contentSheet(el.getAttribute("data-cedit")); return; }
  if ((el = t.closest("[data-cnotify]"))) {
    api("/api/admin/content/" + el.getAttribute("data-cnotify") + "/notify", { method: "POST" }).then(function (r) { toast(r.message); }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-cdelete]"))) {
    if (el.getAttribute("data-sure") !== "1") { el.setAttribute("data-sure", "1"); el.textContent = "Точно удалить? Нажми ещё раз"; return; }
    api("/api/admin/content/" + el.getAttribute("data-cdelete"), { method: "DELETE" }).then(function () {
      toast("Удалено"); closeSheet(); S.admin["content_" + S.admin.kind] = null; refreshContent(); render();
    }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-tsave]")) || (el = t.closest("[data-treset]"))) {
    var key = el.getAttribute("data-tsave") || el.getAttribute("data-treset");
    var box = t.closest("[data-text]");
    var value = el.hasAttribute("data-treset") ? "" : box.querySelector("textarea").value;
    api("/api/admin/texts/" + key, { method: "PUT", body: { text: value } }).then(function () { toast("Сохранено"); S.admin.texts = null; render(); }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-ttest]"))) {
    api("/api/admin/texts/" + el.getAttribute("data-ttest") + "/test", { method: "POST" }).then(function (r) { toast(r.ok ? "Отправил в чат с ботом" : "Не смог написать: нажми /start в боте"); }).catch(function (e) { toast(e.message); });
    return;
  }
  if ((el = t.closest("[data-act]"))) action(el.getAttribute("data-act"), el);
});

document.addEventListener("keydown", function (ev) {
  if (ev.key === "Enter" && ev.target.id === "user-q") { S.admin.q = ev.target.value.trim(); S.admin.users = null; render(); }
});
document.addEventListener("change", function (ev) {
  if (ev.target.id === "files") { saveEvalFields(); addFiles(ev.target.files); ev.target.value = ""; }
  if (ev.target.id === "cfile") {
    var file = ev.target.files[0];
    ev.target.value = "";
    if (!file) return;
    var fd = new FormData(); fd.append("file", file, file.name);
    toast("Загружаю…");
    api("/api/admin/upload", { method: "POST", body: fd }).then(function (r) {
      S.cmedia = (S.cmedia || []).concat([r.url]); renderMedia(); toast("Картинка добавлена");
    }).catch(function (e) { toast(e.message); });
    return;
  }
  if (ev.target.id === "bc-file") {
    var f = ev.target.files[0];
    if (!f) return;
    if (f.size > 9 * 1024 * 1024) { toast("Картинка больше 9 МБ"); return; }
    S.bcText = ($("#bc-text") || {}).value || "";
    var r = new FileReader();
    r.onload = function () { S.bcImage = r.result; render(); };
    r.readAsDataURL(f);
  }
});

function refreshContent() {
  api("/api/bootstrap").then(function (d) { S.boot = d; S.cache = {}; }).catch(function () {});
}

function action(act, el) {
  switch (act) {
    case "done": toggleDone(el.getAttribute("data-id")); break;
    case "share": share(el.getAttribute("data-id")); break;
    case "support": chatWith(links().support); break;
    case "group": openLink(links().group); break;
    case "pay-support": chatWith(links().support, "Привет! Хочу оплатить C&C Family"); break;
    case "check-access": checkAccess(); break;
    case "to-tariffs": var el2 = $("#tariffs"); if (el2) el2.scrollIntoView({ behavior: "smooth" }); break;
    case "theme": setTheme(theme() === "dark" ? "light" : "dark", true); render(); break;
    case "notify":
      var v = !me().notify;
      S.boot.me.notify = v; render();
      api("/api/prefs", { method: "POST", body: { notify: v } }).then(function () { toast(v ? "Бот напишет о новых уроках" : "Уведомления выключены"); }).catch(function (e) { toast(e.message); });
      break;
    case "pick": saveEvalFields(); $("#files").click(); break;
    case "unfile":
      saveEvalFields();
      var i = +el.getAttribute("data-i");
      URL.revokeObjectURL(S.files[i].url); S.files.splice(i, 1); render();
      break;
    case "send-eval": sendEval(); break;
    case "save-tariffs":
      var forms = document.querySelectorAll("[data-tform]");
      var list = S.admin.tariffs.map(function (t, k) {
        var f = readForm(forms[k]);
        return Object.assign({}, t, f, { features: String(f.features || "").split("\n").map(function (s) { return s.trim(); }).filter(Boolean),
          weekly_seats: f.weekly_seats != null ? f.weekly_seats : (t.weekly_seats || 0) });
      });
      api("/api/admin/tariffs", { method: "PUT", body: list }).then(function (d) { S.admin.tariffs = d.tariffs; toast("Тарифы сохранены"); refreshContent(); render(); })
        .catch(function (e) { toast(e.message); });
      break;
    case "save-content":
      var root = el.closest("[data-cform]");
      var data = readForm(root);
      data.kind = root.getAttribute("data-kind");
      data.module = data.module || "";
      data.icon = data.icon || "";
      data.minutes = data.minutes || 0;
      if (data.kind === "review" || data.kind === "marathon") data.free = true;
      data.media = (S.cmedia || []).slice(0, 6);
      if (data.free === undefined) data.free = false;
      var id = root.getAttribute("data-cform");
      api("/api/admin/content" + (id ? "/" + id : ""), { method: id ? "PUT" : "POST", body: data }).then(function () {
        toast("Сохранено"); closeSheet(); S.admin["content_" + S.admin.kind] = null; refreshContent(); render();
      }).catch(function (e) { toast(e.message); });
      break;
    case "cmedia-add":
      if ((S.cmedia || []).length >= 6) { toast("Не больше 6 картинок"); return; }
      $("#cfile").click(); break;
    case "cmedia-del": S.cmedia.splice(+el.getAttribute("data-i"), 1); renderMedia(); break;
    case "bc-image": S.bcText = $("#bc-text").value; $("#bc-file").click(); break;
    case "bc-noimage": S.bcText = $("#bc-text").value; S.bcImage = ""; render(); break;
    case "bc-send":
      var text = $("#bc-text").value.trim();
      if (!text && !S.bcImage) { toast("Добавь текст или картинку"); return; }
      el.disabled = true;
      api("/api/admin/broadcast", { method: "POST", body: { text: text, image: S.bcImage || "", audience: $("#bc-aud").value, button: $("#bc-btn").checked } })
        .then(function (r) { S.bcText = ""; S.bcImage = ""; toast(r.message); render(); })
        .catch(function (e) { el.disabled = false; toast(e.message); });
      break;
    case "save-settings":
      var s = readForm(el.closest(".card"));
      api("/api/admin/settings", { method: "PUT", body: s }).then(function () { toast("Сохранено"); S.admin.settings = null; S.admin.overview = null; refreshContent(); }).catch(function (e) { toast(e.message); });
      break;
  }
}

// ---------- Листание мышью (ПК) ----------

(function () {
  var drag = null, lastDrag = 0;
  document.addEventListener("pointerdown", function (e) {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    var box = e.target.closest(".slides, .chips, .reviews, .atabs, .gal-track");
    if (!box || box.scrollWidth <= box.clientWidth + 2) return;
    drag = { box: box, x: e.clientX, left: box.scrollLeft, moved: false };
    S.userSlid = true;
  });
  document.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) > 5) {
      drag.moved = true;
      drag.box.classList.add("dragging");
    }
    if (drag.moved) { drag.box.scrollLeft = drag.left - dx; e.preventDefault(); }
  });
  function end() {
    if (!drag) return;
    var d = drag; drag = null;
    d.box.classList.remove("dragging");
    if (d.moved) {
      lastDrag = Date.now();
      if (d.box.classList.contains("gal-track")) {
        var w = d.box.clientWidth, j = Math.round(d.box.scrollLeft / w);
        d.box.scrollTo({ left: j * w, behavior: "smooth" });
      }
      if (d.box.classList.contains("slides")) {
        var first = d.box.firstElementChild, step = first ? first.offsetWidth + 10 : d.box.clientWidth;
        var i = Math.max(0, Math.min(d.box.children.length - 1, Math.round(d.box.scrollLeft / step)));
        d.box.scrollTo({ left: i * step, behavior: "smooth" });
      }
    }
  }
  document.addEventListener("pointerup", end);
  document.addEventListener("pointercancel", end);
  document.addEventListener("click", function (e) {
    if (Date.now() - lastDrag < 250) { e.stopPropagation(); e.preventDefault(); }
  }, true);
  document.addEventListener("dragstart", function (e) { if (e.target.closest(".slides, .chips, .gal-track")) e.preventDefault(); });
})();

// ---------- Запуск ----------

function startParam() {
  var p = "";
  try { p = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || ""; } catch (e) {}
  if (!p) { var m = /[?&]startapp=([^&#]+)/.exec(location.search); if (m) p = decodeURIComponent(m[1]); }
  return p;
}

function boot() {
  if (tg) {
    try {
      tg.ready(); tg.expand();
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
      tg.BackButton.onClick(goBack);
    } catch (e) {}
  }
  // Telegram открывает приложение с #tgWebAppData=… в адресе — убираем, это не страница.
  if (/tgWebApp|=/.test(location.hash)) {
    try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { location.hash = ""; }
  }
  var saved = null;
  try { saved = localStorage.getItem("cc_theme"); } catch (e) {}
  setTheme(saved || (tg && tg.colorScheme === "light" ? "light" : document.documentElement.dataset.theme || "dark"), false);

  // Возврат из парсера/скриптов — показываем сразу, данные обновляем в фоне.
  var cached = null;
  try { cached = JSON.parse(sessionStorage.getItem("cc_boot") || "null"); } catch (e) {}
  var param = startParam(), handled = false;
  try { handled = sessionStorage.getItem("cc_param") === param; sessionStorage.setItem("cc_param", param); } catch (e) {}
  if (param && !handled && !location.hash) {
    if (param === "join") location.hash = "join";
    else if (/^item-\d+$/.test(param)) location.hash = "item/" + param.slice(5);
    else if (/^(eval|marathon|course|profile|categories)$/.test(param)) location.hash = param;
  }
  try {
    var ret = sessionStorage.getItem("cc_return");
    if (ret && !location.hash) { location.hash = ret.replace(/^#/, ""); }
    sessionStorage.removeItem("cc_return");
  } catch (e) {}

  var splash = $("#splash");
  var started = Date.now();
  var hide = function () {
    var wait = cached ? 0 : Math.max(0, 650 - (Date.now() - started));
    setTimeout(function () { splash.classList.add("out"); }, wait);
  };
  if (cached) { S.boot = cached; render(); hide(); }
  api("/api/bootstrap").then(function (d) {
    S.boot = d;
    try { sessionStorage.setItem("cc_boot", JSON.stringify(d)); } catch (e) {}
    if (d.me.theme && !saved) setTheme(d.me.theme, false);
    render();
    hide();
  }).catch(function (e) {
    hide();
    var banned = e.detail && e.detail.code === "banned";
    $("#app").innerHTML = '<section class="view">' + empty(banned ? "lock" : "info",
      banned ? e.message : e.status === 401 ? "Открой приложение через бота в Telegram. Если окно было открыто долго — закрой и открой снова." : e.message,
      banned ? '<button class="btn" data-act="support">Написать в поддержку</button>' : '<button class="btn main" onclick="location.reload()">Обновить</button>') + "</section>";
    $("#nav").innerHTML = "";
  });
}

window.addEventListener("pageshow", function (e) { if (e.persisted) reloadBoot().catch(function () {}); });
document.querySelectorAll("[data-bird]").forEach(function (b) { b.innerHTML = BIRD; });
boot();
})();
