"""Spanish and Russian versions of AirFare's interface texts, keyed by the English text (see i18n.py).

Plural texts list their forms between "|": two in Spanish, three in Russian (1 рейс, 2 рейса, 5 рейсов).
Keys starting with "html:" are passages with formatting; the English version is in the page itself.
tools/i18n_keys.py lists any text the interface uses that is missing here.
"""

_PAIRS = {
    # ----- top bar, pages ------------------------------------------------------------------
    "Dashboard": ("Panel", "Панель"),
    "Price history": ("Historial de precios", "История цен"),
    "Settings": ("Ajustes", "Настройки"),
    "Starting AirFare…": ("Iniciando AirFare…", "Запуск AirFare…"),
    "AirFare didn't start. Open it from its desktop or Start menu icon.":
        ("AirFare no se ha iniciado. Ábrelo desde su icono del escritorio o del menú Inicio.",
         "AirFare не запустился. Откройте его значком на рабочем столе или в меню «Пуск»."),

    # ----- Settings: header and routes --------------------------------------------------------
    "Watches the flights you choose and tells you when one gets cheaper.":
        ("Vigila los vuelos que elijas y te avisa cuando uno baja de precio.",
         "Следит за выбранными рейсами и сообщает, когда какой-то из них дешевеет."),
    "Flights to track": ("Vuelos a seguir", "Отслеживаемые рейсы"),
    "Airport or city codes, and an exact date or a range of dates.":
        ("Códigos de aeropuerto o ciudad y una fecha exacta o un rango de fechas.",
         "Коды аэропортов или городов и точная дата либо диапазон дат."),
    "+ Add route": ("+ Añadir ruta", "+ Добавить маршрут"),
    "+ Add a Skyscanner link": ("+ Añadir un enlace de Skyscanner", "+ Добавить ссылку Skyscanner"),
    "+ Another link": ("+ Otro enlace", "+ Ещё ссылка"),
    "Name (optional), e.g. Weekend in Rome": ("Nombre (opcional), p. ej. Fin de semana en Roma",
                                              "Название (необязательно), например «Выходные в Риме»"),
    "Route name": ("Nombre de la ruta", "Название маршрута"),
    "Track": ("Seguir", "Следить"),
    "Remove route": ("Quitar ruta", "Удалить маршрут"),
    "Remove this route?": ("¿Quitar esta ruta?", "Удалить этот маршрут?"),
    "From": ("Desde", "Откуда"),
    "To": ("Hasta", "Куда"),
    "Swap From and To": ("Intercambiar origen y destino", "Поменять местами «Откуда» и «Куда»"),
    "Trip": ("Viaje", "Поездка"),
    "One-way": ("Solo ida", "В одну сторону"),
    "Return": ("Ida y vuelta", "Туда и обратно"),
    "Depart on (or from)": ("Salida el (o desde el)", "Вылет (или начиная с)"),
    "…until (optional, flexible dates)": ("…hasta (opcional, fechas flexibles)", "…по (необязательно, гибкие даты)"),
    "Return on (or from)": ("Vuelta el (o desde el)", "Обратно (или начиная с)"),
    "…until (optional)": ("…hasta (opcional)", "…по (необязательно)"),
    "Adults": ("Adultos", "Взрослые"),
    "Cabin": ("Clase", "Класс"),
    "Economy": ("Turista", "Эконом"),
    "Premium economy": ("Turista superior", "Комфорт"),
    "Business": ("Business", "Бизнес"),
    "First": ("Primera", "Первый"),
    "Prefer direct flights": ("Preferir vuelos directos", "Предпочитать прямые рейсы"),
    "Paste Skyscanner result links (open the search on Skyscanner and copy the address bar).":
        ("Pega enlaces de resultados de Skyscanner (abre la búsqueda en Skyscanner y copia la barra de direcciones).",
         "Вставьте ссылки на результаты Skyscanner (откройте поиск на Skyscanner и скопируйте адресную строку)."),
    "Test this route": ("Probar esta ruta", "Проверить этот маршрут"),
    "Link": ("Enlace", "Ссылка"),
    "Skyscanner link": ("Enlace de Skyscanner", "Ссылка Skyscanner"),
    "{n} adult|{n} adults": ("{n} adulto|{n} adultos", "{n} взрослый|{n} взрослых|{n} взрослых"),
    "{n} date combination for this route|{n} date combinations for this route":
        ("{n} combinación de fechas para esta ruta|{n} combinaciones de fechas para esta ruta",
         "{n} комбинация дат для этого маршрута|{n} комбинации дат для этого маршрута|{n} комбинаций дат для этого маршрута"),
    "No pages: the dates are in the past": ("Sin páginas: las fechas ya han pasado", "Нет страниц: даты уже прошли"),
    "not tested": ("sin probar", "не проверено"),
    "Over the page limit": ("Por encima del límite de páginas", "Сверх лимита страниц"),
    "skipped": ("omitida", "пропущено"),
    "one-way": ("solo ida", "в одну сторону"),
    "Pasted link": ("Enlace pegado", "Вставленная ссылка"),
    "your link": ("tu enlace", "ваша ссылка"),
    "auto": ("auto", "авто"),
    "open": ("abrir", "открыть"),
    "change link": ("cambiar enlace", "изменить ссылку"),
    "use my own link": ("usar mi enlace", "использовать свою ссылку"),
    "Paste the working Skyscanner link for these dates": ("Pega el enlace de Skyscanner que funciona para estas fechas",
                                                          "Вставьте рабочую ссылку Skyscanner для этих дат"),
    "Use link": ("Usar enlace", "Использовать ссылку"),
    "from {price}, {n} flights": ("desde {price}, {n} vuelos", "от {price}, рейсов: {n}"),
    "robot check not solved": ("comprobación de robot sin resolver", "проверка на робота не пройдена"),

    # ----- Settings: price sources ------------------------------------------------------------
    "Price sources": ("Fuentes de precios", "Источники цен"),
    "Where AirFare reads prices. One is enough; more give a fuller picture.":
        ("Dónde lee AirFare los precios. Con una basta; varias dan una imagen más completa.",
         "Где AirFare берёт цены. Хватит одного источника, несколько дают более полную картину."),
    "Chrome extension": ("Extensión de Chrome", "Расширение Chrome"),
    "Copy address": ("Copiar dirección", "Копировать адрес"),
    "Show folder": ("Mostrar carpeta", "Показать папку"),
    "That's it. AirFare opens your Skyscanner and Aviasales pages in a minimized Chrome window and closes only those tabs when it's done. If a site asks for a robot check, the window comes up so you can solve it.":
        ("Listo. AirFare abre tus páginas de Skyscanner y Aviasales en una ventana de Chrome minimizada y, al terminar, "
         "cierra solo esas pestañas. Si un sitio pide una comprobación de robot, la ventana aparece para que la resuelvas.",
         "Вот и всё. AirFare открывает ваши страницы Skyscanner и Aviasales в свёрнутом окне Chrome и по окончании "
         "закрывает только эти вкладки. Если сайт попросит пройти проверку на робота, окно появится, чтобы вы её прошли."),
    "Google Flights (SerpApi)": ("Google Flights (SerpApi)", "Google Flights (SerpApi)"),
    "optional": ("opcional", "необязательно"),
    "Only needed if you want Google Flights prices too. Skyscanner and Aviasales work without it.":
        ("Solo hace falta si también quieres precios de Google Flights. Skyscanner y Aviasales funcionan sin ello.",
         "Нужно, только если вам нужны ещё и цены Google Flights. Skyscanner и Aviasales работают без этого."),
    "SerpApi key": ("Clave de SerpApi", "Ключ SerpApi"),
    "Save key": ("Guardar clave", "Сохранить ключ"),
    "Remove saved key": ("Quitar la clave guardada", "Удалить сохранённый ключ"),
    "Searches left this month": ("Búsquedas que quedan este mes", "Осталось поисков в этом месяце"),
    "Check": ("Comprobar", "Проверить"),
    "serpapi.com → Api Key": ("serpapi.com → Api Key", "serpapi.com → Api Key"),
    "platform.deepseek.com → API keys": ("platform.deepseek.com → API keys", "platform.deepseek.com → API keys"),
    "Saved key {key}. Type a new key to replace it.": ("Clave guardada {key}. Escribe una nueva para sustituirla.",
                                                       "Сохранён ключ {key}. Введите новый, чтобы заменить его."),
    "The saved key can't be read on this Windows account. Paste it again.":
        ("La clave guardada no se puede leer con esta cuenta de Windows. Pégala de nuevo.",
         "Сохранённый ключ нельзя прочитать в этой учётной записи Windows. Вставьте его снова."),
    "Paste the key first.": ("Pega primero la clave.", "Сначала вставьте ключ."),
    "Saving…": ("Guardando…", "Сохранение…"),
    "Saved, but the service says: {error}": ("Guardada, pero el servicio responde: {error}",
                                             "Сохранено, но сервис отвечает: {error}"),
    "Saved. {n} searches left this month.": ("Guardada. Quedan {n} búsquedas este mes.",
                                             "Сохранено. В этом месяце осталось поисков: {n}."),
    "Saved. Balance: {balance}.": ("Guardada. Saldo: {balance}.", "Сохранено. Баланс: {balance}."),
    "Remove the saved key?": ("¿Quitar la clave guardada?", "Удалить сохранённый ключ?"),
    "Key removed.": ("Clave eliminada.", "Ключ удалён."),
    "plan": ("plan", "тариф"),
    "Chrome is still running an older copy of the extension (v{old}; this AirFare has v{new}). Open chrome://extensions and click the reload arrow on AirFare collector, or restart Chrome.":
        ("Chrome sigue usando una copia antigua de la extensión (v{old}; este AirFare trae la v{new}). Abre "
         "chrome://extensions y pulsa la flecha de recarga de AirFare collector, o reinicia Chrome.",
         "Chrome всё ещё использует старую копию расширения (v{old}; в этом AirFare v{new}). Откройте "
         "chrome://extensions и нажмите стрелку перезагрузки у AirFare collector или перезапустите Chrome."),
    "Connected: last heard from the extension (v{version}) on {when}.":
        ("Conectada: la extensión (v{version}) respondió por última vez el {when}.",
         "Подключено: расширение (v{version}) последний раз отвечало {when}."),
    "Not connected yet. The extension reports in the first time AirFare tests links or checks prices.":
        ("Aún no conectada. La extensión se presenta la primera vez que AirFare prueba enlaces o comprueba precios.",
         "Ещё не подключено. Расширение отзовётся, когда AirFare впервые проверит ссылки или цены."),
    "Copied. Paste it into Chrome's address bar.": ("Copiado. Pégalo en la barra de direcciones de Chrome.",
                                                    "Скопировано. Вставьте в адресную строку Chrome."),
    "Type chrome://extensions into Chrome's address bar.": ("Escribe chrome://extensions en la barra de direcciones de Chrome.",
                                                            "Введите chrome://extensions в адресную строку Chrome."),

    # ----- Settings: currency -----------------------------------------------------------------
    "Currency": ("Moneda", "Валюта"),
    "Every price is compared, alerted and shown in this currency. Prices a site shows in another currency are converted with the day's exchange rate.":
        ("Todos los precios se comparan, se avisan y se muestran en esta moneda. Los que un sitio muestra en otra "
         "moneda se convierten con el tipo de cambio del día.",
         "Все цены сравниваются, отслеживаются и показываются в этой валюте. Цены в другой валюте пересчитываются "
         "по курсу дня."),
    "Euro": ("Euro", "Евро"),
    "Pound": ("Libra", "Фунт"),
    "Dollar": ("Dólar", "Доллар"),
    "Ruble": ("Rublo", "Рубль"),
    "Aviasales.ru shows rubles: AirFare converts them for you.":
        ("Aviasales.ru muestra rublos: AirFare los convierte por ti.", "Aviasales.ru показывает рубли: AirFare пересчитает их за вас."),
    "Aviasales shows rubles already; other sites are converted.":
        ("Aviasales ya muestra rublos; los demás sitios se convierten.", "Aviasales уже показывает рубли; цены других сайтов пересчитываются."),

    # ----- Settings: price alerts -------------------------------------------------------------
    "Price alerts": ("Alertas de precio", "Оповещения о ценах"),
    "Three kinds of LOW PRICE alert, each with its own threshold: a small drop on a comfortable trip can matter more than a bigger one on a 40-hour journey.":
        ("Tres tipos de alerta LOW PRICE, cada uno con su propio umbral: una pequeña bajada en un viaje cómodo puede "
         "importar más que una mayor en un trayecto de 40 horas.",
         "Три вида оповещений LOW PRICE, у каждого свой порог: небольшое снижение цены удобного рейса может быть важнее "
         "большой скидки на 40-часовой перелёт."),
    "Cheapest": ("Más barato", "Самый дешёвый"),
    "Fastest": ("Más rápido", "Самый быстрый"),
    "Best value": ("Mejor opción", "Лучший вариант"),
    "The lowest fare, however long the trip.": ("La tarifa más baja, dure lo que dure el viaje.",
                                                "Самый низкий тариф, сколько бы ни длилась поездка."),
    "The cheapest of the quickest trips (within 10% of the shortest travel time).":
        ("El más barato de los viajes más rápidos (hasta un 10 % por encima del tiempo de viaje más corto).",
         "Самый дешёвый из самых быстрых вариантов (не более чем на 10% дольше самого короткого)."),
    "Your analyst's pick, balancing price, stops, travel time and departure hours.":
        ("La elección de tu analista, equilibrando precio, escalas, duración y horarios.",
         "Выбор вашего аналитика с учётом цены, пересадок, времени в пути и часов вылета."),
    "when it drops by": ("cuando baje un", "при снижении на"),
    "or costs at most": ("o cueste como mucho", "или если стоит не дороже"),
    "Ignore trips where one direction takes longer than": ("Ignorar viajes en los que un trayecto dure más de",
                                                           "Не учитывать поездки, где путь в одну сторону дольше"),
    "hours": ("horas", "ч"),
    "Ignore self-transfer trips (you collect your bags and check in again)":
        ("Ignorar viajes con autotransbordo (recoges el equipaje y vuelves a facturar)",
         "Не учитывать перелёты с самостоятельной пересадкой (нужно забрать багаж и снова зарегистрироваться)"),
    "Each kind compares with its own price at its last alert (or the first price seen), so daily wobbles stay quiet but a slow slide still alerts once it adds up. A drop of 0% means any drop. The price limit alerts as soon as a fare is at or under it, then again only when it gets cheaper still.":
        ("Cada tipo se compara con su propio precio de la última alerta (o el primero visto), así que las oscilaciones "
         "diarias no avisan, pero una bajada lenta sí avisa cuando se acumula. Una bajada del 0 % significa cualquier "
         "bajada. El límite de precio avisa en cuanto una tarifa lo iguala o baja de él, y luego solo si baja aún más.",
         "Каждый вид сравнивается со своей ценой на момент последнего оповещения (или с первой увиденной), поэтому "
         "ежедневные колебания не беспокоят, а медленное снижение всё равно даст оповещение, когда накопится. "
         "Снижение на 0% означает любое снижение. Ценовой предел срабатывает, как только тариф достигнет его или "
         "опустится ниже, а затем только при дальнейшем удешевлении."),

    # ----- Settings: schedule -----------------------------------------------------------------
    "When to check": ("Cuándo comprobar", "Когда проверять"),
    "AirFare runs quietly in the background and only speaks up for a low price.":
        ("AirFare funciona en segundo plano sin molestar y solo avisa cuando hay un precio bajo.",
         "AirFare тихо работает в фоне и даёт о себе знать только при низкой цене."),
    "Hours between checks": ("Horas entre comprobaciones", "Часов между проверками"),
    "Background checker is running.": ("El comprobador en segundo plano está activo.", "Фоновая проверка запущена."),
    "Background checker is running; next check around {when}.":
        ("El comprobador en segundo plano está activo; próxima comprobación hacia las {when}.",
         "Фоновая проверка запущена; следующая проверка около {when}."),
    "AirFare checks once each time the PC starts.": ("AirFare comprueba una vez cada vez que se enciende el PC.",
                                                     "AirFare проверяет цены один раз при каждом включении ПК."),
    "The background checker starts when you press Save (and at every PC start after that).":
        ("El comprobador en segundo plano se inicia al pulsar Guardar (y en cada arranque del PC a partir de entonces).",
         "Фоновая проверка начнётся после нажатия «Сохранить» (и затем при каждом включении ПК)."),
    "At most about {n} Google Flights searches a month with this schedule (SerpApi free plan: 250; repeats within an hour are free).":
        ("Como mucho unas {n} búsquedas de Google Flights al mes con este horario (plan gratuito de SerpApi: 250; "
         "las repetidas en una hora son gratis).",
         "Не более примерно {n} поисков Google Flights в месяц при таком расписании (бесплатный тариф SerpApi: 250; "
         "повторы в течение часа бесплатны)."),

    # ----- Settings: analyst ------------------------------------------------------------------
    "AI analyst": ("Analista de IA", "ИИ-аналитик"),
    "Reads every check's prices and picks the cheapest and best-value flights. It writes in the language you picked.":
        ("Lee los precios de cada comprobación y elige los vuelos más baratos y la mejor opción. Escribe en el idioma "
         "que hayas elegido.",
         "Читает цены каждой проверки и выбирает самые дешёвые и самые выгодные рейсы. Пишет на выбранном вами языке."),
    "Log in to Claude": ("Iniciar sesión en Claude", "Войти в Claude"),
    "Check again": ("Comprobar de nuevo", "Проверить снова"),
    "Claude model": ("Modelo de Claude", "Модель Claude"),
    "Sonnet 5.5 (recommended, ~$0.07 a check)": ("Sonnet 5.5 (recomendado, ~0,07 $ por comprobación)",
                                                 "Sonnet 5.5 (рекомендуется, ~$0.07 за проверку)"),
    "Haiku 5.5 (cheapest, ~$0.01 a check)": ("Haiku 5.5 (el más barato, ~0,01 $ por comprobación)",
                                             "Haiku 5.5 (самая дешёвая, ~$0.01 за проверку)"),
    "Opus 5.5 (most thorough, ~$0.12 a check)": ("Opus 5.5 (el más minucioso, ~0,12 $ por comprobación)",
                                                 "Opus 5.5 (самая тщательная, ~$0.12 за проверку)"),
    "Account default": ("Predeterminado de la cuenta", "По умолчанию для аккаунта"),
    "DeepSeek API key": ("Clave API de DeepSeek", "API-ключ DeepSeek"),
    "DeepSeek model": ("Modelo de DeepSeek", "Модель DeepSeek"),
    "V4.1 Flash (recommended, under $0.01 a check)": ("V4.1 Flash (recomendado, menos de 0,01 $ por comprobación)",
                                                      "V4.1 Flash (рекомендуется, меньше $0.01 за проверку)"),
    "V4 Pro (stronger, a few cents a check)": ("V4 Pro (más potente, unos céntimos por comprobación)",
                                               "V4 Pro (сильнее, несколько центов за проверку)"),
    "Balance": ("Saldo", "Баланс"),
    "not enough credit": ("saldo insuficiente", "недостаточно средств"),
    "New conversation after (thousand tokens)": ("Conversación nueva tras (miles de tokens)", "Новый диалог после (тысяч токенов)"),
    "Checks are hours apart, so a long conversation gets re-read in full every time. AirFare starts a fresh one before it passes this size; your price history and the analyst's last recommendation carry over.":
        ("Las comprobaciones están separadas por horas, así que una conversación larga se vuelve a leer entera cada "
         "vez. AirFare empieza una nueva antes de superar este tamaño; tu historial de precios y la última "
         "recomendación del analista se conservan.",
         "Проверки идут с перерывом в несколько часов, поэтому длинный диалог каждый раз перечитывается целиком. "
         "AirFare начинает новый, прежде чем диалог превысит этот размер; история цен и последняя рекомендация "
         "аналитика сохраняются."),
    "Checking the Claude login…": ("Comprobando la sesión de Claude…", "Проверка входа в Claude…"),
    "Logged in to Claude.": ("Sesión iniciada en Claude.", "Вход в Claude выполнен."),
    "Logged in to Claude ({plan}).": ("Sesión iniciada en Claude ({plan}).", "Вход в Claude выполнен ({plan})."),
    "Not logged in yet. Press Log in to Claude and sign in with your Claude account.":
        ("Aún no has iniciado sesión. Pulsa Iniciar sesión en Claude y entra con tu cuenta de Claude.",
         "Вход ещё не выполнен. Нажмите «Войти в Claude» и войдите в свой аккаунт Claude."),
    "A Claude login window opened. Sign in there, then press Check again.":
        ("Se ha abierto una ventana para iniciar sesión en Claude. Entra allí y luego pulsa Comprobar de nuevo.",
         "Открылось окно входа в Claude. Войдите там, затем нажмите «Проверить снова»."),

    # ----- Settings: fine-tuning, latest analysis, action bar ---------------------------------
    "Fine-tuning": ("Ajustes finos", "Тонкая настройка"),
    "Which Skyscanner site to use and how long to wait for prices.": ("Qué sitio de Skyscanner usar y cuánto esperar a los precios.",
                                                                      "Какой сайт Skyscanner использовать и сколько ждать цен."),
    "Skyscanner site": ("Sitio de Skyscanner", "Сайт Skyscanner"),
    "Seconds to wait per page": ("Segundos de espera por página", "Секунд ожидания на страницу"),
    "Most pages per check": ("Máximo de páginas por comprobación", "Максимум страниц за проверку"),
    "{n} date combination per check|{n} date combinations per check":
        ("{n} combinación de fechas por comprobación|{n} combinaciones de fechas por comprobación",
         "{n} комбинация дат за проверку|{n} комбинации дат за проверку|{n} комбинаций дат за проверку"),
    "{n} SerpApi search|{n} SerpApi searches": ("{n} búsqueda de SerpApi|{n} búsquedas de SerpApi",
                                                "{n} поиск SerpApi|{n} поиска SerpApi|{n} поисков SerpApi"),
    "{n} more is over the limit and will be skipped.|{n} more are over the limit and will be skipped.":
        ("{n} más supera el límite y se omitirá.|{n} más superan el límite y se omitirán.",
         "Ещё {n} сверх лимита и будет пропущена.|Ещё {n} сверх лимита и будут пропущены.|Ещё {n} сверх лимита и будут пропущены."),
    "Latest analysis": ("Último análisis", "Последний анализ"),
    "What your analyst said after the most recent check.": ("Lo que dijo tu analista tras la última comprobación.",
                                                            "Что сказал ваш аналитик после последней проверки."),
    "open the dashboard": ("abrir el panel", "открыть панель"),
    "Test links": ("Probar enlaces", "Проверить ссылки"),
    "Open tracker browser": ("Abrir navegador de seguimiento", "Открыть браузер отслеживания"),
    "Run check now": ("Comprobar ahora", "Проверить сейчас"),
    "Save": ("Guardar", "Сохранить"),
    "Unsaved changes": ("Cambios sin guardar", "Есть несохранённые изменения"),
    "Saved. AirFare checks these on the schedule below.": ("Guardado. AirFare los comprueba según el horario de abajo.",
                                                           "Сохранено. AirFare проверяет их по расписанию ниже."),
    "Fill in your first route, then press Save.": ("Rellena tu primera ruta y pulsa Guardar.",
                                                   "Заполните первый маршрут и нажмите «Сохранить»."),
    "Testing links… this takes about {n} seconds": ("Probando enlaces… tarda unos {n} segundos",
                                                    "Проверка ссылок… это займёт около {n} секунд"),
    "{source}: {good} of {total} show prices": ("{source}: {good} de {total} muestran precios",
                                                "{source}: цены есть на {good} из {total}"),
    "Running a full check: opening pages, waiting for prices, asking your analyst…":
        ("Comprobación completa en marcha: abriendo páginas, esperando precios, consultando a tu analista…",
         "Идёт полная проверка: открываем страницы, ждём цены, спрашиваем аналитика…"),
    "Tracker browser is open. Accept cookies, set your currency, or solve a robot check, then close that window.":
        ("El navegador de seguimiento está abierto. Acepta las cookies, elige tu moneda o resuelve una comprobación "
         "de robot y luego cierra esa ventana.",
         "Браузер отслеживания открыт. Примите cookie, выберите валюту или пройдите проверку на робота, затем "
         "закройте это окно."),
    "Tracker browser closed.": ("Navegador de seguimiento cerrado.", "Браузер отслеживания закрыт."),
    "The check failed: {error}": ("La comprobación ha fallado: {error}", "Проверка не удалась: {error}"),
    "A {task} is running…": ("Hay una tarea en curso: {task}…", "Выполняется: {task}…"),
    "check": ("comprobación", "проверка"),
    "test": ("prueba", "тест"),
    "browser": ("navegador", "браузер"),
    "lookup": ("búsqueda", "поиск"),
    "Check finished.": ("Comprobación terminada.", "Проверка завершена."),
    "Nothing to check: add a route with future dates.": ("Nada que comprobar: añade una ruta con fechas futuras.",
                                                         "Нечего проверять: добавьте маршрут с будущими датами."),
    "Another check is already running.": ("Ya hay otra comprobación en marcha.", "Уже идёт другая проверка."),
    "The check failed; see the log.": ("La comprobación ha fallado; consulta el registro.", "Проверка не удалась; см. журнал."),
    "AirFare's local server has stopped. Open AirFare again.": ("El servidor local de AirFare se ha detenido. Vuelve a abrir AirFare.",
                                                                "Локальный сервер AirFare остановился. Откройте AirFare снова."),
    "Request failed ({status})": ("La solicitud ha fallado ({status})", "Запрос не удался ({status})"),
    "These settings weren't fully saved because this tab is talking to an outdated AirFare server. Close this tab, wait two minutes, then open AirFare again.":
        ("Estos ajustes no se han guardado del todo porque esta pestaña habla con un servidor de AirFare desactualizado. "
         "Cierra esta pestaña, espera dos minutos y vuelve a abrir AirFare.",
         "Эти настройки сохранены не полностью: вкладка связана с устаревшим сервером AirFare. Закройте вкладку, "
         "подождите две минуты и откройте AirFare снова."),
    "AirFare is busy with another check or test. Try again in a minute.":
        ("AirFare está ocupado con otra comprobación o prueba. Inténtalo dentro de un minuto.",
         "AirFare занят другой проверкой или тестом. Попробуйте через минуту."),
    "Last check {when}.": ("Última comprobación: {when}.", "Последняя проверка: {when}."),
    "{name} conversation {id}.": ("Conversación de {name}: {id}.", "Диалог {name}: {id}."),
    "The {name} conversation starts with the next check.": ("La conversación con {name} empieza en la próxima comprobación.",
                                                            "Диалог с {name} начнётся при следующей проверке."),
    "No checks yet. The {name} conversation starts with the first one.":
        ("Aún no hay comprobaciones. La conversación con {name} empieza con la primera.",
         "Проверок ещё не было. Диалог с {name} начнётся с первой."),

    # ----- Settings: messages from the server -------------------------------------------------
    "Pick at least one price source": ("Elige al menos una fuente de precios", "Выберите хотя бы один источник цен"),
    "The Skyscanner domain should look like www.skyscanner.net": ("El dominio de Skyscanner debe ser como www.skyscanner.net",
                                                                  "Домен Skyscanner должен выглядеть как www.skyscanner.net"),
    "The Chrome extension doesn't cover {domain}; pick a site from the list":
        ("La extensión de Chrome no cubre {domain}; elige un sitio de la lista",
         "Расширение Chrome не поддерживает {domain}; выберите сайт из списка"),
    "Pick a currency from the list": ("Elige una moneda de la lista", "Выберите валюту из списка"),
    "Pick English, Spanish or Russian": ("Elige inglés, español o ruso", "Выберите английский, испанский или русский"),
    "Pick a Claude model from the list": ("Elige un modelo de Claude de la lista", "Выберите модель Claude из списка"),
    "Pick a DeepSeek model from the list": ("Elige un modelo de DeepSeek de la lista", "Выберите модель DeepSeek из списка"),
    "Pick Claude or DeepSeek": ("Elige Claude o DeepSeek", "Выберите Claude или DeepSeek"),
    "Pick Claude or DeepSeek as the analyst": ("Elige Claude o DeepSeek como analista", "Выберите аналитиком Claude или DeepSeek"),
    "Add your DeepSeek API key, or switch the analyst back to Claude":
        ("Añade tu clave API de DeepSeek o vuelve a elegir Claude como analista",
         "Добавьте API-ключ DeepSeek или снова выберите аналитиком Claude"),
    "Add a DeepSeek API key in AirFare Settings to use DeepSeek": ("Añade una clave API de DeepSeek en los Ajustes de AirFare para usar DeepSeek",
                                                                   "Добавьте API-ключ DeepSeek в настройках AirFare, чтобы использовать DeepSeek"),
    "Add a DeepSeek API key in Settings to use DeepSeek.": ("Añade una clave API de DeepSeek en Ajustes para usar DeepSeek.",
                                                            "Добавьте API-ключ DeepSeek в настройках, чтобы использовать DeepSeek."),
    "The session size should be a number of thousand tokens, like 40": ("El tamaño de la sesión debe ser un número de miles de tokens, como 40",
                                                                         "Размер сессии указывается в тысячах токенов, например 40"),
    "The session size should be between 10 and 500 thousand tokens": ("El tamaño de la sesión debe estar entre 10 y 500 mil tokens",
                                                                       "Размер сессии должен быть от 10 до 500 тысяч токенов"),
    "Pick when AirFare should check": ("Elige cuándo debe comprobar AirFare", "Выберите, когда AirFare должен проверять"),
    "The check interval should be a number of hours, like 6": ("El intervalo debe ser un número de horas, como 6",
                                                               "Интервал указывается в часах, например 6"),
    "Check every 1 to 48 hours": ("Comprueba cada 1 a 48 horas", "Проверяйте раз в 1–48 часов"),
    "Route {i}: {problem}": ("Ruta {i}: {problem}", "Маршрут {i}: {problem}"),
    "use airport or city codes like LHR, LOND or BCN for From and To":
        ("usa códigos de aeropuerto o ciudad como LHR, LOND o BCN en Desde y Hasta",
         "укажите коды аэропортов или городов, например LHR, LOND или BCN, в полях «Откуда» и «Куда»"),
    "Use airport or city codes like LHR, LOND or BCN for From and To":
        ("Usa códigos de aeropuerto o ciudad como LHR, LOND o BCN en Desde y Hasta",
         "Укажите коды аэропортов или городов, например LHR, LOND или BCN, в полях «Откуда» и «Куда»"),
    "pick a departure date": ("elige una fecha de salida", "выберите дату вылета"),
    "Pick a departure date": ("Elige una fecha de salida", "Выберите дату вылета"),
    "pick a return date, or switch to one-way": ("elige una fecha de vuelta o cambia a solo ida",
                                                 "выберите дату возвращения или переключитесь на «В одну сторону»"),
    "Pick a return date, or switch to one-way": ("Elige una fecha de vuelta o cambia a solo ida",
                                                 "Выберите дату возвращения или переключитесь на «В одну сторону»"),
    "enter From/To codes or paste a Skyscanner link": ("escribe los códigos Desde/Hasta o pega un enlace de Skyscanner",
                                                       "введите коды «Откуда»/«Куда» или вставьте ссылку Skyscanner"),
    "Enter From/To codes or paste a Skyscanner link": ("Escribe los códigos Desde/Hasta o pega un enlace de Skyscanner",
                                                       "Введите коды «Откуда»/«Куда» или вставьте ссылку Skyscanner"),
    "{what} should be a number": ("{what} debe ser un número", "{what}: нужно число"),
    "{what} should be between {lo} and {hi}": ("{what} debe estar entre {lo} y {hi}", "{what}: значение от {lo} до {hi}"),
    "Cheapest: the price drop (%)": ("Más barato: la bajada de precio (%)", "Самый дешёвый: снижение цены (%)"),
    "Fastest: the price drop (%)": ("Más rápido: la bajada de precio (%)", "Самый быстрый: снижение цены (%)"),
    "Best value: the price drop (%)": ("Mejor opción: la bajada de precio (%)", "Лучший вариант: снижение цены (%)"),
    "Cheapest: the price limit": ("Más barato: el límite de precio", "Самый дешёвый: ценовой предел"),
    "Fastest: the price limit": ("Más rápido: el límite de precio", "Самый быстрый: ценовой предел"),
    "Best value: the price limit": ("Mejor opción: el límite de precio", "Лучший вариант: ценовой предел"),
    "The longest trip for alerts (hours)": ("El viaje más largo para alertas (horas)", "Самая долгая поездка для оповещений (часы)"),
    "Unknown key": ("Clave desconocida", "Неизвестный ключ"),
    "That doesn't look like an API key: paste only the key itself":
        ("Eso no parece una clave API: pega solo la clave", "Это не похоже на API-ключ: вставьте только сам ключ"),

    # ----- dashboard ----------------------------------------------------------------------------
    "Checked {when}": ("Comprobado el {when}", "Проверено {when}"),
    "{n} of {total} pages read": ("{n} de {total} páginas leídas", "прочитано страниц: {n} из {total}"),
    "prices in {currency}": ("precios en {currency}", "цены в {currency}"),
    "Low price": ("Precio bajo", "Низкая цена"),
    "a tracked flight got cheaper": ("un vuelo seguido ha bajado de precio", "отслеживаемый рейс подешевел"),
    "{name}'s take": ("La opinión de {name}", "Мнение {name}"),
    "{name}'s full analysis": ("Análisis completo de {name}", "Полный анализ от {name}"),
    "{name}'s pick": ("Elección de {name}", "Выбор {name}"),
    "{name} couldn't analyse this check. The prices above are still current.":
        ("{name} no ha podido analizar esta comprobación. Los precios de arriba siguen siendo actuales.",
         "{name} не смог проанализировать эту проверку. Цены выше по-прежнему актуальны."),
    "Full price data:": ("Datos completos de precios:", "Полные данные о ценах:"),
    "Exchange rates ({source}, {date}): {rates}": ("Tipos de cambio ({source}, {date}): {rates}",
                                                   "Курсы валют ({source}, {date}): {rates}"),
    "Out {dates}": ("Ida {dates}", "Туда {dates}"),
    "back {dates}": ("vuelta {dates}", "обратно {dates}"),
    "back": ("vuelta", "обратно"),
    "cheapest": ("más barato", "самый дешёвый"),
    "alert at {price}": ("alerta a {price}", "оповещение при {price}"),
    "alert below {price}": ("alerta por debajo de {price}", "оповещение ниже {price}"),
    "alert": ("alerta", "оповещение"),
    "Price trend": ("Evolución del precio", "Динамика цен"),
    "{source} cheapest": ("{source}: más barato", "{source}: самый дешёвый"),
    "Next cheapest alert": ("Próxima alerta del más barato", "Следующее оповещение о самом дешёвом"),
    "The price trend appears after the next check.": ("La evolución del precio aparece tras la próxima comprobación.",
                                                      "Динамика цен появится после следующей проверки."),
    "Cheapest price per check": ("Precio más bajo por comprobación", "Самая низкая цена за проверку"),
    "Cheapest by return date": ("Más barato por fecha de vuelta", "Самые дешёвые по дате возвращения"),
    "Cheapest by date pair": ("Más barato por par de fechas", "Самые дешёвые по парам дат"),
    "No prices this time": ("Esta vez no hay precios", "На этот раз цен нет"),
    "Best (as ranked by {source})": ("Mejores (según {source})", "Лучшие (по оценке {source})"),
    "return picked on {source}": ("vuelta a elegir en {source}", "обратный рейс выбирается на {source}"),
    "on the site: {price}": ("en el sitio: {price}", "на сайте: {price}"),
    "direct": ("directo", "прямой"),
    "{n} stop|{n} stops": ("{n} escala|{n} escalas", "{n} пересадка|{n} пересадки|{n} пересадок"),
    "overnight layover": ("escala nocturna", "ночная пересадка"),
    "visa needed": ("hace falta visado", "нужна виза"),
    "self-transfer": ("autotransbordo", "самостоятельная пересадка"),
    "No dashboard yet": ("Aún no hay panel", "Панели пока нет"),
    "It appears after the first price check. Save your routes in Settings, then press Run check now.":
        ("Aparece tras la primera comprobación de precios. Guarda tus rutas en Ajustes y pulsa Comprobar ahora.",
         "Она появится после первой проверки цен. Сохраните маршруты в настройках и нажмите «Проверить сейчас»."),

    # ----- notifications and the check ----------------------------------------------------------
    "Book now": ("Reservar", "Забронировать"),
    "Dismiss": ("Cerrar", "Закрыть"),
    "vs": ("frente a", "против"),
    "AirFare needs a hand": ("AirFare necesita una mano", "AirFare нужна ваша помощь"),
    "{site} is asking for a robot check. Please solve it in the {browser} window that just opened; AirFare continues by itself afterwards.":
        ("{site} pide una comprobación de robot. Resuélvela en la ventana de {browser} que se acaba de abrir; luego "
         "AirFare sigue solo.",
         "{site} просит пройти проверку на робота. Пройдите её в только что открывшемся окне {browser}; дальше AirFare "
         "продолжит сам."),
    "No internet connection, so prices were not checked this time.": ("No hay conexión a internet, así que esta vez no se han comprobado los precios.",
                                                                      "Нет подключения к интернету, поэтому цены в этот раз не проверены."),
    "AirFare couldn't read any prices": ("AirFare no ha podido leer ningún precio", "AirFare не смог прочитать ни одной цены"),
    "See the log for details.": ("Consulta el registro para más detalles.", "Подробности в журнале."),
    "Claude isn't logged in. Open AirFare and press Log in to Claude.":
        ("Claude no tiene la sesión iniciada. Abre AirFare y pulsa Iniciar sesión en Claude.",
         "Вход в Claude не выполнен. Откройте AirFare и нажмите «Войти в Claude»."),
    "Prices were saved, but {name} couldn't analyse them. {reason}": ("Los precios se han guardado, pero {name} no ha podido analizarlos. {reason}",
                                                                      "Цены сохранены, но {name} не смог их проанализировать. {reason}"),
    "The price check failed. See data\\logs\\airfare.log for details.":
        ("La comprobación de precios ha fallado. Consulta data\\logs\\airfare.log para más detalles.",
         "Проверка цен не удалась. Подробности в data\\logs\\airfare.log."),
    "Checking flight prices": ("Comprobando precios de vuelos", "Проверяем цены на рейсы"),
    "AirFare opened this window for its price check. Your own tabs aren't touched, and this window closes by itself when the check is done.":
        ("AirFare ha abierto esta ventana para comprobar precios. Tus pestañas no se tocan y esta ventana se cierra "
         "sola cuando termine.",
         "AirFare открыл это окно для проверки цен. Ваши вкладки не трогаются, а это окно закроется само, когда "
         "проверка закончится."),
    "Price check done": ("Comprobación de precios terminada", "Проверка цен завершена"),
    "AirFare opened {browser} only for its price check and has closed its own tabs. If {browser} offers to restore your previous tabs, you can do it in this window. Otherwise, close it.":
        ("AirFare abrió {browser} solo para comprobar precios y ha cerrado sus propias pestañas. Si {browser} ofrece "
         "restaurar tus pestañas anteriores, puedes hacerlo en esta ventana. Si no, ciérrala.",
         "AirFare открывал {browser} только для проверки цен и закрыл свои вкладки. Если {browser} предложит "
         "восстановить прежние вкладки, это можно сделать в этом окне. Иначе просто закройте его."),

    # ----- price history ----------------------------------------------------------------------
    "Conditions": ("Condiciones", "Условия"),
    "Route": ("Ruta", "Маршрут"),
    "Depart from": ("Salida desde", "Вылет с"),
    "Depart until": ("Salida hasta", "Вылет по"),
    "Return from": ("Vuelta desde", "Возвращение с"),
    "Return until": ("Vuelta hasta", "Возвращение по"),
    "Source": ("Fuente", "Источник"),
    "All sources": ("Todas las fuentes", "Все источники"),
    "Use the route's dates": ("Usar las fechas de la ruta", "Взять даты маршрута"),
    "Lowest price in the past 2 years": ("Precio más bajo en los últimos 2 años", "Самая низкая цена за последние 2 года"),
    "Analyst": ("Analista", "Аналитик"),
    "Model": ("Modelo", "Модель"),
    "Search the web": ("Buscar en la web", "Искать в интернете"),
    "Records": ("Registros", "Записи"),
    "Records ({n})": ("Registros ({n})", "Записи ({n})"),
    "Seen": ("Visto", "Когда"),
    "Depart": ("Salida", "Вылет"),
    "Price": ("Precio", "Цена"),
    "Airlines": ("Aerolíneas", "Авиакомпании"),
    "Stops": ("Escalas", "Пересадки"),
    "Travel time": ("Duración", "Время в пути"),
    "Delete all history for this route": ("Borrar todo el historial de esta ruta", "Удалить всю историю этого маршрута"),
    "Delete the {n} record shown|Delete the {n} records shown": ("Borrar el {n} registro mostrado|Borrar los {n} registros mostrados",
                                                                 "Удалить показанную запись ({n})|Удалить показанные записи ({n})|Удалить показанные записи ({n})"),
    "Delete the {n} record shown? This can't be undone.|Delete the {n} records shown? This can't be undone.":
        ("¿Borrar el {n} registro mostrado? No se puede deshacer.|¿Borrar los {n} registros mostrados? No se puede deshacer.",
         "Удалить показанную запись ({n})? Это нельзя отменить.|Удалить показанные записи ({n})? Это нельзя отменить.|"
         "Удалить показанные записи ({n})? Это нельзя отменить."),
    "Delete all price history for {name}? This can't be undone.": ("¿Borrar todo el historial de precios de {name}? No se puede deshacer.",
                                                                   "Удалить всю историю цен для «{name}»? Это нельзя отменить."),
    "Delete this record": ("Borrar este registro", "Удалить эту запись"),
    "Delete this record?": ("¿Borrar este registro?", "Удалить эту запись?"),
    "Delete this lookup": ("Borrar esta búsqueda", "Удалить этот поиск"),
    "Delete this lookup result?": ("¿Borrar este resultado de búsqueda?", "Удалить этот результат поиска?"),
    "Delete": ("Borrar", "Удалить"),
    "No prices recorded for these conditions yet.": ("Aún no hay precios registrados con estas condiciones.",
                                                     "Для этих условий цен пока нет."),
    "All-time cheapest": ("El más barato de siempre", "Самая низкая за всё время"),
    "Latest check": ("Última comprobación", "Последняя проверка"),
    "Above the all-time low": ("Por encima del mínimo histórico", "Выше исторического минимума"),
    "at the low": ("en el mínimo", "на минимуме"),
    "latest check vs all-time cheapest": ("última comprobación frente al más barato de siempre",
                                          "последняя проверка против самой низкой цены"),
    "seen {when}": ("visto el {when}", "замечено {when}"),
    "since {when}": ("desde el {when}", "с {when}"),
    "recorded {when}": ("registrado el {when}", "зафиксировано {when}"),
    "The trend appears after two checks with these conditions.": ("La evolución aparece tras dos comprobaciones con estas condiciones.",
                                                                  "Динамика появится после двух проверок с этими условиями."),
    "needs an API key": ("necesita una clave API", "нужен API-ключ"),
    "no longer tracked": ("ya no se sigue", "больше не отслеживается"),
    "Search the lowest price with {name} {model}": ("Buscar el precio más bajo con {name} {model}",
                                                    "Найти самую низкую цену с {name} {model}"),
    "{name} searches the web for the lowest price recorded in the past two years for exactly this route and these dates.":
        ("{name} busca en la web el precio más bajo registrado en los últimos dos años para exactamente esta ruta y estas fechas.",
         "{name} ищет в интернете самую низкую цену за последние два года именно для этого маршрута и этих дат."),
    '{name} answers only from what it already knows, without searching the web; expect "No information" most of the time.':
        ("{name} responde solo con lo que ya sabe, sin buscar en la web; casi siempre verás «Sin información».",
         "{name} отвечает только по тому, что уже знает, без поиска в интернете; чаще всего будет «Нет информации»."),
    '{name}\'s API can\'t browse the web, so it can only cite sources it already knows; expect "No information" most of the time.':
        ("La API de {name} no puede navegar por la web, así que solo puede citar fuentes que ya conoce; casi siempre "
         "verás «Sin información».",
         "API {name} не умеет ходить в интернет, поэтому может ссылаться только на уже известные ему источники; "
         "чаще всего будет «Нет информации»."),
    "A price is shown only if it is for these airports and dates, was recorded in the window, and AirFare finds it quoted on the cited page. Otherwise: No information.":
        ("Solo se muestra un precio si es de estos aeropuertos y fechas, se registró dentro del periodo y AirFare lo "
         "encuentra citado en la página indicada. Si no: Sin información.",
         "Цена показывается, только если она для этих аэропортов и дат, зафиксирована в этот период и AirFare "
         "находит её на указанной странице. Иначе: «Нет информации»."),
    "Prices in another currency are converted to {currency}.": ("Los precios en otra moneda se convierten a {currency}.",
                                                                "Цены в другой валюте пересчитываются в {currency}."),
    "{name} is searching… this can take a minute or two.": ("{name} está buscando… puede tardar uno o dos minutos.",
                                                            "{name} ищет… это может занять минуту-другую."),
    "{name} is answering… this can take a minute or two.": ("{name} está respondiendo… puede tardar uno o dos minutos.",
                                                            "{name} отвечает… это может занять минуту-другую."),
    "Found a verified price.": ("Se ha encontrado un precio verificado.", "Найдена проверенная цена."),
    "No information.": ("Sin información.", "Нет информации."),
    "No information": ("Sin información", "Нет информации"),
    "That route isn't in your settings any more": ("Esa ruta ya no está en tus ajustes", "Этого маршрута больше нет в настройках"),
    "This route has no airport codes to look up": ("Esta ruta no tiene códigos de aeropuerto que buscar",
                                                   "У этого маршрута нет кодов аэропортов для поиска"),
    "Pick the departure dates to look up": ("Elige las fechas de salida que buscar", "Выберите даты вылета для поиска"),
    "The 'until' dates must come after the 'from' dates": ("Las fechas «hasta» deben ser posteriores a las fechas «desde»",
                                                           "Даты «по» должны быть позже дат «с»"),
    "the analyst found no price that meets the rules": ("el analista no encontró ningún precio que cumpla las reglas",
                                                        "аналитик не нашёл цены, которая отвечает правилам"),
    "the answer had no usable price": ("la respuesta no tenía un precio utilizable", "в ответе не было подходящей цены"),
    "the answer was for a different route": ("la respuesta era de otra ruta", "ответ был для другого маршрута"),
    "the answer's departure date is outside your range": ("la fecha de salida de la respuesta está fuera de tu rango",
                                                          "дата вылета в ответе вне вашего диапазона"),
    "the answer's return date is outside your range": ("la fecha de vuelta de la respuesta está fuera de tu rango",
                                                       "дата возвращения в ответе вне вашего диапазона"),
    "the price wasn't recorded within the past two years": ("el precio no se registró en los últimos dos años",
                                                            "цена зафиксирована не в последние два года"),
    "the answer didn't cite a source and quote it": ("la respuesta no citaba una fuente con su texto",
                                                     "в ответе нет источника с цитатой"),
    "the quote doesn't contain the price": ("la cita no contiene el precio", "в цитате нет цены"),
    "AirFare only opens source pages on the public internet": ("AirFare solo abre páginas de fuentes en internet público",
                                                               "AirFare открывает только страницы в открытом интернете"),
    "AirFare couldn't find the quoted price on the source page": ("AirFare no encontró el precio citado en la página de la fuente",
                                                                  "AirFare не нашёл указанную цену на странице источника"),
}

