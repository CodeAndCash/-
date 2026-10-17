/* Весь код внутри своей области: Telegram на iPhone добавляет на страницу свои
   глобальные переменные (например, head), и они затирали наши функции. */
(function () {
"use strict";
/* Evaluation C&C — мини-апп для админов: заявки, оценка, переписка, люди, тексты бота, рассылка. */

var tg = window.Telegram && window.Telegram.WebApp || null;
/* Данные входа Telegram кладёт в адрес (#tgWebAppData=…). Берём их и оттуда —
   на случай, если скрипт telegram.org не загрузился (бывает с мобильным интернетом). */
var HASH_DATA = (function () {
  var h = String(window.TG_HASH || location.hash || "").replace(/^#/, "").split("&");
  for (var i = 0; i < h.length; i++) {
    if (h[i].indexOf("tgWebAppData=") === 0) { try { return decodeURIComponent(h[i].slice(13)); } catch (_) { return ""; } }
  }
  return "";
})();
function initData() { return (tg && tg.initData) || HASH_DATA; }
var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

var S = {
  tab: "reviews", me: null, error: null,
  status: "open", q: "", reviews: [], counts: {},
  detail: null, review: null, forms: {}, rejecting: false, busy: false,
  users: [], uq: "",
  texts: null, textKey: null, textImg: null, textImgState: "keep",
  segments: null, segment: "all", bcImages: [], bcConfirm: false, bcHtml: "",
  stats: null
};
var MEDIA = {};
var VER = "10";
var STATUS = { "new": "Новая", work: "В работе", done: "Оценено", rejected: "Отклонена" };
var FILTERS = [["open", "Открытые"], ["new", "Новые"], ["work", "В работе"], ["done", "Готовые"], ["rejected", "Отклонённые"], ["all", "Все"]];
var TABS = [["stats", "chart", "Статистика"], ["reviews", "gallery", "Заявки"], ["users", "users", "Люди"], ["texts", "chat", "Сообщения"], ["broadcast", "send", "Рассылка"]];
var SEGMENTS = [["all", "Все"], ["sent", "Отправляли сайт"], ["not_sent", "Не отправляли"], ["paid", "Оплачивали"]];

function ic(name, cls) {
  var body = (window.ICONS && ICONS[name]) || "";
  return '<svg class="ic ' + (cls || "") + '" viewBox="0 0 24 24" aria-hidden="true">' + body + "</svg>";
}
function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function num(v) {
  var n = Math.round(Number(v) * 10) / 10;
  return String(n).replace(".", ",");
}
function when(ts) {
  if (!ts) return "";
  var d = new Date(ts * 1000);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }).replace(".", "") + ", " +
    d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}
function plural(n, one, few, many) {
  var a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : (a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many);
}
function verdict(t) {
  return t >= 8.5 ? "Отличный сайт" : t >= 7 ? "Хороший сайт" : t >= 5 ? "Есть над чем поработать" : "Сайт стоит переделать";
}
function stripTags(html) {
  var d = document.createElement("div");
  d.innerHTML = String(html || "").replace(/<br\s*\/?>/g, " ");
  return (d.textContent || "").replace(/\s+/g, " ").trim();
}

var toastTimer;
function toast(text) {
  var t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { t.classList.remove("show"); }, 2600);
}

function api(path, options) {
  options = options || {};
  /* XMLHttpRequest, а не fetch: у него честный таймаут на весь ответ целиком,
     и он одинаково работает во всех версиях Telegram на телефонах. */
  return new Promise(function (resolve, reject) {
    var fail = function (msg, status) { var e = new Error(msg); if (status) e.status = status; reject(e); };
    try {
      var x = new XMLHttpRequest();
      x.open(options.method || "GET", "/eval" + path, true);
      x.timeout = options.raw ? 60000 : 15000;
      if (options.raw) x.responseType = "blob";
      // кириллица в имени ломает заголовок — шлём данные входа закодированными
      x.setRequestHeader("X-Init-Data", encodeURIComponent(initData()));
      if (options.body) x.setRequestHeader("Content-Type", "application/json");
      x.ontimeout = function () { fail("Сервер не отвечает. Проверьте интернет — попробуйте Wi‑Fi или VPN."); };
      x.onerror = function () { fail("Нет связи с сервером. Проверьте интернет."); };
      x.onabort = function () { fail("Запрос прерван. Попробуйте ещё раз."); };
      x.onload = function () {
        if (path === "/api/me" && window.PING) PING("вход: onload, длина ответа " + String(x.responseText || "").length);
        var ok = x.status >= 200 && x.status < 300;
        if (options.raw && ok) return resolve(x.response);
        var parse = function (text) { try { return JSON.parse(text || "{}") || {}; } catch (_) { return {}; } };
        if (options.raw) {
          // ошибка пришла как blob — читаем из него текст
          var fr = new FileReader();
          fr.onload = function () { var d = parse(fr.result); fail(typeof d.detail === "string" ? d.detail : "Ошибка " + x.status, x.status); };
          fr.onerror = function () { fail("Ошибка " + x.status, x.status); };
          try { fr.readAsText(x.response); } catch (_) { fail("Ошибка " + x.status, x.status); }
          return;
        }
        var data = parse(x.responseText);
        if (!ok) return fail(typeof data.detail === "string" ? data.detail : "Ошибка сервера: " + x.status, x.status);
        resolve(data);
      };
      if (path === "/api/me") {
        x.onreadystatechange = function () { if (window.PING) PING("вход: readyState " + x.readyState + " код " + x.status); };
        x.addEventListener("timeout", function () { if (window.PING) PING("вход: таймаут"); });
        x.addEventListener("error", function () { if (window.PING) PING("вход: ошибка сети"); });
      }
      x.send(options.body ? JSON.stringify(options.body) : null);
      if (path === "/api/me" && window.PING) PING("вход: запрос отправлен");
    } catch (e) {
      if (window.PING) PING("вход: исключение " + (e && e.message || e));
      fail("Не получилось отправить запрос: " + (e && e.message || e));
    }
  });
}

/* ---------- Загрузка ---------- */

function load(tab, silent) {
  tab = tab || S.tab;
  var btn = $("#refresh");
  if (btn) btn.classList.add("spin");
  var p;
  if (tab === "reviews") {
    p = Promise.all([
      api("/api/reviews?status=" + S.status + "&q=" + encodeURIComponent(S.q)),
      api("/api/overview")
    ]).then(function (r) { S.reviews = r[0].items; S.counts = r[1]; });
  } else if (tab === "review") {
    p = api("/api/reviews/" + S.detail).then(function (d) { S.review = d; });
  } else if (tab === "users") {
    p = api("/api/users?q=" + encodeURIComponent(S.uq)).then(function (d) { S.users = d.items; });
  } else if (tab === "preview") {
    p = api("/api/preview").then(function (d) { S.preview = d; });
    if (!S.cardUrl) api("/api/preview/card", { raw: true }).then(function (blob) { S.cardUrl = URL.createObjectURL(blob); var im = $("#pv-card"); if (im) { im.src = S.cardUrl; im.parentNode.classList.remove("wait"); } }).catch(function () {});
  } else if (tab === "texts" || tab === "text") {
    p = api("/api/texts").then(function (d) { S.texts = d; });
  } else if (tab === "broadcast") {
    p = api("/api/broadcast").then(function (d) { S.segments = d.segments; });
  } else {
    p = api("/api/stats").then(function (d) { S.stats = d; S.counts = d.overview; });
  }
  return p.then(function () { if (btn) btn.classList.remove("spin"); render(silent); })
    .catch(function (e) { if (btn) btn.classList.remove("spin"); toast(e.message); render(silent); });
}

