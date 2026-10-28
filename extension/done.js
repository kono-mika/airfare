// The "Price check done" page in the language picked in AirFare (done.html?lang=es).
(() => {
  const TEXT = {
    es: ["Comprobación de precios terminada",
         "AirFare ha cerrado las pestañas de vuelos que abrió. Esta página se queda para que Chrome no guarde las " +
         "páginas de vuelos como tu última sesión. Si Chrome ofrece restaurar tus pestañas anteriores, puedes hacerlo " +
         "aquí. Si no, cierra esta ventana."],
    ru: ["Проверка цен завершена",
         "AirFare закрыл вкладки с рейсами, которые открывал. Эта страница остаётся, чтобы Chrome не запомнил " +
         "страницы рейсов как ваш последний сеанс. Если Chrome предложит восстановить прежние вкладки, это можно " +
         "сделать здесь. Иначе просто закройте это окно."],
  };
  const lang = new URLSearchParams(location.search).get("lang");
  const t = TEXT[lang];
  if (!t) return;
  document.documentElement.lang = lang;
  document.title = "AirFare: " + t[0];
  document.getElementById("t").textContent = t[0];
  document.getElementById("s").textContent = t[1];
})();