_MESSAGES = {
    "paste the address of a Skyscanner search results page (https://www.skyscanner…/transport/flights/…)":
        ("pega la dirección de una página de resultados de búsqueda de Skyscanner (https://www.skyscanner…/transport/flights/…)",
         "вставьте адрес страницы с результатами поиска Skyscanner (https://www.skyscanner…/transport/flights/…)"),
    "Paste the address of a Skyscanner search results page (https://www.skyscanner…/transport/flights/…)":
        ("Pega la dirección de una página de resultados de búsqueda de Skyscanner (https://www.skyscanner…/transport/flights/…)",
         "Вставьте адрес страницы с результатами поиска Skyscanner (https://www.skyscanner…/transport/flights/…)"),
    "There's no exchange rate for {currency} yet, so your price limits can't be converted. Connect to the internet and save again.":
        ("Aún no hay tipo de cambio para {currency}, así que tus límites de precio no se pueden convertir. Conéctate a "
         "internet y vuelve a guardar.",
         "Курса для {currency} пока нет, поэтому ценовые пределы нельзя пересчитать. Подключитесь к интернету и "
         "сохраните снова."),
    "Also cheaper: {routes}": ("También más baratos: {routes}", "Также подешевели: {routes}"),
    "this link isn't a search results page on a site the extension covers":
        ("este enlace no es una página de resultados de un sitio que cubra la extensión",
         "эта ссылка не ведёт на страницу результатов поиска на сайте, который поддерживает расширение"),
    "No SerpApi key yet": ("Aún no hay clave de SerpApi", "Ключа SerpApi пока нет"),
    "No DeepSeek key yet": ("Aún no hay clave de DeepSeek", "Ключа DeepSeek пока нет"),
    "AirFare was updated. Close this tab and open AirFare Settings again.":
        ("AirFare se ha actualizado. Cierra esta pestaña y vuelve a abrir los Ajustes de AirFare.",
         "AirFare обновился. Закройте эту вкладку и снова откройте настройки AirFare."),
    "Aviasales needs 3-letter airport or city codes and dates within the coming year":
        ("Aviasales necesita códigos de aeropuerto o ciudad de 3 letras y fechas dentro del próximo año",
         "Aviasales нужны трёхбуквенные коды аэропортов или городов и даты в пределах ближайшего года"),
    "page loaded but no flight results were found": ("la página cargó, pero no se encontraron vuelos",
                                                     "страница загрузилась, но рейсы не найдены"),
    "no prices found on the page": ("no se encontraron precios en la página", "на странице не найдено цен"),
    "the AirFare extension didn't respond (is it installed and enabled on your browser's extensions page?)":
        ("la extensión de AirFare no respondió (¿está instalada y activada en la página de extensiones de tu navegador?)",
         "расширение AirFare не ответило (оно установлено и включено на странице расширений вашего браузера?)"),
    "the AirFare add-on didn't respond (Firefox removes an add-on loaded in about:debugging when it restarts: load it again, or install the signed .xpi)":
        ("el complemento de AirFare no respondió (Firefox quita un complemento cargado en about:debugging al "
         "reiniciarse: cárgalo de nuevo o instala el .xpi firmado)",
         "дополнение AirFare не ответило (Firefox удаляет дополнение, загруженное в about:debugging, при перезапуске: "
         "загрузите его снова или установите подписанный .xpi)"),
    "the AirFare extension started but didn't finish in time": ("la extensión de AirFare empezó, pero no terminó a tiempo",
                                                                "расширение AirFare начало работу, но не успело закончить"),
}