/* ---------- Экраны ---------- */

function pageHead(title, small) {
  return '<div class="h"><h1>' + title + "</h1>" + (small ? "<small>" + small + "</small>" : "") + "</div>";
}

function vStats() {
  var st = S.stats;
  if (!st) return '<div class="dots"><i></i><i></i><i></i></div>';
  var o = st.overview;
  var tiles = [
    ["inbox", "Новые", o.new, true], ["hourglass", "В работе", o.work], ["check", "Оценено", o.done],
    ["star", "Средний балл", o.avg_total ? num(o.avg_total) : "—"], ["users", "Людей в боте", o.users],
    ["wallet", S.me.paid ? "Платных заявок" : "Доп. заявок", o.paid_reviews]
  ].concat(S.me.paid ? [["starline", "Звёзды", o.stars || 0], ["ticket", "Переводы, ₽", o.manual_rub || 0]] : []);
  var max = Math.max.apply(null, st.daily.map(function (d) { return Math.max(d.new, d.done); }).concat([1]));
  return pageHead("Статистика", "за всё время") +
    '<div class="grid2">' + tiles.map(function (t) {
      return '<div class="tile' + (t[3] ? " inv" : "") + '"><small>' + ic(t[0]) + t[1] + "</small><b>" + esc(t[2]) + "</b></div>";
    }).join("") + "</div>" +
    '<div class="card" style="margin-top:12px"><h3>Последние 14 дней</h3><div class="bars">' + st.daily.map(function (d) {
      var day = new Date(d.day * 1000).getDate();
      return '<div title="' + d.new + " / " + d.done + '"><i style="height:' + Math.round(d.new / max * 100) + '%"></i>' +
        '<i class="d" style="height:' + Math.round(d.done / max * 100) + '%"></i><span>' + day + "</span></div>";
    }).join("") + '</div><div class="legend"><span><i></i>Пришло</span><span><i class="d"></i>Оценено</span></div></div>';
}

function statusPill(r) {
  if (r.status === "done") return '<span class="pill">' + (r.total != null ? num(r.total) + " / 10" : "Оценено") + "</span>";
  if (r.status === "rejected") return '<span class="pill ghost">Отклонена</span>';
  if (r.status === "work") return '<span class="pill dark">В работе</span>';
  return '<span class="pill">Новая</span>';
}

