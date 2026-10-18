/* Парсер и скрипты внутри мини-аппа C&C Family: общий адрес API, тема и кнопка «назад». */
(function () {
  "use strict";
  var base = "/" + (location.pathname.split("/")[1] || "");
  window.CC_BASE = base;
  window.ccTheme = function () {
    try {
      var t = localStorage.getItem("cc_theme");
      if (t === "light" || t === "dark") return t;
    } catch (e) {}
    var tg = window.Telegram && window.Telegram.WebApp;
    return tg && tg.colorScheme === "light" ? "light" : "dark";
  };
  function home() {
    var ret = "#categories";
    try { ret = sessionStorage.getItem("cc_return") || ret; sessionStorage.removeItem("cc_return"); } catch (e) {}
    location.href = "/" + (ret === "#" ? "" : ret);
  }
  window.ccGo = function (hash) {
    try { sessionStorage.removeItem("cc_return"); } catch (e) {}
    location.href = "/#" + hash;
  };
  document.documentElement.dataset.theme = window.ccTheme();
  document.addEventListener("DOMContentLoaded", function () {
    var brand = document.querySelector("header .brand");
    if (brand) {
      var title = brand.textContent.trim();
      brand.innerHTML = '<button class="cc-back" type="button" aria-label="Назад в C&amp;C">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="m15 5-7 7 7 7"/></svg>' +
        "<span>C&amp;C</span></button><b class=\"cc-title\"></b>";
      brand.querySelector(".cc-title").textContent = { "/parser": "Парсер" }[base] || title;
      brand.querySelector(".cc-back").addEventListener("click", home);
    }
    var tg = window.Telegram && window.Telegram.WebApp;
    try { tg.BackButton.show(); tg.BackButton.onClick(home); } catch (e) {}
  });
})();