_MORE = {
    # ----- the Clean up page ------------------------------------------------------------------
    "Clean up": ("Limpieza", "Очистка"),
    "Clear out what AirFare kept from past checks.": ("Borra lo que AirFare guardó de comprobaciones anteriores.",
                                                      "Удалите то, что AirFare сохранил после прошлых проверок."),
    "Each button says how much it will delete before you press it. Settings and API keys are never touched here.":
        ("Cada botón dice cuánto borrará antes de pulsarlo. Aquí nunca se tocan los ajustes ni las claves API.",
         "Каждая кнопка заранее показывает, сколько удалит. Настройки и API-ключи здесь не затрагиваются."),
    "Every price AirFare recorded, as shown on the Price history page.":
        ("Todos los precios que AirFare registró, tal como aparecen en el Historial de precios.",
         "Все цены, записанные AirFare, как на странице «История цен»."),
    "All routes": ("Todas las rutas", "Все маршруты"),
    "Seen more than … days ago": ("Vistos hace más de … días", "Записаны более … дней назад"),
    "Only trips whose departure date has passed": ("Solo viajes cuya fecha de salida ya pasó",
                                                   "Только поездки, дата вылета которых уже прошла"),
    "Deleting price history doesn't change alerts; reset those under Alert references.":
        ("Borrar el historial de precios no cambia las alertas; restablécelas en Referencias de alertas.",
         "Удаление истории цен не меняет оповещения; сбросить их можно в разделе «Опорные цены оповещений»."),
    "No price history yet.": ("Aún no hay historial de precios.", "Истории цен пока нет."),
    "{n} record|{n} records": ("{n} registro|{n} registros", "{n} запись|{n} записи|{n} записей"),
    "{n} for a trip that already happened|{n} for trips that already happened":
        ("{n} de un viaje que ya pasó|{n} de viajes que ya pasaron",
         "{n} — по уже прошедшей поездке|{n} — по уже прошедшим поездкам|{n} — по уже прошедшим поездкам"),
    "Pick which records to delete": ("Elige qué registros borrar", "Выберите, какие записи удалить"),
    "Delete {n} record|Delete {n} records": ("Borrar {n} registro|Borrar {n} registros",
                                             "Удалить {n} запись|Удалить {n} записи|Удалить {n} записей"),
    "Delete these price records? This can't be undone.": ("¿Borrar estos registros de precios? No se puede deshacer.",
                                                          "Удалить эти записи цен? Это нельзя отменить."),
    "Routes on the dashboard. An earlier route keeps its last check on its own tab until you remove it.":
        ("Rutas en el panel. Una ruta anterior conserva su última comprobación en su propia pestaña hasta que la quites.",
         "Маршруты на панели. Прежний маршрут хранит последнюю проверку на своей вкладке, пока вы его не удалите."),
    "The dashboard is empty.": ("El panel está vacío.", "Панель пуста."),
    "in the latest check": ("en la última comprobación", "в последней проверке"),
    "earlier, checked {when}": ("anterior, comprobada el {when}", "прежний, проверен {when}"),
    "Remove {n} route from the dashboard|Remove {n} routes from the dashboard":
        ("Quitar {n} ruta del panel|Quitar {n} rutas del panel",
         "Убрать {n} маршрут с панели|Убрать {n} маршрута с панели|Убрать {n} маршрутов с панели"),
    "Remove the {n} earlier route|Remove all {n} earlier routes":
        ("Quitar la {n} ruta anterior|Quitar las {n} rutas anteriores",
         "Убрать {n} прежний маршрут|Убрать все прежние маршруты ({n})|Убрать все прежние маршруты ({n})"),
    "Something went wrong. Details are in AirFare's log.": ("Algo ha fallado. Los detalles están en el registro de AirFare.",
                                                            "Что-то пошло не так. Подробности в журнале AirFare."),
    "The Codex app isn't installed: install it from AirFare Settings, then sign in to ChatGPT":
        ("La app Codex no está instalada: instálala desde los Ajustes de AirFare e inicia sesión en ChatGPT",
         "Приложение Codex не установлено: установите его в настройках AirFare и войдите в ChatGPT"),
    "The Codex app isn't installed yet": ("La app Codex aún no está instalada", "Приложение Codex ещё не установлено"),
    "ChatGPT isn't signed in: press Log in to ChatGPT in AirFare Settings":
        ("ChatGPT no tiene la sesión iniciada: pulsa Iniciar sesión en ChatGPT en los Ajustes de AirFare",
         "Вход в ChatGPT не выполнен: нажмите «Войти в ChatGPT» в настройках AirFare"),
    "Install the Codex app with the Install the Codex app button in AirFare Settings":
        ("Instala la app Codex con el botón Instalar la app Codex de los Ajustes de AirFare",
         "Установите приложение Codex кнопкой «Установить приложение Codex» в настройках AirFare"),
    "Nothing to delete any more.": ("Ya no queda nada que borrar.", "Удалять больше нечего."),
    "{n} item will be deleted.|{n} items will be deleted.": ("Se borrará {n} elemento.|Se borrarán {n} elementos.",
                                                              "Будет удалён {n} элемент.|Будет удалено {n} элемента.|Будет удалено {n} элементов."),
    "What this would delete has changed since the page showed it. Check the numbers and try again.":
        ("Lo que se borraría ha cambiado desde que la página lo mostró. Revisa las cifras e inténtalo de nuevo.",
         "То, что будет удалено, изменилось с тех пор, как страница это показала. Проверьте цифры и попробуйте снова."),
    "Tick the routes to remove": ("Marca las rutas que quitar", "Отметьте маршруты, которые нужно убрать"),
    "No earlier routes": ("No hay rutas anteriores", "Прежних маршрутов нет"),
    "Remove these routes from the dashboard? Their price history stays.":
        ("¿Quitar estas rutas del panel? Su historial de precios se conserva.",
         "Убрать эти маршруты с панели? Их история цен сохранится."),
    "Remove every earlier route from the dashboard? Their price history stays.":
        ("¿Quitar del panel todas las rutas anteriores? Su historial de precios se conserva.",
         "Убрать с панели все прежние маршруты? Их история цен сохранится."),
    "Alert references": ("Referencias de alertas", "Опорные цены оповещений"),
    "The prices each alert kind compares with. Resetting starts every kind again from the next check's prices, as if the route were new.":
        ("Los precios con los que compara cada tipo de alerta. Al restablecerlos, cada tipo vuelve a empezar con los "
         "precios de la próxima comprobación, como si la ruta fuera nueva.",
         "Цены, с которыми сравнивается каждый вид оповещения. После сброса каждый вид начинает заново с цен "
         "следующей проверки, как для нового маршрута."),
    "Reset this route's alerts": ("Restablecer las alertas de esta ruta", "Сбросить оповещения этого маршрута"),
    "Reset every route's alerts": ("Restablecer las alertas de todas las rutas", "Сбросить оповещения всех маршрутов"),
    "Reset this route's alerts? Every kind starts again from the next check's prices.":
        ("¿Restablecer las alertas de esta ruta? Cada tipo vuelve a empezar con los precios de la próxima comprobación.",
         "Сбросить оповещения этого маршрута? Каждый вид начнёт заново с цен следующей проверки."),
    "Reset the alerts of every route? Every kind starts again from the next check's prices.":
        ("¿Restablecer las alertas de todas las rutas? Cada tipo vuelve a empezar con los precios de la próxima comprobación.",
         "Сбросить оповещения всех маршрутов? Каждый вид начнёт заново с цен следующей проверки."),
    "Pick a route": ("Elige una ruta", "Выберите маршрут"),
    "Lowest-price lookups": ("Búsquedas del precio más bajo", "Поиски самой низкой цены"),
    'Results of "Search the lowest price history" on the Price history page.':
        ("Resultados de «Buscar el precio más bajo» en el Historial de precios.",
         "Результаты «Найти самую низкую цену» на странице «История цен»."),
    "Older than … days": ("De hace más de … días", "Старше … дней"),
    "Delete {n} lookup|Delete {n} lookups": ("Borrar {n} búsqueda|Borrar {n} búsquedas",
                                             "Удалить {n} поиск|Удалить {n} поиска|Удалить {n} поисков"),
    "Delete these lookup results? This can't be undone.": ("¿Borrar estos resultados de búsqueda? No se puede deshacer.",
                                                           "Удалить эти результаты поиска? Это нельзя отменить."),
    "Check reports and log": ("Informes de comprobación y registro", "Отчёты проверок и журнал"),
    "The price document and analysis saved at each check, and AirFare's log. The latest check's reports always stay.":
        ("El documento de precios y el análisis guardados en cada comprobación, y el registro de AirFare. Los informes "
         "de la última comprobación siempre se quedan.",
         "Документ с ценами и анализ, сохраняемые при каждой проверке, и журнал AirFare. Отчёты последней проверки "
         "всегда остаются."),
    "{n} check report|{n} check reports": ("{n} informe|{n} informes", "{n} отчёт|{n} отчёта|{n} отчётов"),
    "Delete {n} report|Delete {n} reports": ("Borrar {n} informe|Borrar {n} informes",
                                             "Удалить {n} отчёт|Удалить {n} отчёта|Удалить {n} отчётов"),
    "Delete these check reports? This can't be undone.": ("¿Borrar estos informes? No se puede deshacer.",
                                                          "Удалить эти отчёты? Это нельзя отменить."),
    "Clear the log ({size})": ("Vaciar el registro ({size})", "Очистить журнал ({size})"),
    "Clear AirFare's log?": ("¿Vaciar el registro de AirFare?", "Очистить журнал AirFare?"),
    "The log is cleared.": ("El registro está vacío.", "Журнал очищен."),
    "Analyst conversations": ("Conversaciones con el analista", "Диалоги с аналитиком"),
    "Each analyst continues one conversation from check to check. Start fresh if its answers drift; your price history still reaches it.":
        ("Cada analista sigue una misma conversación de una comprobación a otra. Empieza de cero si sus respuestas se "
         "desvían; tu historial de precios le sigue llegando.",
         "Каждый аналитик ведёт один диалог от проверки к проверке. Начните заново, если ответы стали хуже; история "
         "цен по-прежнему будет ему передаваться."),
    "No conversations yet.": ("Aún no hay conversaciones.", "Диалогов пока нет."),
    "Start fresh conversations": ("Empezar conversaciones nuevas", "Начать новые диалоги"),
    "Start fresh conversations with the analysts you picked?": ("¿Empezar conversaciones nuevas con los analistas elegidos?",
                                                                "Начать новые диалоги с выбранными аналитиками?"),
    "DeepSeek and OpenAI API conversations are stored by AirFare and are deleted. Claude and ChatGPT keep their own copy in their apps.":
        ("Las conversaciones de DeepSeek y de la API de OpenAI las guarda AirFare y se borran. Claude y ChatGPT guardan "
         "su propia copia en sus apps.",
         "Диалоги DeepSeek и OpenAI API хранит AirFare, и они удаляются. Claude и ChatGPT хранят свою копию в своих "
         "приложениях."),
    "{n} conversation will start fresh at the next check.|{n} conversations will start fresh at the next check.":
        ("{n} conversación empezará de cero en la próxima comprobación.|{n} conversaciones empezarán de cero en la próxima comprobación.",
         "{n} диалог начнётся заново при следующей проверке.|{n} диалога начнутся заново при следующей проверке.|"
         "{n} диалогов начнутся заново при следующей проверке."),
    "Automatic clean-up": ("Limpieza automática", "Автоматическая очистка"),
    "After every check, AirFare removes what's older than this. Leave a field empty to keep everything.":
        ("Tras cada comprobación, AirFare quita lo que sea más antiguo que esto. Deja un campo vacío para conservarlo todo.",
         "После каждой проверки AirFare удаляет то, что старше указанного. Оставьте поле пустым, чтобы хранить всё."),
    "Keep price history for (days)": ("Conservar el historial de precios (días)", "Хранить историю цен (дней)"),
    "Keep check reports for (days)": ("Conservar los informes (días)", "Хранить отчёты проверок (дней)"),
    "Keep earlier dashboard routes for (days)": ("Conservar las rutas anteriores del panel (días)",
                                                 "Хранить прежние маршруты на панели (дней)"),
    "Save automatic clean-up": ("Guardar limpieza automática", "Сохранить автоматическую очистку"),
    "Automatic clean-up saved.": ("Limpieza automática guardada.", "Автоматическая очистка сохранена."),
    "Start over": ("Empezar de nuevo", "Начать заново"),
    "Everything AirFare learned from checks: price history, lookups, dashboard, alert references and reports.":
        ("Todo lo que AirFare aprendió de las comprobaciones: historial de precios, búsquedas, panel, referencias de "
         "alertas e informes.",
         "Всё, что AirFare узнал из проверок: история цен, поиски, панель, опорные цены оповещений и отчёты."),
    "Your routes, settings, API keys and analyst accounts stay.": ("Tus rutas, ajustes, claves API y cuentas de analista se conservan.",
                                                                   "Ваши маршруты, настройки, API-ключи и аккаунты аналитиков сохранятся."),
    "Delete all check history": ("Borrar todo el historial de comprobaciones", "Удалить всю историю проверок"),
    "Delete all check history? Price history, lookups, dashboard, alert references and reports are deleted for good. Your routes, settings and keys stay.":
        ("¿Borrar todo el historial de comprobaciones? El historial de precios, las búsquedas, el panel, las referencias "
         "de alertas y los informes se borran para siempre. Tus rutas, ajustes y claves se conservan.",
         "Удалить всю историю проверок? История цен, поиски, панель, опорные цены оповещений и отчёты будут удалены "
         "безвозвратно. Ваши маршруты, настройки и ключи сохранятся."),
    "Deleted {n} item.|Deleted {n} items.": ("Borrado {n} elemento.|Borrados {n} elementos.",
                                             "Удалён {n} элемент.|Удалено {n} элемента.|Удалено {n} элементов."),
    "Enter a number of days, like 30": ("Escribe un número de días, como 30", "Введите число дней, например 30"),
    "Unknown clean-up action": ("Acción de limpieza desconocida", "Неизвестное действие очистки"),

    # ----- dashboard tabs ------------------------------------------------------------------------
    "Routes": ("Rutas", "Маршруты"),
    "Earlier route, last checked {when}. It isn't in the latest check.":
        ("Ruta anterior, comprobada por última vez el {when}. No está en la última comprobación.",
         "Прежний маршрут, последняя проверка {when}. В последнюю проверку он не входит."),
    "Remove from the dashboard": ("Quitar del panel", "Убрать с панели"),
    "Remove {name} from the dashboard? Its price history stays.": ("¿Quitar {name} del panel? Su historial de precios se conserva.",
                                                                   "Убрать «{name}» с панели? Его история цен сохранится."),

    # ----- ChatGPT ---------------------------------------------------------------------------------
    "My ChatGPT account": ("Mi cuenta de ChatGPT", "Мой аккаунт ChatGPT"),
    "An OpenAI API key": ("Una clave API de OpenAI", "API-ключ OpenAI"),
    "Install the Codex app": ("Instalar la app Codex", "Установить приложение Codex"),
    "Log in to ChatGPT": ("Iniciar sesión en ChatGPT", "Войти в ChatGPT"),
    "Uses your ChatGPT plan (Plus, Pro, Business and the like) through OpenAI's Codex app, so checks need no API key and count against your plan's limits. Install the Codex app with OpenAI's own installer, then sign in once.":
        ("Usa tu plan de ChatGPT (Plus, Pro, Business y similares) a través de la app Codex de OpenAI, así que las "
         "comprobaciones no necesitan clave API y cuentan dentro de los límites de tu plan. Instala la app Codex con el "
         "instalador oficial de OpenAI y luego inicia sesión una vez.",
         "Использует ваш тариф ChatGPT (Plus, Pro, Business и т. п.) через приложение Codex от OpenAI: API-ключ не нужен, "
         "проверки расходуют лимиты тарифа. Установите Codex официальным установщиком OpenAI и войдите один раз."),
    "OpenAI API key": ("Clave API de OpenAI", "API-ключ OpenAI"),
    "ChatGPT model": ("Modelo de ChatGPT", "Модель ChatGPT"),
    "GPT-6.1 Terra (recommended, ~$0.04 a check)": ("GPT-6.1 Terra (recomendado, ~0,04 $ por comprobación)",
                                                    "GPT-6.1 Terra (рекомендуется, ~$0.04 за проверку)"),
    "GPT-6 Luna (cheapest, under $0.01 a check)": ("GPT-6 Luna (el más barato, menos de 0,01 $ por comprobación)",
                                                   "GPT-6 Luna (самая дешёвая, меньше $0.01 за проверку)"),
    "GPT-6.1 Sol (stronger, ~$0.07 a check)": ("GPT-6.1 Sol (más potente, ~0,07 $ por comprobación)",
                                               "GPT-6.1 Sol (сильнее, ~$0.07 за проверку)"),
    "GPT-6 Astra (most capable, ~$0.35 a check)": ("GPT-6 Astra (el más capaz, ~0,35 $ por comprobación)",
                                                   "GPT-6 Astra (самая мощная, ~$0.35 за проверку)"),
    "Key": ("Clave", "Ключ"),
    "platform.openai.com → API keys": ("platform.openai.com → API keys", "platform.openai.com → API keys"),
    "Saved. OpenAI accepts the key.": ("Guardada. OpenAI acepta la clave.", "Сохранено. OpenAI принимает ключ."),
    "The key works.": ("La clave funciona.", "Ключ работает."),
    "No OpenAI key yet": ("Aún no hay clave de OpenAI", "Ключа OpenAI пока нет"),
    "Checking the ChatGPT sign-in…": ("Comprobando la sesión de ChatGPT…", "Проверка входа в ChatGPT…"),
    "Signed in to ChatGPT.": ("Sesión iniciada en ChatGPT.", "Вход в ChatGPT выполнен."),
    "Not signed in yet. Press Log in to ChatGPT and sign in with your ChatGPT account.":
        ("Aún no has iniciado sesión. Pulsa Iniciar sesión en ChatGPT y entra con tu cuenta de ChatGPT.",
         "Вход ещё не выполнен. Нажмите «Войти в ChatGPT» и войдите в свой аккаунт ChatGPT."),
    "The Codex app isn't installed yet. Press Install the Codex app, then Log in to ChatGPT.":
        ("La app Codex aún no está instalada. Pulsa Instalar la app Codex y luego Iniciar sesión en ChatGPT.",
         "Приложение Codex ещё не установлено. Нажмите «Установить приложение Codex», затем «Войти в ChatGPT»."),
    "A ChatGPT sign-in window opened. Sign in there, then press Check again.":
        ("Se ha abierto una ventana para iniciar sesión en ChatGPT. Entra allí y luego pulsa Comprobar de nuevo.",
         "Открылось окно входа в ChatGPT. Войдите там, затем нажмите «Проверить снова»."),
    "Install OpenAI's Codex app now? A PowerShell window runs OpenAI's own installer from chatgpt.com.":
        ("¿Instalar ahora la app Codex de OpenAI? Una ventana de PowerShell ejecuta el instalador oficial de OpenAI desde chatgpt.com.",
         "Установить приложение Codex от OpenAI? В окне PowerShell запустится официальный установщик OpenAI с chatgpt.com."),
    "The Codex installer is running in its own window. When it's done, press Check again.":
        ("El instalador de Codex se ejecuta en su propia ventana. Cuando termine, pulsa Comprobar de nuevo.",
         "Установщик Codex работает в отдельном окне. Когда он закончит, нажмите «Проверить снова»."),
    "Pick Claude, ChatGPT or DeepSeek": ("Elige Claude, ChatGPT o DeepSeek", "Выберите Claude, ChatGPT или DeepSeek"),
    "Pick Claude, ChatGPT or DeepSeek as the analyst": ("Elige Claude, ChatGPT o DeepSeek como analista",
                                                        "Выберите аналитиком Claude, ChatGPT или DeepSeek"),
    "Pick a ChatGPT model from the list": ("Elige un modelo de ChatGPT de la lista", "Выберите модель ChatGPT из списка"),
    "Add your OpenAI API key, or use ChatGPT with your ChatGPT account":
        ("Añade tu clave API de OpenAI o usa ChatGPT con tu cuenta de ChatGPT",
         "Добавьте API-ключ OpenAI или используйте ChatGPT со своим аккаунтом ChatGPT"),
    "Add an OpenAI API key in AirFare Settings to use ChatGPT through the API":
        ("Añade una clave API de OpenAI en los Ajustes de AirFare para usar ChatGPT por la API",
         "Добавьте API-ключ OpenAI в настройках AirFare, чтобы использовать ChatGPT через API"),
    "Add an OpenAI API key in Settings to use ChatGPT through the API.":
        ("Añade una clave API de OpenAI en Ajustes para usar ChatGPT por la API.",
         "Добавьте API-ключ OpenAI в настройках, чтобы использовать ChatGPT через API."),
    "Install the Codex app and sign in to ChatGPT in AirFare Settings":
        ("Instala la app Codex e inicia sesión en ChatGPT en los Ajustes de AirFare",
         "Установите приложение Codex и войдите в ChatGPT в настройках AirFare"),
    "Install the Codex app and sign in to ChatGPT in Settings to use your ChatGPT account.":
        ("Instala la app Codex e inicia sesión en ChatGPT en Ajustes para usar tu cuenta de ChatGPT.",
         "Установите приложение Codex и войдите в ChatGPT в настройках, чтобы использовать свой аккаунт ChatGPT."),
}