function thumbs(r, limit, big) {
  var list = r.media.slice(0, limit);
  return list.map(function (m, i) {
    var more = i === limit - 1 && r.media.length > limit ? '<span class="more">+' + (r.media.length - limit + 1) + "</span>" : "";
    return '<div class="thumb" data-media="' + r.id + "/" + i + '" data-type="' + esc(m.type) + '" data-mime="' + esc(m.mime) + '"' +
      (big ? ' data-act="view" data-v="' + i + '" role="button" tabindex="0"' : "") + ">" +
      (m.type !== "photo" && !/^image\//.test(m.mime) ? '<span class="play">' + ic("play") + "</span>" : "") + more + "</div>";
  }).join("");
}

function reviewCard(r) {
  var who = r.user.charAt(0) === "@" ? '<span>' + esc(r.user) + "</span>" : esc(r.user);
  return '<button class="card tap" data-act="open" data-v="' + r.id + '"><div class="row top"><div class="grow">' +
    '<div class="name">#' + r.id + " " + who + "</div>" +
    '<div class="meta">' + (r.kind === "free" ? "Бесплатная" : "Платная") + " · " + when(r.created_at) +
    (r.admin_name && r.status !== "new" ? " · " + esc(r.admin_name) : "") + (r.msg_count ? " · " + r.msg_count + " сообщ." : "") + "</div>" +
    (r.url ? '<div class="meta">' + esc(r.url.replace(/^https?:\/\//, "").slice(0, 48)) + "</div>" : "") +
    "</div>" + statusPill(r) + '</div><div class="thumbs">' + thumbs(r, 3) + "</div></button>";
}

function vReviews() {
  var c = S.counts || {};
  var badge = { open: (c.new || 0) + (c.work || 0), "new": c.new, work: c.work, done: c.done };
  return pageHead("Заявки", "всего " + S.reviews.length) +
    '<div class="chips scroll">' + FILTERS.map(function (f) {
      var n = badge[f[0]];
      return '<button class="chip' + (S.status === f[0] ? " on" : "") + '" data-act="filter" data-v="' + f[0] + '">' + f[1] +
        (n ? "<b>" + n + "</b>" : "") + "</button>";
    }).join("") + "</div>" +
    '<div class="search">' + ic("search") + '<input class="field" id="rq" placeholder="Поиск: @username, сайт или номер" value="' + esc(S.q) + '"></div>' +
    (S.reviews.length ? S.reviews.map(reviewCard).join("") :
      '<div class="empty">' + ic("inbox") + "<p>" + (S.status === "open" ? "Новых заявок нет — всё оценено" : "Здесь пока пусто") + "</p></div>");
}

function form(id) {
  if (!S.forms[id]) {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem("ev-form-" + id) || "null"); } catch (_) {}
    S.forms[id] = saved || { scores: {}, html: "", useScores: false };
    if (!S.forms[id].scores) S.forms[id].scores = {};
  }
  return S.forms[id];
}
function saveForm(id) {
  try { localStorage.setItem("ev-form-" + id, JSON.stringify(S.forms[id])); } catch (_) {}
}
function totalOf(f) {
  var keys = (S.me ? S.me.criteria : []).map(function (c) { return c.key; });
  var vals = keys.map(function (k) { return f.scores[k]; }).filter(function (v) { return v != null; });
  return { done: vals.length === keys.length && keys.length > 0, value: vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : 0, n: vals.length };
}

var HEADINGS = ["Дизайн", "Удобство", "Мобильная версия", "Тексты", "Доверие и продажи", "Что сделать первым"];

function scoresBlock(f) {
  var t = totalOf(f);
  return '<div class="card scores">' + S.me.criteria.map(function (c) {
      var v = f.scores[c.key];
      var whole = v == null ? 0 : Math.floor(v);
      return '<div class="crit"><div class="row"><b>' + esc(c.title) + '</b><span class="val' + (v == null ? " unset" : "") + '">' +
        (v == null ? "—" : num(v)) + '</span></div><div class="scale">' +
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(function (n) {
          return '<button data-act="score" data-k="' + c.key + '" data-v="' + n + '" class="' + (n === whole ? "on" : n < whole ? "in" : "") + '">' + n + "</button>";
        }).join("") + "</div>" +
        (v != null && whole < 10 ? '<div class="half"><button data-act="half" data-k="' + c.key + '" class="' + (v % 1 ? "on" : "") + '">' + whole + ",5</button></div>" : "") +
        "</div>";
    }).join("") + "</div>" +
    '<div class="total"><b>' + (t.n ? num(t.value) : "—") + "</b><div><small>" + (t.done ? verdict(t.value) : "Поставь баллы всем 5 пунктам") +
    "</small><span>" + (t.done ? "человек получит ещё и картинку-оценку" : t.n + " из 5") + "</span></div></div>" +
    '<div class="btns"><button class="btn wide" data-act="scoresoff">' + ic("close") + "Убрать баллы</button></div>";
}

function rateForm(r) {
  var f = form(r.id);
  return '<div class="label">Оценка</div>' +
    '<div class="rte">' + toolbar() +
    '<div class="rte-ed" id="ed" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Текст оценки" data-ph="Просто напиши, что думаешь о сайте: что хорошо, что мешает, что исправить первым."></div>' +
    '<div class="rte-foot"><span>Человек получит этот текст в боте</span><span id="cnt">0 / 3300</span></div></div>' +
    '<div class="vars heads"><span>Заголовок:</span>' + HEADINGS.map(function (h) {
      return '<button type="button" data-ins="' + esc(h) + '">' + esc(h) + "</button>";
    }).join("") + "</div>" +
    (f.useScores ? '<div class="label">Баллы</div>' + scoresBlock(f)
      : '<div class="btns"><button class="btn wide" data-act="scoreson">' + ic("star") + "Поставить баллы — по желанию</button></div>") +
    '<div class="btns"><button class="btn main wide" data-act="rate"' + (S.busy ? " disabled" : "") + ">" + ic("send") + "Отправить оценку</button></div>" +
    (S.rejecting
      ? '<div class="confirm"><label class="fl" for="f-reason" style="margin-top:0">Причина (увидит человек)</label><textarea class="field" id="f-reason" placeholder="Например: на скриншотах не видно сайта, пришлите другие"></textarea>' +
        '<div class="btns"><button class="btn" data-act="rejcancel">Отмена</button><button class="btn danger" data-act="reject">Отклонить и вернуть оценку</button></div></div>'
      : '<div class="btns"><button class="btn danger wide" data-act="rejask">' + ic("close") + "Отклонить заявку</button></div>");
}

function vReview() {
  var r = S.review;
  if (!r || r.id !== S.detail) return '<button class="back" data-act="back">' + ic("back") + 'Заявки</button><div class="dots"><i></i><i></i><i></i></div>';
  var open = r.status === "new" || r.status === "work";
  var mine = S.me && r.admin_id === S.me.id;
  var who = r.user;
  return '<button class="back" data-act="back">' + ic("back") + "Заявки</button>" +
    '<div class="h"><h1>Заявка #' + r.id + "</h1>" + statusPill(r) + "</div>" +
    '<div class="card"><div class="kv">' +
      "<div>" + ic("user") + '<div class="grow"><b>' + esc(who) + '</b><div class="meta">ID ' + r.user_id + " · " + (r.kind === "free" ? "бесплатная" : S.me.paid ? "платная" : "дополнительная") + " · " + when(r.created_at) + "</div></div></div>" +
      (r.url ? "<div>" + ic("link") + '<a href="' + esc(/^https?:/.test(r.url) ? r.url : "https://" + r.url) + '" target="_blank" rel="noopener" data-ext>' + esc(r.url) + "</a></div>" : "") +
      (r.admin_name ? "<div>" + ic("shield") + "<span>" + (r.status === "done" ? "Оценил " : r.status === "rejected" ? "Отклонил " : "Смотрит ") + esc(r.admin_name) + "</span></div>" : "") +
    "</div>" + (r.comment ? '<div class="comment">' + esc(r.comment) + "</div>" : "") +
    (r.status === "new" ? '<div class="btns"><button class="btn main wide" data-act="take">' + ic("case") + "Взять в работу</button></div>" : "") + "</div>" +
    '<div class="label">Скриншоты и видео · ' + r.media.length + '</div><div class="gallery">' + thumbs(r, r.media.length, true) + "</div>" +
    '<div class="btns" style="margin-top:8px"><button class="btn wide" data-act="forward">' + ic("send") + "Прислать файлы мне в чат</button></div>" +
    (r.status === "done" ? '<div class="label">Что получил человек</div>' +
      (r.total != null ? '<div class="total"><b>' + num(r.total) + "</b><div><small>" + verdict(r.total) + "</small><span>" + esc(r.admin_name) + " · " + when(r.done_at) + "</span></div></div>"
        : '<p class="meta" style="margin:0 2px 10px">' + esc(r.admin_name) + " · " + when(r.done_at) + "</p>") +
      '<div class="preview">' + r.preview + "</div>" : "") +
    (r.status === "rejected" ? '<div class="label">Причина отказа</div><div class="preview">' + esc(r.reason || "без причины") + "</div>" : "") +
    (open ? (mine || r.status === "new" || !r.admin_id ? rateForm(r) : '<div class="label">Оценка</div><div class="card"><p class="meta">Заявку оценивает ' + esc(r.admin_name) + ". Можно переписываться с человеком ниже.</p></div>" + rateForm(r)) : "") +
    '<div class="label">Переписка</div>' +
    (r.messages.length ? '<div class="chat">' + r.messages.map(function (m) {
      return '<div class="msg ' + (m.from_admin ? "me" : "them") + '">' + esc(m.text) + "<small>" + (m.from_admin ? "команда" : esc(who)) + " · " + when(m.created_at) + "</small></div>";
    }).join("") + "</div>" : '<p class="meta" style="margin:0 2px 10px">Сообщений пока нет. Человек получит ваше сообщение в боте и сможет ответить.</p>') +
    '<div class="send"><textarea class="field" id="msg" placeholder="Написать человеку…"></textarea><button class="btn main" data-act="msg" aria-label="Отправить">' + ic("send") + "</button></div>";
}

function vUsers() {
  return pageHead("Люди", "кто запускал бота") +
    '<div class="search">' + ic("search") + '<input class="field" id="uq" placeholder="@username, имя или ID" value="' + esc(S.uq) + '"></div>' +
    (S.users.length ? S.users.map(function (u) {
      return '<div class="card"><div class="row"><div class="grow"><div class="name">' + esc(u.name) + (u.first_name && u.name.charAt(0) === "@" ? " <span>" + esc(u.first_name) + "</span>" : "") + "</div>" +
        '<div class="meta">ID ' + u.id + " · с " + when(u.created_at).split(",")[0] + "</div></div>" +
        (u.admin ? '<span class="pill">Админ</span>' : u.banned ? '<span class="pill ghost">Бан</span>' : "") + "</div>" +
        '<div class="counts"><span>Бесплатных <b>' + u.free_left + "</b></span><span>" + (S.me.paid ? "Оплачено" : "Доп.") + " <b>" + u.credits + "</b></span><span>Заявок <b>" + u.reviews + "</b></span></div>" +
        (u.admin ? "" : '<div class="urow"><button data-act="cred" data-id="' + u.id + '" data-v="1">' + ic("plus") + "Оценка</button>" +
          '<button data-act="cred" data-id="' + u.id + '" data-v="-1"' + (u.credits ? "" : " disabled") + ">" + ic("minus") + "Списать</button>" +
          '<button class="danger" data-act="ban" data-id="' + u.id + '" data-v="' + (u.banned ? 0 : 1) + '">' + ic(u.banned ? "refresh" : "danger") + (u.banned ? "Разбан" : "Бан") + "</button></div>") +
        "</div>";
    }).join("") : '<div class="empty">' + ic("users") + "<p>Никого не найдено</p></div>");
}

function vTexts() {
  var t = S.texts;
  if (!t) return '<div class="dots"><i></i><i></i><i></i></div>';
  return pageHead("Сообщения", "что бот пишет людям") +
    '<button class="card tap pvcard" data-act="preview"><span class="pvic">' + ic("eye") + '</span><span class="grow"><b>Как видит участник</b><small>Вся переписка с ботом — от /start до оценки</small></span>' + ic("back", "fwd") + "</button>" +
    '<p class="lead">Выбери сообщение: можно поменять текст (жирный, курсив, ссылки) и картинку. Изменения сразу работают в боте, ничего обновлять не нужно.</p>' +
    t.groups.map(function (g) {
      return '<div class="label">' + esc(g) + "</div>" + t.items.filter(function (i) { return i.group === g; }).map(function (i) {
        return '<button class="card tap tcard" data-act="text" data-v="' + i.key + '"><div class="row"><h3 class="grow">' + esc(i.title) + "</h3>" +
          (i.changed ? '<span class="mark">' + (i.has_image ? ic("camera") : "") + "изменено</span>" : "") + "</div><p>" + esc(stripTags(i.text)) + "</p></button>";
      }).join("");
    }).join("");
}

function toolbar() {
  return '<div class="rte-bar" role="toolbar" aria-label="Оформление">' +
    '<button type="button" data-fmt="bold" aria-label="Жирный"><b>Ж</b></button>' +
    '<button type="button" data-fmt="italic" aria-label="Курсив"><i>К</i></button>' +
    '<button type="button" data-fmt="underline" aria-label="Подчёркнутый"><u>Ч</u></button>' +
    '<button type="button" data-fmt="strikeThrough" aria-label="Зачёркнутый"><s>З</s></button>' +
    '<button type="button" data-fmt="link" aria-label="Ссылка">' + ic("link") + "</button>" +
    '<button type="button" data-fmt="quote" aria-label="Цитата">❝</button>' +
    '<button type="button" data-fmt="code" aria-label="Моноширинный">&lt;/&gt;</button>' +
    '<button type="button" data-fmt="spoiler" aria-label="Скрытый текст">' + ic("eye") + "</button></div>";
}

function vText() {
  var t = S.texts && S.texts.items.filter(function (i) { return i.key === S.textKey; })[0];
  if (!t) return '<button class="back" data-act="tback">' + ic("back") + 'Сообщения</button><div class="dots"><i></i><i></i><i></i></div>';
  var img = S.textImgState === "none" ? null : S.textImg;
  return '<button class="back" data-act="tback">' + ic("back") + "Сообщения</button>" + pageHead(esc(t.title), t.changed ? "изменено" : "стандартный текст") +
    '<div class="rte">' + toolbar() + '<div class="rte-ed" id="ed" contenteditable="true" role="textbox" aria-multiline="true" data-ph="Текст сообщения"></div>' +
    '<div class="rte-foot"><span>Выдели слово и нажми кнопку сверху</span><span id="cnt">0 / 4000</span></div></div>' +
    (t.vars.length ? '<div class="vars">' + t.vars.map(function (v) {
      return '<button data-act="var" data-v="' + v.key + '"><b>{' + v.key + "}</b> " + esc(v.title) + "</button>";
    }).join("") + "</div>" : "") +
    '<div class="card" style="margin-top:14px"><div class="addrow"><div><b>Картинка</b><br><small>сверху сообщения, по желанию</small></div>' +
    '<button class="btn" data-act="timg">' + ic("gallery") + (img ? "Заменить" : "Добавить") + "</button></div>" +
    (img ? '<div class="imgs"><div class="thumb"><img src="' + esc(img) + '" alt=""><button class="x" data-act="timgdel" aria-label="Убрать">' + ic("x") + "</button></div></div>" : "") +
    '<input type="file" id="timg-file" accept="image/png,image/jpeg,image/webp" hidden></div>' +
    '<div class="btns"><button class="btn main wide" data-act="tsave">' + ic("check") + "Сохранить</button></div>" +
    '<div class="btns"><button class="btn" data-act="ttest">' + ic("send") + "Прислать мне</button>" +
    (t.changed ? '<button class="btn" data-act="treset">' + ic("refresh") + "Вернуть стандартный</button>" : "") + "</div>";
}

function tgBubble(st) {
  var html = st.kind === "card"
    ? '<div class="tg-photo' + (S.cardUrl ? "" : " wait") + '"><img id="pv-card" alt="Картинка-оценка" src="' + (S.cardUrl || "") + '"></div>'
    : (st.image ? '<div class="tg-photo tg-img">' + ic("gallery") + "<span>картинка из «Сообщений»</span></div>" : "") +
      '<div class="tg-text">' + st.html.replace(/<\/blockquote>\n/g, "</blockquote>") + "</div>";
  return html;
}
function vPreview() {
  var d = S.preview;
  var top = '<button class="back" data-act="tback">' + ic("back") + "Сообщения</button>" + pageHead("Как видит участник", "пример переписки");
  if (!d) return top + '<div class="dots"><i></i><i></i><i></i></div>';
  return top + '<p class="lead">Так бот общается с человеком по шагам. Данные условные (Тимур, barber-kzn.ru), тексты — твои текущие. Нажми «Изменить», чтобы поправить сообщение.</p>' +
    '<div class="tg">' + d.steps.map(function (st) {
      if (st.who === "tap") return '<div class="tg-tap">' + ic("cursor") + "нажимает «" + esc(st.html) + "»</div>";
      if (st.who === "user") {
        return '<div class="tg-row me"><div class="tg-b me">' +
          (st.kind === "photos" ? '<div class="tg-ph">' + Array.apply(null, Array(st.count || 1)).map(function () { return "<i>" + ic("gallery") + "</i>"; }).join("") + "</div>" : "") +
          '<div class="tg-text">' + esc(st.html) + "</div></div></div>";
      }
      return (st.note ? '<div class="tg-note"><span>' + esc(st.note) + "</span>" + (st.key ? '<button data-act="pvedit" data-v="' + st.key + '">Изменить</button>' : "") + "</div>" : "") +
        '<div class="tg-row"><div class="tg-col"><div class="tg-b' + (st.kind === "card" ? " pic" : "") + '">' + tgBubble(st) + "</div>" +
        (st.buttons && st.buttons.length ? '<div class="tg-kb">' + st.buttons.map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("") + "</div>" : "") +
        "</div></div>";
    }).join("") + "</div>";
}

function vBroadcast() {
  var seg = S.segments || {};
  var n = seg[S.segment] || 0;
  return pageHead("Рассылка", "тем, кто запускал бота") +
    '<div class="chips">' + SEGMENTS.map(function (s) {
      return '<button class="chip' + (S.segment === s[0] ? " on" : "") + '" data-act="seg" data-v="' + s[0] + '">' + (s[0] === "paid" && !S.me.paid ? "С доп. оценками" : s[1]) + " · " + (seg[s[0]] || 0) + "</button>";
    }).join("") + "</div>" +
    '<div class="rte">' + toolbar() + '<div class="rte-ed" id="ed" contenteditable="true" role="textbox" aria-multiline="true" data-ph="Текст рассылки. Выдели слово и нажми кнопку сверху: жирный, курсив, ссылка…"></div>' +
    '<div class="rte-foot"><span></span><span id="cnt">0 / 4096</span></div></div>' +
    '<div class="card" style="margin-top:12px"><div class="addrow"><small>Фото (по желанию, до 10)</small><button class="btn" data-act="bimg"' + (S.bcImages.length >= 10 ? " disabled" : "") + ">Добавить фото</button></div>" +
    (S.bcImages.length ? '<div class="imgs">' + S.bcImages.map(function (src, i) {
      return '<div class="thumb"><img src="' + esc(src) + '" alt=""><button class="x" data-act="bimgdel" data-v="' + i + '" aria-label="Убрать">' + ic("x") + "</button></div>";
    }).join("") + "</div>" : "") +
    '<input type="file" id="bimg-file" accept="image/png,image/jpeg,image/webp" multiple hidden></div>' +
    (S.bcConfirm
      ? '<div class="confirm"><b>Отправить ' + n + " " + plural(n, "человеку", "людям", "людям") + "?</b>" +
        '<p class="meta">Отменить рассылку после запуска нельзя. Итог придёт в чат с ботом.</p>' +
        '<div class="btns"><button class="btn" data-act="bcno">Отмена</button><button class="btn main" data-act="bcgo">' + ic("send") + "Отправить</button></div></div>"
      : '<div class="btns"><button class="btn main wide" data-act="bcask"' + (n ? "" : " disabled") + ">" + ic("send") + "Отправить · " + n + "</button></div>");
}

function vDenied() {
  var e = S.error;
  var diag = "Код " + (e && e.status ? e.status : "—") + " · вход Telegram: " + (initData() ? "есть" : "нет") +
    " · " + (tg ? (tg.platform || "") + " " + (tg.version || "") : "скрипт Telegram не загрузился");
  return '<div class="empty">' + ic(e && e.status === 403 ? "shield" : "danger") + "<p><b>" +
    (e && e.status === 403 ? "Только для админов" : "Не удалось открыть") + "</b></p><p>" + esc(e ? e.message : "") + "</p>" +
    (e && e.status === 401 ? "<p>Закрой мини-апп и открой заново кнопкой «Админка» в чате с ботом.</p>" : "") +
    '<p class="meta" style="font-size:12px">' + esc(diag) + "</p>" +
    '<div class="btns" style="justify-content:center"><button class="btn" data-act="retry">' + ic("refresh") + "Повторить</button></div></div>";
}

/* ---------- Отрисовка ---------- */

function render(keepScroll) {
  var y = window.scrollY;
  var app = $("#app");
  var editing = S.tab === "text" || S.tab === "broadcast" || S.tab === "review";
  var edKey = S.tab === "text" ? "text:" + S.textKey : S.tab === "review" ? "review:" + S.detail : S.tab;
  // текст в поле сохраняем, только если перерисовываем тот же экран
  var edHtml = editing && $("#ed") && S.edFor === edKey ? $("#ed").innerHTML : null;
  S.edFor = editing ? edKey : null;
  if (!S.me) {
    app.innerHTML = S.error ? vDenied() : '<div class="dots"><i></i><i></i><i></i></div>';
    $("#tabs").innerHTML = "";
    return;
  }
  var views = { preview: vPreview, stats: vStats, reviews: vReviews, review: vReview, users: vUsers, texts: vTexts, text: vText, broadcast: vBroadcast };
  app.innerHTML = (views[S.tab] || vReviews)();
  var active = S.tab === "review" ? "reviews" : S.tab === "text" || S.tab === "preview" ? "texts" : S.tab;
  var newCount = (S.counts && S.counts.new) || 0;
  $("#tabs").innerHTML = TABS.map(function (t) {
    return '<button class="' + (active === t[0] ? "on" : "") + '" data-act="tab" data-v="' + t[0] + '">' + ic(t[1]) + "<span>" + t[2] + "</span>" +
      (t[0] === "reviews" && newCount ? "<em>" + newCount + "</em>" : "") + "</button>";
  }).join("");
  if (editing) setupEditor(edHtml);
  hydrateMedia();
  if (tg && tg.BackButton) {
    tg.BackButton.show(); // на главной вкладке «назад» ведёт в админку C&C Family
  }
  $$("textarea[data-note]").forEach(autoGrow);
  window.scrollTo(0, keepScroll ? y : 0);
}

/* Картинки и видео заявок грузим с заголовком авторизации и показываем через blob-ссылки. */
function hydrateMedia() {
  $$("[data-media]").forEach(function (el) {
    var key = el.dataset.media;
    var cached = MEDIA[key];
    if (cached && cached.url) return fill(el, cached);
    if (cached && cached.err) return fail(el, cached.err);
    if (cached && cached.loading) return;
    MEDIA[key] = { loading: true };
    var parts = key.split("/");
    api("/api/reviews/" + parts[0] + "/media/" + parts[1], { raw: true }).then(function (blob) {
      MEDIA[key] = { url: URL.createObjectURL(blob), video: /^video\//.test(blob.type) };
      $$('[data-media="' + key + '"]').forEach(function (n) { fill(n, MEDIA[key]); });
    }).catch(function (e) {
      MEDIA[key] = { err: e.status === 413 ? "Большое видео — пришлите в чат" : "Не загрузилось" };
      $$('[data-media="' + key + '"]').forEach(function (n) { fail(n, MEDIA[key].err); });
    });
  });
  function fill(el, m) {
    if (el.querySelector("img,video")) return;
    var node;
    if (m.video) { node = document.createElement("video"); node.muted = true; node.playsInline = true; node.preload = "metadata"; }
    else { node = document.createElement("img"); node.alt = ""; node.loading = "lazy"; }
    node.src = m.url;
    el.insertBefore(node, el.firstChild);
  }
  function fail(el, text) {
    if (el.classList.contains("err")) return;
    el.classList.add("err");
    if (el.closest(".gallery")) el.innerHTML = "<span>" + esc(text) + "</span>";
  }
}

function openViewer(index) {
  var r = S.review;
  var m = MEDIA[r.id + "/" + index];
  if (!m || !m.url) { toast(m && m.err ? m.err : "Файл ещё загружается"); return; }
  var v = document.createElement("div");
  v.className = "viewer";
  v.innerHTML = '<div class="vt"><span>' + (index + 1) + " из " + r.media.length + '</span><button aria-label="Закрыть">' + ic("x") + '</button></div><div class="vb">' +
    (m.video ? '<video src="' + m.url + '" controls autoplay playsinline></video>' : '<img src="' + m.url + '" alt="">') + "</div>";
  v.addEventListener("click", function (e) { if (e.target.closest("button") || e.target === v || e.target.classList.contains("vb")) v.remove(); });
  document.body.appendChild(v);
}

/* ---------- Редактор: HTML Telegram ⇄ поле ввода ---------- */

var ALLOWED = { B: "b", STRONG: "b", I: "i", EM: "i", U: "u", INS: "u", S: "s", STRIKE: "s", DEL: "s", CODE: "code", PRE: "code", BLOCKQUOTE: "blockquote", A: "a", "TG-SPOILER": "tg-spoiler" };

function telegramToEditor(html) {
  var doc = new DOMParser().parseFromString("<div>" + String(html || "") + "</div>", "text/html");
  function walk(node) {
    var out = "";
    node.childNodes.forEach(function (n) {
      if (n.nodeType === 3) { out += esc(n.nodeValue).replace(/\n/g, "<br>"); return; }
      if (n.nodeType !== 1) return;
      var tag = ALLOWED[n.tagName] || (n.tagName === "SPAN" && n.classList.contains("tg-spoiler") ? "tg-spoiler" : "");
      var inner = walk(n);
      if (tag === "a") {
        var href = n.getAttribute("href") || "";
        out += /^(https?|tg):\/\//.test(href) ? '<a href="' + esc(href) + '">' + inner + "</a>" : inner;
      } else if (tag === "tg-spoiler") out += '<span class="tg-spoiler">' + inner + "</span>";
      else if (tag) out += "<" + tag + ">" + inner + "</" + tag + ">";
      else out += inner;
    });
    return out;
  }
  return walk(doc.body.firstChild);
}

function editorToTelegram(node) {
  var out = "";
  node.childNodes.forEach(function (child) {
    if (child.nodeType === 3) { out += esc(child.nodeValue.replace(/ /g, " ")); return; }
    if (child.nodeType !== 1) return;
    var tag = child.tagName;
    if (tag === "BR") { out += "\n"; return; }
    var inner = editorToTelegram(child);
    var st = child.style || {};
    var deco = String(st.textDecorationLine || st.textDecoration || "");
    var weight = String(st.fontWeight || "");
    if (tag === "B" || tag === "STRONG" || weight === "bold" || Number(weight) >= 600) inner = "<b>" + inner + "</b>";
    if (tag === "I" || tag === "EM" || st.fontStyle === "italic") inner = "<i>" + inner + "</i>";
    if (tag === "U" || deco.indexOf("underline") >= 0) inner = "<u>" + inner + "</u>";
    if (tag === "S" || tag === "STRIKE" || tag === "DEL" || deco.indexOf("line-through") >= 0) inner = "<s>" + inner + "</s>";
    if (tag === "CODE") inner = "<code>" + inner + "</code>";
    if (tag === "SPAN" && child.classList.contains("tg-spoiler")) inner = "<tg-spoiler>" + inner + "</tg-spoiler>";
    if (tag === "A" && /^(https?|tg):\/\//.test(child.getAttribute("href") || "")) inner = '<a href="' + esc(child.getAttribute("href")) + '">' + inner + "</a>";
    if (tag === "BLOCKQUOTE") {
      if (out && !/\n$/.test(out)) out += "\n";
      out += "<blockquote>" + inner.replace(/\n+$/, "") + "</blockquote>\n";
      return;
    }
    if ((tag === "DIV" || tag === "P") && out && !/\n$/.test(out)) out += "\n";
    out += inner;
  });
  return out;
}

function edText() {
  var ed = $("#ed");
  return ed ? editorToTelegram(ed).replace(/\n{3,}/g, "\n\n").trim() : "";
}

function setupEditor(previousHtml) {
  var ed = $("#ed");
  if (!ed) return;
  if (previousHtml !== null && previousHtml !== undefined) ed.innerHTML = previousHtml;
  else if (S.tab === "text") {
    var t = S.texts.items.filter(function (i) { return i.key === S.textKey; })[0];
    ed.innerHTML = telegramToEditor(t ? t.text : "");
  } else if (S.tab === "review") ed.innerHTML = form(S.detail).html || "";
  else ed.innerHTML = S.bcHtml || "";
  count();
}

function count() {
  var ed = $("#ed"), c = $("#cnt");
  if (!ed || !c) return;
  var n = (ed.innerText || "").replace(/\n$/, "").length;
  var lim = S.tab === "broadcast" ? 4096 : S.tab === "review" ? 3300 : 4000;
  c.textContent = n + " / " + lim;
  c.style.color = n > lim ? "var(--bad)" : "";
  if (S.tab === "broadcast") S.bcHtml = ed.innerHTML;
  if (S.tab === "review" && S.detail) { form(S.detail).html = ed.innerHTML; saveForm(S.detail); }
}

var savedRange = null;
function wrapSelection(build) {
  var sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) { toast("Сначала выдели текст"); return; }
  var range = sel.getRangeAt(0);
  var el = build();
  el.appendChild(range.extractContents());
  range.insertNode(el);
  sel.removeAllRanges();
  var after = document.createRange();
  after.selectNodeContents(el);
  after.collapse(false);
  sel.addRange(after);
}

function applyFormat(kind) {
  var ed = $("#ed");
  if (!ed) return;
  if (document.activeElement !== ed) ed.focus();
  if (kind === "link") {
    var sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) { toast("Выдели слово, которое станет ссылкой"); return; }
    savedRange = sel.getRangeAt(0).cloneRange();
    var box = document.createElement("div");
    box.className = "confirm";
    box.id = "linkbox";
    box.innerHTML = '<input class="field" id="linkurl" placeholder="https://…" inputmode="url"><div class="btns"><button class="btn" data-act="linkno">Отмена</button><button class="btn main" data-act="linkok">Сделать ссылкой</button></div>';
    var old = $("#linkbox");
    if (old) old.remove();
    ed.parentNode.insertAdjacentElement("afterend", box);
    $("#linkurl").focus();
    return;
  }
  if (kind === "quote") wrapSelection(function () { return document.createElement("blockquote"); });
  else if (kind === "code") wrapSelection(function () { return document.createElement("code"); });
  else if (kind === "spoiler") wrapSelection(function () { var s = document.createElement("span"); s.className = "tg-spoiler"; return s; });
  else { try { document.execCommand(kind, false, null); } catch (_) {} }
  count();
}

function insertAtCursor(text) {
  var ed = $("#ed");
  if (!ed) return;
  ed.focus();
  try { document.execCommand("insertText", false, text); } catch (_) { ed.innerHTML += esc(text); }
  count();
}

function insertHeading(title) {
  var ed = $("#ed");
  if (!ed) return;
  ed.focus();
  var sel = window.getSelection();
  if (!sel.rangeCount || !ed.contains(sel.anchorNode)) {
    var r = document.createRange();
    r.selectNodeContents(ed);
    r.collapse(false);
    sel.removeAllRanges();
    sel.addRange(r);
  }
  var filled = (ed.innerText || "").replace(/\s+$/, "").length > 0;
  var range = sel.getRangeAt(0);
  range.deleteContents();
  function div(child) { var d = document.createElement("div"); d.appendChild(child); return d; }
  var b = document.createElement("b");
  b.textContent = title;
  var line = div(document.createElement("br"));
  var frag = document.createDocumentFragment();
  if (filled) frag.appendChild(div(document.createElement("br")));
  frag.appendChild(div(b));
  frag.appendChild(line);
  range.insertNode(frag);
  var caret = document.createRange();
  caret.setStart(line, 0);
  caret.collapse(true);
  sel.removeAllRanges();
  sel.addRange(caret);
  count();
}

/* Картинки уменьшаем в браузере: до 1600 px по длинной стороне, JPEG. */
function readImage(file) {
  return new Promise(function (resolve, reject) {
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { reject(new Error("Нужна картинка JPG, PNG или WEBP")); return; }
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var k = Math.min(1, 1600 / Math.max(img.width, img.height));
      var c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      var ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.88));
    };
    img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("Не получилось открыть картинку")); };
    img.src = url;
  });
}

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight + 2, 240) + "px";
}