# Passages with formatting, keyed by name.
_HTML = {
    "html:welcome": ("<strong>Bienvenido.</strong> Añade los vuelos que quieras vigilar. Usa códigos de aeropuerto (LHR, BCN) "
                     "o códigos de ciudad de Skyscanner (LOND, NYCA) y elige una fecha exacta o un rango para fechas flexibles.",
                     "<strong>Добро пожаловать.</strong> Добавьте рейсы, за которыми хотите следить. Используйте коды "
                     "аэропортов (LHR, BCN) или коды городов Skyscanner (LOND, NYCA) и выберите точную дату или диапазон "
                     "для гибких дат."),
    "html:welcome2": ("Después elige abajo tus fuentes de precios y tu analista de IA, pulsa <strong>Guardar</strong> y "
                      "<strong>Probar enlaces</strong> para ver los primeros precios. Las claves API se pueden guardar por "
                      "separado con su botón <strong>Guardar clave</strong>.",
                      "Затем выберите ниже источники цен и ИИ-аналитика, нажмите <strong>Сохранить</strong> и "
                      "<strong>Проверить ссылки</strong>, чтобы увидеть первые цены. API-ключи можно сохранить отдельно "
                      "кнопкой <strong>Сохранить ключ</strong>."),
    "html:src-sky": ("<strong>Skyscanner</strong> con la extensión de AirFare en tu navegador de siempre (Chrome, Edge, "
                     "Brave, Opera o Firefox)",
                     "<strong>Skyscanner</strong> через расширение AirFare в вашем обычном браузере (Chrome, Edge, Brave, "
                     "Opera или Firefox)"),
    "html:src-avia": ("<strong>Aviasales.ru</strong> con la misma extensión (sus precios en rublos se convierten a tu moneda)",
                      "<strong>Aviasales.ru</strong> через то же расширение (цены в рублях пересчитываются в вашу валюту)"),
    "html:src-serp": ("<strong>Google Flights</strong> con SerpApi: opcional, del todo en segundo plano, necesita una clave API gratuita",
                      "<strong>Google Flights</strong> через SerpApi: необязательно, полностью в фоне, нужен бесплатный API-ключ"),
    "html:src-browser": ("Skyscanner en un navegador aparte en segundo plano <span class=\"muted\">(la comprobación de robot "
                         "de Skyscanner suele bloquearlo)</span>",
                         "Skyscanner в отдельном фоновом браузере <span class=\"muted\">(обычно его останавливает проверка "
                         "Skyscanner на робота)</span>"),
    "html:ext1": ("En Chrome, abre <code>chrome://extensions</code>", "В Chrome откройте <code>chrome://extensions</code>"),
    "html:ext1b": ("y activa el <strong>Modo de desarrollador</strong> (arriba a la derecha).",
                   "и включите <strong>Режим разработчика</strong> (справа вверху)."),
    "html:ext2": ("Pulsa <strong>Cargar descomprimida</strong> y elige esta carpeta:",
                  "Нажмите <strong>Загрузить распакованное расширение</strong> и выберите эту папку:"),
    "html:serp-help": ("Consigue una clave gratuita en <a href=\"https://serpapi.com/users/sign_up\" target=\"_blank\" "
                       "rel=\"noopener\">serpapi.com</a> (unas 250 búsquedas al mes) y cópiala desde "
                       "<a href=\"https://serpapi.com/manage-api-key\" target=\"_blank\" rel=\"noopener\">Api Key</a>. Cada "
                       "combinación de fechas usa una búsqueda por comprobación.",
                       "Получите бесплатный ключ на <a href=\"https://serpapi.com/users/sign_up\" target=\"_blank\" "
                       "rel=\"noopener\">serpapi.com</a> (около 250 поисков в месяц) и скопируйте его на странице "
                       "<a href=\"https://serpapi.com/manage-api-key\" target=\"_blank\" rel=\"noopener\">Api Key</a>. Каждая "
                       "комбинация дат расходует один поиск за проверку."),
    "html:sched1": ("<strong>Al encender el PC</strong>", "<strong>При включении ПК</strong>"),
    "html:sched2": ("<strong>Cada pocas horas</strong> mientras el PC está encendido",
                    "<strong>Каждые несколько часов</strong>, пока ПК включён"),
    "html:sched3": ("<strong>Ambos</strong>: al encender el PC y luego cada pocas horas",
                    "<strong>Оба варианта</strong>: при включении ПК, затем каждые несколько часов"),
    "html:llm-claude": ("<strong>Claude</strong> con tu cuenta de Claude (la CLI de Claude Code incluida en AirFare)",
                        "<strong>Claude</strong> через ваш аккаунт Claude (CLI Claude Code входит в AirFare)"),
    "html:llm-deepseek": ("<strong>DeepSeek</strong> con la API de DeepSeek: necesita una clave API con saldo, más barato por comprobación",
                          "<strong>DeepSeek</strong> через API DeepSeek: нужен API-ключ с балансом, дешевле за проверку"),
    "html:ds-help": ("Crea una clave y añade saldo en <a href=\"https://platform.deepseek.com/api_keys\" target=\"_blank\" "
                     "rel=\"noopener\">platform.deepseek.com</a>. Tus rutas y precios se envían a la API de DeepSeek en cada "
                     "comprobación. Los costes del registro son estimaciones según los precios publicados por DeepSeek.",
                     "Создайте ключ и пополните баланс на <a href=\"https://platform.deepseek.com/api_keys\" target=\"_blank\" "
                     "rel=\"noopener\">platform.deepseek.com</a>. Ваши маршруты и цены отправляются в API DeepSeek при каждой "
                     "проверке. Стоимость в журнале оценивается по опубликованным ценам DeepSeek."),
    "html:llm-chatgpt": ("<strong>ChatGPT</strong> con tu cuenta de ChatGPT (la app Codex de OpenAI) o una clave API de OpenAI",
                         "<strong>ChatGPT</strong> через ваш аккаунт ChatGPT (приложение Codex от OpenAI) или API-ключ OpenAI"),
    "html:oa-help": ("Crea una clave en <a href=\"https://platform.openai.com/api-keys\" target=\"_blank\" rel=\"noopener\">"
                     "platform.openai.com</a> y añade saldo en Billing. Tus rutas y precios se envían a la API de OpenAI en cada "
                     "comprobación. Los costes del registro son estimaciones según los precios publicados por OpenAI.",
                     "Создайте ключ на <a href=\"https://platform.openai.com/api-keys\" target=\"_blank\" rel=\"noopener\">"
                     "platform.openai.com</a> и пополните баланс в разделе Billing. Ваши маршруты и цены отправляются в API "
                     "OpenAI при каждой проверке. Стоимость в журнале оценивается по опубликованным ценам OpenAI."),
    "html:no-checks": ("Aún no hay comprobaciones. Pulsa <strong>Comprobar ahora</strong> cuando tengas tus rutas guardadas.",
                       "Проверок ещё не было. Нажмите <strong>Проверить сейчас</strong>, когда маршруты будут сохранены."),
    "html:history-disk": ("Abierto desde el disco: puedes consultar, pero para borrar registros o hacer una búsqueda, abre "
                          "<strong>Historial de precios</strong> desde los Ajustes de AirFare.",
                          "Открыто с диска: просматривать можно, но чтобы удалять записи или искать, откройте "
                          "<strong>История цен</strong> из настроек AirFare."),
}

# ----- 1.4: no analyst, Claude by API key, every ECB currency, children, Edge and Brave, updates, tray, CSV -----
_V14 = {
    "A check is already running.": ("Ya hay una comprobación en marcha.", "Проверка уже идёт."),
    "Add an Anthropic API key in Settings, or switch Claude to your Claude account.":
        ("Añade una clave API de Anthropic en Ajustes, o cambia Claude a tu cuenta de Claude.",
         "Добавьте API-ключ Anthropic в настройках или переключите Claude на ваш аккаунт Claude."),
    "Add an Anthropic API key in AirFare Settings, or switch Claude to your Claude account":
        ("Añade una clave API de Anthropic en los Ajustes de AirFare, o cambia Claude a tu cuenta de Claude",
         "Добавьте API-ключ Anthropic в настройках AirFare или переключите Claude на ваш аккаунт Claude"),
    "Add your Anthropic API key, or use Claude with your Claude account":
        ("Añade tu clave API de Anthropic, o usa Claude con tu cuenta de Claude",
         "Добавьте ваш API-ключ Anthropic или используйте Claude через ваш аккаунт Claude"),
    "An Anthropic API key": ("Una clave API de Anthropic", "API-ключ Anthropic"),
    "Anthropic API key": ("Clave API de Anthropic", "API-ключ Anthropic"),
    "Anthropic doesn't accept the key.": ("Anthropic no acepta la clave.", "Anthropic не принимает ключ."),
    "Anthropic doesn't accept the saved API key: {e}": ("Anthropic no acepta la clave API guardada: {e}",
                                                        "Anthropic не принимает сохранённый API-ключ: {e}"),
    "Browser extension": ("Extensión del navegador", "Расширение браузера"),
    "Browser the extension runs in": ("Navegador en el que funciona la extensión", "Браузер, в котором работает расширение"),
    "Check for updates": ("Buscar actualizaciones", "Проверить обновления"),
    "Check prices now": ("Comprobar precios ahora", "Проверить цены сейчас"),
    "Checking prices…": ("Comprobando precios…", "Проверяю цены…"),
    "Checking…": ("Comprobando…", "Проверка…"),
    "Children's ages": ("Edades de los niños", "Возраст детей"),
    "Children's ages should be whole numbers from 0 to 15 (at most 8), like 4, 9":
        ("Las edades de los niños deben ser números enteros de 0 a 15 (8 como máximo), por ejemplo 4, 9",
         "Возраст детей — целые числа от 0 до 15 (не больше 8 детей), например 4, 9"),
    "children's ages should be whole numbers from 0 to 15 (at most 8), like 4, 9":
        ("las edades de los niños deben ser números enteros de 0 a 15 (8 como máximo), por ejemplo 4, 9",
         "возраст детей — целые числа от 0 до 15 (не больше 8 детей), например 4, 9"),
    "Copied. Paste it into the browser's address bar.": ("Copiado. Pégalo en la barra de direcciones del navegador.",
                                                         "Скопировано. Вставьте в адресную строку браузера."),
    "Export CSV": ("Exportar CSV", "Экспорт в CSV"),
    "In that browser, open": ("En ese navegador, abre", "В этом браузере откройте"),
    "Keep a AirFare icon in the notification area (check now, open the dashboard, quit)":
        ("Mantener un icono de AirFare en el área de notificación (comprobar ahora, abrir el panel, salir)",
         "Показывать значок AirFare в области уведомлений (проверить сейчас, открыть панель, выйти)"),
    "Look for a newer AirFare when Settings opens (one anonymous request to github.com, at most once a day)":
        ("Buscar una versión más nueva de AirFare al abrir Ajustes (una petición anónima a github.com, como mucho una vez al día)",
         "Искать новую версию AirFare при открытии настроек (один анонимный запрос к github.com, не чаще раза в день)"),
    "My Claude account": ("Mi cuenta de Claude", "Мой аккаунт Claude"),
    "Needs an analyst: with \"No analyst\" this kind never alerts.":
        ("Necesita un analista: con «Sin analista» este tipo nunca avisa.",
         "Нужен аналитик: при варианте «Без аналитика» этот тип не срабатывает."),
    "Next around {when}.": ("Siguiente hacia las {when}.", "Следующая около {when}."),
    "No Anthropic key yet": ("Aún no hay clave de Anthropic", "Ключа Anthropic пока нет"),
    "No analyst is set up: AirFare picked the cheapest and fastest flights by its own rules. Choose an analyst in Settings for best-value picks and advice.":
        ("No hay analista configurado: AirFare eligió los vuelos más baratos y más rápidos con sus propias reglas. Elige un analista en Ajustes para la mejor opción y consejos.",
         "Аналитик не настроен: AirFare выбрал самые дешёвые и быстрые рейсы по своим правилам. Выберите аналитика в настройках, чтобы получать лучший вариант и советы."),
    "No analyst: AirFare's own rules pick the flights.": ("Sin analista: las reglas de AirFare eligen los vuelos.",
                                                          "Без аналитика: рейсы выбирают правила AirFare."),
    "No checks yet.": ("Aún no hay comprobaciones.", "Проверок ещё не было."),
    "Not checked yet.": ("Aún no se ha comprobado.", "Ещё не проверялось."),
    "Other": ("Otra", "Другая"),
    "Other currency": ("Otra moneda", "Другая валюта"),
    "Pick Chrome, Edge, Brave, Opera or Firefox for the extension":
        ("Elige Chrome, Edge, Brave, Opera o Firefox para la extensión",
         "Выберите для расширения Chrome, Edge, Brave, Opera или Firefox"),
    "Pick Claude, ChatGPT, DeepSeek or no analyst": ("Elige Claude, ChatGPT, DeepSeek o sin analista",
                                                      "Выберите Claude, ChatGPT, DeepSeek или вариант без аналитика"),
    "Pick your Claude account or an Anthropic API key": ("Elige tu cuenta de Claude o una clave API de Anthropic",
                                                          "Выберите ваш аккаунт Claude или API-ключ Anthropic"),
    "Quit AirFare": ("Salir de AirFare", "Выйти из AirFare"),
    "Saved. Anthropic accepts the key.": ("Guardada. Anthropic acepta la clave.", "Сохранено. Anthropic принимает ключ."),
    "AirFare is running.": ("AirFare está en marcha.", "AirFare работает."),
    "AirFare {version}.": ("AirFare {version}.", "AirFare {version}."),
    "That's it. AirFare opens your Skyscanner and Aviasales pages in a minimized browser window and closes only those tabs when it's done. If a site asks for a robot check, the window comes up so you can solve it.":
        ("Eso es todo. AirFare abre tus páginas de Skyscanner y Aviasales en una ventana minimizada del navegador y, al terminar, cierra solo esas pestañas. Si un sitio pide una verificación de robot, la ventana aparece para que la resuelvas.",
         "Готово. AirFare открывает страницы Skyscanner и Aviasales в свёрнутом окне браузера и по окончании закрывает только эти вкладки. Если сайт попросит проверку на робота, окно появится, чтобы вы её прошли."),
    "The browser is still running an older copy of the extension (v{old}; this AirFare has v{new}). Open its extensions page and click the reload arrow on AirFare collector, or restart the browser.":
        ("El navegador sigue usando una copia antigua de la extensión (v{old}; este AirFare tiene la v{new}). Abre su página de extensiones y pulsa la flecha de recarga en AirFare collector, o reinicia el navegador.",
         "В браузере всё ещё старая копия расширения (v{old}; в этом AirFare v{new}). Откройте страницу расширений и нажмите стрелку перезагрузки у AirFare collector или перезапустите браузер."),
    "The icon appears once the checker restarts, a minute after you save.":
        ("El icono aparece cuando el comprobador se reinicia, un minuto después de guardar.",
         "Значок появится после перезапуска фонового процесса, через минуту после сохранения."),
    "The icon needs the pystray and Pillow packages, which this AirFare doesn't have. Run install.ps1 again to add them.":
        ("El icono necesita los paquetes pystray y Pillow, que este AirFare no tiene. Ejecuta install.ps1 otra vez para añadirlos.",
         "Для значка нужны пакеты pystray и Pillow, которых в этом AirFare нет. Запустите install.ps1 ещё раз, чтобы их добавить."),
    "The last update check failed: {error}": ("La última búsqueda de actualizaciones falló: {error}",
                                              "Последняя проверка обновлений не удалась: {error}"),
    "Type {page} into the browser's address bar.": ("Escribe {page} en la barra de direcciones del navegador.",
                                                    "Введите {page} в адресную строку браузера."),
    "Up to date (checked {when}).": ("Actualizado (comprobado el {when}).", "Актуальная версия (проверено {when})."),
    "Update checks aren't set up for this copy of AirFare.":
        ("Esta copia de AirFare no tiene configurada la búsqueda de actualizaciones.",
         "В этой копии AirFare проверка обновлений не настроена."),
    "Updates": ("Actualizaciones", "Обновления"),
    "Uses your Claude subscription through the Claude Code CLI bundled with AirFare. Sign in once; checks count against your plan's limits.":
        ("Usa tu suscripción a Claude mediante la CLI de Claude Code incluida en AirFare. Inicia sesión una vez; las comprobaciones cuentan para los límites de tu plan.",
         "Использует вашу подписку Claude через CLI Claude Code, входящую в AirFare. Войдите один раз; проверки учитываются в лимитах вашего плана."),
    "Version {latest} is available on GitHub.": ("La versión {latest} está disponible en GitHub.",
                                                 "На GitHub доступна версия {latest}."),
    "Without an analyst, AirFare still records every price, alerts on the cheapest and fastest fares and draws the dashboard. The best-value pick, the analysis text and the lowest-price lookups need an analyst.":
        ("Sin analista, AirFare sigue registrando todos los precios, avisa de las tarifas más baratas y más rápidas y dibuja el panel. La mejor opción, el texto del análisis y las búsquedas del precio mínimo necesitan un analista.",
         "Без аналитика AirFare по-прежнему записывает все цены, сообщает о самых дешёвых и быстрых тарифах и строит панель. Лучший вариант, текст анализа и поиск минимальной цены требуют аналитика."),
    "console.anthropic.com → API keys": ("console.anthropic.com → API keys", "console.anthropic.com → API keys"),
    "none, or e.g. 4, 9": ("ninguno, o p. ej. 4, 9", "нет, или например 4, 9"),
    "{browser} (not installed)": ("{browser} (no instalado)", "{browser} (не установлен)"),
    "{n} child|{n} children": ("{n} niño|{n} niños", "{n} ребёнок|{n} ребёнка|{n} детей"),
    "html:llm-none": ("<strong>Sin analista</strong>: las reglas de AirFare eligen los vuelos más baratos y más rápidos. No hace falta ninguna cuenta de IA; los avisos de mejor opción quedan desactivados.",
                      "<strong>Без аналитика</strong>: правила AirFare выбирают самые дешёвые и быстрые рейсы. Аккаунт ИИ не нужен; оповещения о лучшем варианте отключены."),
    "html:an-help": ("Crea una clave en <a href=\"https://console.anthropic.com/settings/keys\" target=\"_blank\" rel=\"noopener\">"
                     "console.anthropic.com</a> y añade saldo en Billing. Tus rutas y precios se envían a la API de Anthropic en cada "
                     "comprobación, con cargo a esa clave.",
                     "Создайте ключ на <a href=\"https://console.anthropic.com/settings/keys\" target=\"_blank\" rel=\"noopener\">"
                     "console.anthropic.com</a> и пополните баланс в разделе Billing. Ваши маршруты и цены отправляются в API "
                     "Anthropic при каждой проверке и оплачиваются с этого ключа."),
}