/* ---------- Действия ---------- */

function go(tab) {
  S.tab = tab;
  S.bcConfirm = false;
  render();
  load(tab, true);
}

function openReview(id) {
  S.detail = Number(id);
  S.rejecting = false;
  S.tab = "review";
  render();
  load("review", true);
}

function openText(key) {
  S.textKey = key;
  S.textImg = null;
  S.textImgState = "keep";
  S.tab = "text";
  render();
  var t = S.texts.items.filter(function (i) { return i.key === key; })[0];
  if (t && t.has_image) {
    api("/api/texts/" + key + "/image", { raw: true }).then(function (blob) {
      var reader = new FileReader();
      reader.onload = function () { if (S.textKey === key && S.textImgState === "keep") { S.textImg = reader.result; render(true); } };
      reader.readAsDataURL(blob);
    }).catch(function () {});
  }
}

function busy(button, promise) {
  if (button) button.disabled = true;
  return promise.finally(function () { if (button) button.disabled = false; });
}

document.addEventListener("click", function (e) {
  var b = e.target.closest("[data-act]");
  if (!b) return;
  var a = b.dataset.act, v = b.dataset.v;
  if (a === "tab") go(v);
  else if (a === "retry") boot();
  else if (a === "filter") { S.status = v; render(true); load("reviews", true); }
  else if (a === "open") openReview(v);
  else if (a === "back") go("reviews");
  else if (a === "view") openViewer(Number(v));
  else if (a === "take") busy(b, api("/api/reviews/" + S.detail + "/take", { method: "POST" }).then(function () { toast("Заявка твоя — человек получил уведомление"); return load("review", true); }).catch(function (er) { toast(er.message); load("review", true); }));
  else if (a === "forward") busy(b, api("/api/reviews/" + S.detail + "/forward", { method: "POST" }).then(function (d) { toast(d.message); }).catch(function (er) { toast(er.message); }));
  else if (a === "score" || a === "half") {
    var f = form(S.detail);
    var key = b.dataset.k;
    if (a === "score") f.scores[key] = Number(v);
    else f.scores[key] = f.scores[key] % 1 ? Math.floor(f.scores[key]) : Math.floor(f.scores[key]) + 0.5;
    saveForm(S.detail);
    render(true);
  }
  else if (a === "scoreson") { form(S.detail).useScores = true; saveForm(S.detail); render(true); }
  else if (a === "scoresoff") { var fo = form(S.detail); fo.useScores = false; fo.scores = {}; saveForm(S.detail); render(true); }
  else if (a === "rate") {
    var fm = form(S.detail);
    var body = edText();
    var tt = totalOf(fm);
    if (stripTags(body).trim().length < 3) { toast("Напиши текст оценки"); var e1 = $("#ed"); if (e1) e1.focus(); return; }
    if (fm.useScores && !tt.done) { toast("Поставь баллы всем 5 пунктам или нажми «Убрать баллы»"); return; }
    S.busy = true;
    busy(b, api("/api/reviews/" + S.detail + "/rate", { method: "POST", body: { text: body, scores: fm.useScores ? fm.scores : {} } })
      .then(function (d) {
        toast(d.message);
        delete S.forms[S.detail];
        try { localStorage.removeItem("ev-form-" + S.detail); } catch (_) {}
        var e2 = $("#ed"); if (e2) e2.innerHTML = "";
        S.edFor = null;
        if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
        return load("review", true);
      }).catch(function (er) { toast(er.message); })
      .finally(function () { S.busy = false; }));
  }
  else if (a === "rejask") { S.rejecting = true; render(true); var rr = $("#f-reason"); if (rr) rr.focus(); }
  else if (a === "rejcancel") { S.rejecting = false; render(true); }
  else if (a === "reject") {
    var reason = ($("#f-reason") || {}).value || "";
    busy(b, api("/api/reviews/" + S.detail + "/reject", { method: "POST", body: { reason: reason } })
      .then(function (d) { toast(d.message); S.rejecting = false; return load("review", true); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "msg") {
    var box = $("#msg");
    var text = box ? box.value.trim() : "";
    if (!text) { toast("Напиши сообщение"); return; }
    busy(b, api("/api/reviews/" + S.detail + "/message", { method: "POST", body: { text: text } })
      .then(function (d) { toast(d.message); return load("review", true); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "cred") {
    busy(b, api("/api/users/" + b.dataset.id + "/credits", { method: "POST", body: { amount: Number(v) } })
      .then(function () { toast(Number(v) > 0 ? "Оценка добавлена — человеку пришло сообщение" : "Оценка списана"); return load("users", true); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "ban") {
    busy(b, api("/api/users/" + b.dataset.id + "/ban", { method: "POST", body: { banned: v === "1" } })
      .then(function () { toast(v === "1" ? "Забанен" : "Разбанен"); return load("users", true); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "text") openText(v);
  else if (a === "preview") go("preview");
  else if (a === "pvedit") { if (S.texts) openText(v); else load("texts", true).then(function () { openText(v); }); }
  else if (a === "tback") { S.tab = "texts"; render(); load("texts", true); }
  else if (a === "var") insertAtCursor("{" + v + "}");
  else if (a === "timg") $("#timg-file").click();
  else if (a === "timgdel") { S.textImg = null; S.textImgState = "none"; render(true); }
  else if (a === "tsave") {
    var html = edText();
    if (!html) { toast("Текст пустой"); return; }
    var image = S.textImgState === "new" ? S.textImg : S.textImgState === "none" ? "none" : "keep";
    busy(b, api("/api/texts/" + S.textKey, { method: "PUT", body: { text: html, image: image } })
      .then(function () { toast("Сохранено — бот уже пишет так"); S.textImgState = "keep"; return load("texts", true); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "ttest") busy(b, api("/api/texts/" + S.textKey + "/test", { method: "POST" }).then(function (d) { toast(d.message); }).catch(function (er) { toast(er.message); }));
  else if (a === "treset") {
    busy(b, api("/api/texts/" + S.textKey, { method: "DELETE" })
      .then(function () { toast("Вернули стандартный текст"); S.textImg = null; S.textImgState = "keep"; return load("text", false); })
      .catch(function (er) { toast(er.message); }));
  }
  else if (a === "seg") { S.segment = v; S.bcConfirm = false; render(true); }
  else if (a === "bimg") $("#bimg-file").click();
  else if (a === "bimgdel") { S.bcImages.splice(Number(v), 1); render(true); }
  else if (a === "bcask") {
    if (!edText() && !S.bcImages.length) { toast("Добавь текст или фото"); return; }
    S.bcConfirm = true; render(true);
  }
  else if (a === "bcno") { S.bcConfirm = false; render(true); }
  else if (a === "bcgo") {
    busy(b, api("/api/broadcast", { method: "POST", body: { text: edText(), images: S.bcImages, segment: S.segment } })
      .then(function (d) { toast(d.message); S.bcConfirm = false; S.bcHtml = ""; S.bcImages = []; var ed = $("#ed"); if (ed) ed.innerHTML = ""; render(true); })
      .catch(function (er) { toast(er.message); S.bcConfirm = false; render(true); }));
  }
  else if (a === "linkno") { var lb = $("#linkbox"); if (lb) lb.remove(); }
  else if (a === "linkok") {
    var url = ($("#linkurl") || {}).value || "";
    url = url.trim();
    if (url && !/^(https?|tg):\/\//.test(url)) url = "https://" + url;
    var lbx = $("#linkbox");
    if (lbx) lbx.remove();
    if (!url || !savedRange) return;
    var ed2 = $("#ed");
    ed2.focus();
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(savedRange);
    try { document.execCommand("createLink", false, url); } catch (_) {}
    count();
  }
});

document.addEventListener("mousedown", function (e) {
  var h = e.target.closest && e.target.closest("[data-ins]");
  if (h) { e.preventDefault(); insertHeading(h.dataset.ins); return; }
  var f = e.target.closest && e.target.closest("[data-fmt]");
  if (!f) return;
  e.preventDefault();   // не теряем выделение в редакторе
  applyFormat(f.dataset.fmt);
});
document.addEventListener("keydown", function (e) {
  var t = e.target.closest && e.target.closest('[role="button"][data-act]');
  if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); t.click(); }
});
document.addEventListener("paste", function (e) {
  if (!e.target.closest || !e.target.closest("#ed")) return;
  e.preventDefault();
  var text = (e.clipboardData || window.clipboardData).getData("text/plain");
  insertAtCursor(text);
});

var searchTimer;
document.addEventListener("input", function (e) {
  var t = e.target;
  if (t.id === "ed") count();
  else if (t.dataset && t.dataset.f) { form(S.detail)[t.dataset.f] = t.value; saveForm(S.detail); }
  else if (t.dataset && t.dataset.note) { form(S.detail).notes[t.dataset.note] = t.value; saveForm(S.detail); autoGrow(t); }
  else if (t.id === "rq" || t.id === "uq") {
    if (t.id === "rq") S.q = t.value; else S.uq = t.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { load(t.id === "rq" ? "reviews" : "users", true).then(function () {
      var input = $("#" + t.id);
      if (input) { input.focus(); var n = input.value.length; try { input.setSelectionRange(n, n); } catch (_) {} }
    }); }, 300);
  }
});
document.addEventListener("change", function (e) {
  var t = e.target;
  if (t.id === "timg-file" && t.files[0]) {
    readImage(t.files[0]).then(function (data) { S.textImg = data; S.textImgState = "new"; render(true); }).catch(function (er) { toast(er.message); });
  }
  if (t.id === "bimg-file" && t.files.length) {
    var files = Array.prototype.slice.call(t.files, 0, 10 - S.bcImages.length);
    Promise.all(files.map(readImage)).then(function (list) { S.bcImages = S.bcImages.concat(list).slice(0, 10); render(true); })
      .catch(function (er) { toast(er.message); });
  }
});
document.addEventListener("click", function (e) {
  var link = e.target.closest && e.target.closest("a[data-ext]");
  if (link && tg && tg.openLink) { e.preventDefault(); tg.openLink(link.href); }
}, true);

/* ---------- Старт ---------- */

function boot() {
  S.error = null;
  window.BOOT_STAGE = "вход (" + (initData() ? "данные Telegram есть" : "данных Telegram нет") + ")";
  render();
  var bi = document.createElement("p");
  bi.id = "bootInfo2"; bi.style.cssText = "text-align:center;color:#5f626a;font-size:12px;margin-top:6px";
  if (!S.me && !S.error) $("#app").appendChild(bi);
  var t0 = Date.now();
  /* секунды тикают — значит страница живая и ждёт сервер */
  var tick = setInterval(function () {
    var el = document.getElementById("bootInfo2");
    if (!el || window.BOOT_DONE) { clearInterval(tick); return; }
    el.textContent = "v" + VER + " · " + window.BOOT_STAGE + " · " + Math.round((Date.now() - t0) / 1000) + " с";
  }, 500);
  bi.textContent = "v" + VER + " · " + window.BOOT_STAGE + " · 0 с";
  if (window.PING) PING("boot: " + window.BOOT_STAGE + ", платформа " + (tg ? tg.platform + " " + tg.version : "без скрипта Telegram"));
  window.BOOT_STAGE = "ждём ответ сервера";
  api("/api/me").then(function (me) {
    if (window.PING) PING("вход: ответ разобран, имя " + (me && me.name));
    S.me = me;
    window.BOOT_DONE = true;
    try {
      var m = /[?&]r=(\d+)/.exec(location.search);
      if (m) { openReview(m[1]); load("reviews", true); }
      else go("reviews");
      if (window.PING) PING("вход успешен, админка открыта");
    } catch (err) {
      var msg = (err && err.message || String(err)) + " | " + String(err && err.stack || "").split("\n").slice(0, 3).join(" < ");
      if (window.PING) PING("СБОЙ ОТРИСОВКИ: " + msg);
      $("#app").innerHTML = '<div class="empty"><p><b>Сбой при открытии</b></p><p class="meta" style="font-size:12px;word-break:break-word">' + esc(msg) + "</p></div>";
    }
  }).catch(function (e) { window.BOOT_DONE = true; S.error = e; render(); if (window.PING) PING("вход не удался: " + (e.status || "") + " " + e.message); });
}

$("#refresh").innerHTML = ic("refresh");
$("#refresh").addEventListener("click", function () { load(S.tab, true); });
var tgReady = false;
function setupTg() {
  tg = window.Telegram && window.Telegram.WebApp || tg;
  if (!tg || tgReady) return;
  tgReady = true;
  try {
    tg.ready(); tg.expand();
    if (window.BOOT_STAGE === "страница") window.BOOT_STAGE = "скрипт Telegram загружен";
    tg.setHeaderColor("#151619"); tg.setBackgroundColor("#151619");
    tg.BackButton.onClick(function () { if (S.tab === "review") go("reviews"); else if (S.tab === "text" || S.tab === "preview") { S.tab = "texts"; render(); load("texts", true); } else location.href = "/#admin/overview"; });
  } catch (_) {}
}
window.addEventListener("load", setupTg);
/* Ждём скрипт Telegram не дольше 2,5 секунды, дальше открываемся с данными из адреса. */
window.BOOT_STAGE = "ждём Telegram";
(function start(waited) {
  if ((window.Telegram && window.Telegram.WebApp) || waited >= 2500 || (!HASH_DATA && waited >= 600 && !window.Telegram)) {
    setupTg();
    boot();
    return;
  }
  setTimeout(function () { start(waited + 100); }, 100);
})(0);
})();