# ----- the public release: opt-in sources, the providers' terms, the Codex app installed by the user, notices -----
_PUBLIC = {
    "Skyscanner and Aviasales are read through your own browser, page by page. Their terms of use don't allow automated visits, so tick them only if that is acceptable to you; keep the page count small and never pass the data on. Google Flights through SerpApi is an API you pay for with your own key.":
        ("Skyscanner y Aviasales se leen con tu propio navegador, página a página. Sus condiciones de uso no permiten visitas automatizadas, así que márcalos solo si te parece aceptable; usa pocas páginas y nunca cedas los datos a terceros. Google Flights con SerpApi es una API que pagas con tu propia clave.",
         "Skyscanner и Aviasales читаются через ваш собственный браузер, страница за страницей. Их условия использования не допускают автоматических посещений, поэтому отмечайте их, только если вас это устраивает; держите число страниц небольшим и никому не передавайте данные. Google Flights через SerpApi — это API, который вы оплачиваете своим ключом."),
    "Uses your Claude subscription through the Claude Code CLI bundled with AirFare. Anthropic's terms are written for your own use of Claude Code; using a subscription from another program is your responsibility. The API key is the path meant for a tool like this.":
        ("Usa tu suscripción a Claude mediante la CLI de Claude Code incluida en AirFare. Las condiciones de Anthropic están pensadas para tu propio uso de Claude Code; usar la suscripción desde otro programa queda bajo tu responsabilidad. La clave API es la vía prevista para una herramienta como esta.",
         "Использует вашу подписку Claude через CLI Claude Code, входящую в AirFare. Условия Anthropic написаны для вашего собственного использования Claude Code; использование подписки из другой программы остаётся на вашей ответственности. API-ключ — предусмотренный путь для такой программы."),
    "Uses your ChatGPT plan (Plus, Pro, Business and the like) through OpenAI's Codex app, so checks need no API key and count against your plan's limits. Check OpenAI's terms for using a ChatGPT plan through Codex from another program.":
        ("Usa tu plan de ChatGPT (Plus, Pro, Business y similares) mediante la app Codex de OpenAI, así que las comprobaciones no necesitan clave API y cuentan para los límites de tu plan. Consulta las condiciones de OpenAI sobre usar un plan de ChatGPT con Codex desde otro programa.",
         "Использует ваш тариф ChatGPT (Plus, Pro, Business и подобные) через приложение Codex от OpenAI, поэтому проверкам не нужен API-ключ, и они учитываются в лимитах тарифа. Проверьте условия OpenAI об использовании тарифа ChatGPT через Codex из другой программы."),
    "html:codex-install": ("Instala primero la app Codex tú mismo, con el instalador oficial de OpenAI: abre PowerShell y ejecuta <code>irm https://chatgpt.com/codex/install.ps1 | iex</code> (ver <a href=\"https://developers.openai.com/codex\" target=\"_blank\" rel=\"noopener\">developers.openai.com/codex</a>); luego pulsa <strong>Iniciar sesión en ChatGPT</strong> e inicia sesión una vez.",
                           "Сначала установите приложение Codex сами, официальным установщиком OpenAI: откройте PowerShell и выполните <code>irm https://chatgpt.com/codex/install.ps1 | iex</code> (см. <a href=\"https://developers.openai.com/codex\" target=\"_blank\" rel=\"noopener\">developers.openai.com/codex</a>), затем нажмите <strong>Войти в ChatGPT</strong> и войдите один раз."),
    "The Codex app isn't installed yet. Install it with OpenAI's installer (see below), then press Check again.":
        ("La app Codex aún no está instalada. Instálala con el instalador de OpenAI (ver abajo) y luego pulsa Comprobar de nuevo.",
         "Приложение Codex ещё не установлено. Установите его установщиком OpenAI (см. ниже), затем нажмите Проверить снова."),
    "The Codex app isn't installed: install it with OpenAI's installer, then sign in to ChatGPT":
        ("La app Codex no está instalada: instálala con el instalador de OpenAI y luego inicia sesión en ChatGPT",
         "Приложение Codex не установлено: установите его установщиком OpenAI, затем войдите в ChatGPT"),
    "Install the Codex app with OpenAI's own installer, not npm, as AirFare Settings explains":
        ("Instala la app Codex con el instalador oficial de OpenAI, no con npm, como explican los Ajustes de AirFare",
         "Установите приложение Codex официальным установщиком OpenAI, а не через npm, как объясняют настройки AirFare"),
    "AirFare is an independent, open-source tool. It is not affiliated with or endorsed by Skyscanner, Aviasales, Google, Anthropic, OpenAI, DeepSeek or SerpApi; their names are trademarks of their owners, used only to say which service is meant. Prices can be wrong or out of date: check them on the site before you book.":
        ("AirFare es una herramienta independiente y de código abierto. No está afiliada a Skyscanner, Aviasales, Google, Anthropic, OpenAI, DeepSeek ni SerpApi, ni cuenta con su respaldo; sus nombres son marcas de sus propietarios y se usan solo para indicar de qué servicio se trata. Los precios pueden ser erróneos o estar desactualizados: compruébalos en el sitio antes de reservar.",
         "AirFare — независимая программа с открытым исходным кодом. Она не связана со Skyscanner, Aviasales, Google, Anthropic, OpenAI, DeepSeek или SerpApi и не одобрена ими; их названия — товарные знаки владельцев и используются только для указания сервиса. Цены могут быть неверными или устаревшими: проверяйте их на сайте перед бронированием."),
}

# The extension in Opera and Firefox. Firefox's own buttons as its Spanish and Russian versions name them;
# addons.mozilla.org's in English, as its developer pages show them.
_FIREFOX = {
    "html:ext2-firefox": ("Pulsa <strong>Cargar complemento temporal…</strong> y elige el archivo <code>manifest.json</code> "
                          "de esta carpeta:",
                          "Нажмите <strong>Загрузить временное дополнение…</strong> и выберите файл "
                          "<code>manifest.json</code> в этой папке:"),
    "Firefox removes a temporary add-on when it restarts. To keep it, sign it once at addons.mozilla.org (free, and not listed in the store) and install the signed file.":
        ("Firefox quita los complementos temporales al reiniciarse. Para conservarlo, fírmalo una vez en "
         "addons.mozilla.org (gratis y sin publicarlo en la tienda) e instala el archivo firmado.",
         "Firefox удаляет временные дополнения при перезапуске. Чтобы дополнение осталось, один раз подпишите его на "
         "addons.mozilla.org (бесплатно, без публикации в каталоге) и установите подписанный файл."),
    "How to sign it": ("Cómo firmarlo", "Как его подписать"),
    "html:amo1": ("Inicia sesión en <a href=\"https://addons.mozilla.org/developers/\" target=\"_blank\" rel=\"noopener\">"
                  "addons.mozilla.org/developers</a> con una cuenta de Mozilla y acepta el acuerdo para desarrolladores.",
                  "Войдите на <a href=\"https://addons.mozilla.org/developers/\" target=\"_blank\" rel=\"noopener\">"
                  "addons.mozilla.org/developers</a> с аккаунтом Mozilla и примите соглашение для разработчиков."),
    "html:amo2": ("En PowerShell, en la carpeta de AirFare, prepara lo que vas a subir con un id de complemento propio "
                  "(parece una dirección de correo; nadie más puede haberlo firmado): <code>.venv\\Scripts\\python "
                  "tools\\make_firefox.py --zip --id airfare-collector@tunombre.example</code>. Crea "
                  "<code>dist\\airfare-firefox-&lt;versión&gt;.zip</code>.",
                  "В PowerShell, в папке AirFare, создайте архив для загрузки со своим идентификатором дополнения (он "
                  "похож на адрес почты; никто другой не должен был его подписать): <code>.venv\\Scripts\\python "
                  "tools\\make_firefox.py --zip --id airfare-collector@vashe-imya.example</code>. Появится "
                  "<code>dist\\airfare-firefox-&lt;версия&gt;.zip</code>."),
    "html:amo3": ("Pulsa <strong>Submit a New Add-on</strong>, elige <strong>On your own</strong>, sube el zip, marca solo "
                  "<strong>Firefox</strong> y continúa. Responde <strong>No</strong> a la pregunta sobre el código fuente "
                  "y envíalo.",
                  "Нажмите <strong>Submit a New Add-on</strong>, выберите <strong>On your own</strong>, загрузите zip, "
                  "отметьте только <strong>Firefox</strong> и продолжите. На вопрос об исходном коде ответьте "
                  "<strong>No</strong> и отправьте."),
    "html:amo4": ("Cuando llegue el correo de que está firmado (suele tardar unos minutos), abre el complemento en "
                  "<strong>My Add-ons</strong>, luego la versión, y descarga el archivo <code>.xpi</code> firmado.",
                  "Когда придёт письмо о подписи (обычно через несколько минут), откройте дополнение в "
                  "<strong>My Add-ons</strong>, затем версию, и скачайте подписанный файл <code>.xpi</code>."),
    "html:amo5": ("En Firefox, abre <code>about:addons</code>, pulsa el engranaje, elige <strong>Instalar complemento desde "
                  "archivo…</strong>, selecciona el <code>.xpi</code> y pulsa <strong>Añadir</strong>.",
                  "В Firefox откройте <code>about:addons</code>, нажмите на шестерёнку, выберите <strong>Установить "
                  "дополнение из файла…</strong>, укажите <code>.xpi</code> и нажмите <strong>Добавить</strong>."),
    "When AirFare brings a new version of the add-on, sign it the same way with the same id, under Upload New Version on the add-on's page.":
        ("Cuando AirFare traiga una versión nueva del complemento, fírmala igual y con el mismo id, en Upload New "
         "Version en la página del complemento.",
         "Когда в AirFare появится новая версия дополнения, подпишите её так же и с тем же идентификатором — через "
         "Upload New Version на странице дополнения."),
    "Firefox is still running an older copy of the add-on (v{old}; this AirFare has v{new}). Load it again in about:debugging, or sign and install the new version.":
        ("Firefox sigue usando una copia antigua del complemento (v{old}; este AirFare tiene la v{new}). Cárgalo de "
         "nuevo en about:debugging, o firma e instala la versión nueva.",
         "В Firefox всё ещё старая копия дополнения (v{old}; в этом AirFare v{new}). Загрузите его снова в "
         "about:debugging или подпишите и установите новую версию."),
}

# ----- messages added by the 2026-10-27 review ---------------------------------------------------------------
_REVIEW = {
    "This route uses the city code {code}, which AirFare can't map to airports; the lookup needs 3-letter airport codes":
        ("Esta ruta usa el código de ciudad {code}, que AirFare no puede convertir en aeropuertos; la búsqueda necesita "
         "códigos de aeropuerto de 3 letras",
         "В этом маршруте код города {code}, который AirFare не может сопоставить аэропортам; для поиска нужны "
         "трёхбуквенные коды аэропортов"),
}

# ----- limits on the browser sources (limits.py) ---------------------------------------------------------------
_LIMITS = {
    "Limits": ("Límites", "Лимиты"),
    "Personal": ("Personal", "Личный"),
    "Extended": ("Ampliado", "Расширенный"),
    "{level}: at most {pages} Skyscanner and Aviasales pages per check and {day} a day; automatic checks open them at most once every {hours} hours. Google Flights (SerpApi) isn't limited.":
        ("{level}: como máximo {pages} páginas de Skyscanner y Aviasales por comprobación y {day} al día; las "
         "comprobaciones automáticas las abren como mucho una vez cada {hours} horas. Google Flights (SerpApi) no "
         "tiene límite.",
         "{level}: не больше {pages} страниц Skyscanner и Aviasales за проверку и {day} в день; автоматические "
         "проверки открывают их не чаще одного раза в {hours} ч. Google Flights (SerpApi) не ограничен."),
    "Extended limits load more pages from Skyscanner and Aviasales. Their terms don't allow automated visits, and more pages mean more robot checks or a blocked browser. Use it only for your own trips, at your own risk.":
        ("Los límites ampliados cargan más páginas de Skyscanner y Aviasales. Sus condiciones no permiten visitas "
         "automatizadas, y más páginas significan más comprobaciones de robot o un navegador bloqueado. Úsalos solo "
         "para tus propios viajes y bajo tu propia responsabilidad.",
         "Расширенные лимиты загружают больше страниц Skyscanner и Aviasales. Их условия использования не допускают "
         "автоматических посещений, а чем больше страниц, тем больше проверок на робота или риск блокировки "
         "браузера. Используйте их только для своих поездок и на свой страх и риск."),
    "Skyscanner and Aviasales: {n} more page is over the limits for one check and will be left out.|Skyscanner and Aviasales: {n} more pages are over the limits for one check and will be left out.":
        ("Skyscanner y Aviasales: {n} página más supera los límites de una comprobación y se dejará fuera.|"
         "Skyscanner y Aviasales: {n} páginas más superan los límites de una comprobación y se dejarán fuera.",
         "Skyscanner и Aviasales: ещё {n} страница сверх лимита одной проверки и будет пропущена.|"
         "Skyscanner и Aviasales: ещё {n} страницы сверх лимита одной проверки и будут пропущены.|"
         "Skyscanner и Aviasales: ещё {n} страниц сверх лимита одной проверки и будут пропущены."),
    "Pick Personal or Extended limits": ("Elige los límites Personal o Ampliado", "Выберите лимиты: «Личный» или «Расширенный»"),
    "Confirm the warning about Extended limits first":
        ("Primero confirma el aviso sobre los límites ampliados", "Сначала подтвердите предупреждение о расширенных лимитах"),
    "Nothing was checked: the limits hold Skyscanner and Aviasales for now.":
        ("No se ha comprobado nada: los límites retienen Skyscanner y Aviasales por ahora.",
         "Ничего не проверено: лимиты пока не позволяют открыть Skyscanner и Aviasales."),
    "Skyscanner and Aviasales were skipped this time: with the {level} limits, automatic checks open their pages at most once every {hours} hours.":
        ("Esta vez se han omitido Skyscanner y Aviasales: con el nivel {level}, las comprobaciones automáticas abren "
         "sus páginas como mucho una vez cada {hours} horas.",
         "В этот раз Skyscanner и Aviasales пропущены: с лимитами уровня «{level}» автоматические проверки открывают "
         "их страницы не чаще одного раза в {hours} ч."),
    "{n} Skyscanner or Aviasales page waits until tomorrow: the {level} limits allow {max} a day.|{n} Skyscanner and Aviasales pages wait until tomorrow: the {level} limits allow {max} a day.":
        ("{n} página de Skyscanner o Aviasales espera hasta mañana: el nivel {level} permite {max} al día.|"
         "{n} páginas de Skyscanner y Aviasales esperan hasta mañana: el nivel {level} permite {max} al día.",
         "{n} страница Skyscanner или Aviasales ждёт до завтра: лимиты уровня «{level}» разрешают {max} в день.|"
         "{n} страницы Skyscanner и Aviasales ждут до завтра: лимиты уровня «{level}» разрешают {max} в день.|"
         "{n} страниц Skyscanner и Aviasales ждут до завтра: лимиты уровня «{level}» разрешают {max} в день."),
    "{n} Skyscanner or Aviasales page was left out: the {level} limits allow {max} per check.|{n} Skyscanner and Aviasales pages were left out: the {level} limits allow {max} per check.":
        ("Se ha dejado fuera {n} página de Skyscanner o Aviasales: el nivel {level} permite {max} por comprobación.|"
         "Se han dejado fuera {n} páginas de Skyscanner y Aviasales: el nivel {level} permite {max} por comprobación.",
         "{n} страница Skyscanner или Aviasales пропущена: лимиты уровня «{level}» разрешают {max} за проверку.|"
         "{n} страницы Skyscanner и Aviasales пропущены: лимиты уровня «{level}» разрешают {max} за проверку.|"
         "{n} страниц Skyscanner и Aviasales пропущено: лимиты уровня «{level}» разрешают {max} за проверку."),
}

# ----- 1.5.0: updates that never lose data ------------------------------------------------------------------
_UPDATES = {
    "Backups before updates": ("Copias antes de actualizar", "Резервные копии перед обновлениями"),
    "Before an update changes your data, AirFare copies it here. The newest 3 are kept, and Start over leaves them alone.":
        ("Antes de que una actualización cambie tus datos, AirFare los copia aquí. Se guardan las 3 más recientes, "
         "y Empezar de nuevo no las toca.",
         "Перед тем как обновление изменит ваши данные, AirFare копирует их сюда. Хранятся 3 последние копии, "
         "и «Начать заново» их не трогает."),
    "AirFare {version}, saved {when}": ("AirFare {version}, guardada el {when}", "AirFare {version}, сохранена {when}"),
    "No backups yet.": ("Aún no hay copias.", "Резервных копий пока нет."),
    "Tick the backups to delete": ("Marca las copias que borrar", "Отметьте копии, которые нужно удалить"),
    "Delete {n} backup|Delete {n} backups": ("Borrar {n} copia|Borrar {n} copias",
                                             "Удалить {n} копию|Удалить {n} копии|Удалить {n} копий"),
    "Delete every backup": ("Borrar todas las copias", "Удалить все копии"),
    "Delete these backups? AirFare can't go back to them afterwards.":
        ("¿Borrar estas copias? Después AirFare no podrá volver a ellas.",
         "Удалить эти копии? Потом AirFare не сможет к ним вернуться."),
    "Delete every backup? AirFare can't go back to them afterwards.":
        ("¿Borrar todas las copias? Después AirFare no podrá volver a ellas.",
         "Удалить все копии? Потом AirFare не сможет к ним вернуться."),
    "To go back to a backup, close AirFare and copy the files in it into the data folder.":
        ("Para volver a una copia, cierra AirFare y copia sus archivos en la carpeta data.",
         "Чтобы вернуться к копии, закройте AirFare и скопируйте её файлы в папку data."),
    "Pick the backups to delete": ("Elige las copias que borrar", "Выберите копии для удаления"),
    "Deleted {n} backup.|Deleted {n} backups.": ("Borrada {n} copia.|Borradas {n} copias.",
                                                 "Удалена {n} копия.|Удалено {n} копии.|Удалено {n} копий."),
    "This data was written by AirFare {version}; install that version or newer":
        ("Estos datos los escribió AirFare {version}; instala esa versión o una más nueva",
         "Эти данные записал AirFare {version}; установите эту версию или более новую"),
    "Quit AirFare: tray icon → Quit AirFare.": ("Cierra AirFare: icono de la bandeja → Salir de AirFare.",
                                                "Закройте AirFare: значок в трее → «Выйти из AirFare»."),
    "Download AirFare.zip from the release page.": ("Descarga AirFare.zip desde la página de la versión.",
                                                    "Скачайте AirFare.zip со страницы выпуска."),
    "Unzip it into this same folder, {folder}, and choose to replace the files. Never into a new folder: your data stays in this one.":
        ("Descomprímelo en esta misma carpeta, {folder}, y elige reemplazar los archivos. Nunca en una carpeta "
         "nueva: tus datos se quedan en esta.",
         "Распакуйте его в эту же папку, {folder}, и выберите замену файлов. Не в новую папку: ваши данные "
         "остаются в этой."),
    "Double-click AirFare.exe. It backs up your data and finishes the update.":
        ("Haz doble clic en AirFare.exe. Hace una copia de tus datos y termina la actualización.",
         "Дважды щёлкните AirFare.exe. Он сделает резервную копию данных и завершит обновление."),
    "Run sh install.sh in this folder. It backs up your data and finishes the update.":
        ("Ejecuta sh install.sh en esta carpeta. Hace una copia de tus datos y termina la actualización.",
         "Запустите sh install.sh в этой папке. Он сделает резервную копию данных и завершит обновление."),
    "If Settings then says the browser runs an older extension, reload it (Firefox: sign and install the new .xpi).":
        ("Si después Ajustes dice que el navegador usa una extensión anterior, recárgala (Firefox: firma e instala "
         "el nuevo .xpi).",
         "Если затем Настройки сообщат, что браузер использует старую версию расширения, перезагрузите её "
         "(Firefox: подпишите и установите новый .xpi)."),
}

T: dict[str, dict] = {k: {"es": es, "ru": ru} for k, (es, ru) in
                      {**_PAIRS, **_MESSAGES, **_MORE, **_HTML, **_V14, **_PUBLIC, **_FIREFOX, **_REVIEW,
                       **_LIMITS, **_UPDATES}.items()}
