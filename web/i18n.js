/* Язык приложения: русский, украинский, английский.
   Интерфейс переводится после каждой отрисовки: тексты кнопок, заголовков и подсказок.
   Уроки, промпты, скиллы и другие материалы остаются на русском. */
(function () {
  "use strict";

  // Русская фраза → [украинский, английский]
  var D = {
    // Навигация и общее
    "Главная": ["Головна", "Home"], "Категории": ["Категорії", "Categories"], "Профиль": ["Профіль", "Profile"],
    "Разделы": ["Розділи", "Sections"], "Назад": ["Назад", "Back"], "Открыть": ["Відкрити", "Open"],
    "Читать": ["Читати", "Read"], "Перечитать": ["Перечитати", "Read again"], "Что внутри": ["Що всередині", "What's inside"],
    "Начать": ["Почати", "Start"], "Все": ["Усі", "All"], "Бесплатные": ["Безкоштовні", "Free"],
    "Переслать": ["Переслати", "Share"], "Скопировать": ["Скопіювати", "Copy"], "Отметить пройденным": ["Позначити пройденим", "Mark as done"],
    "Пройдено": ["Пройдено", "Done"], "Для резидентов": ["Для резидентів", "For residents"], "Закрыто": ["Закрито", "Locked"],
    "Бесплатно": ["Безкоштовно", "Free"], "бесплатно": ["безкоштовно", "free"], "Открыто": ["Відкрито", "Open"],
    "часть закрыта": ["частина закрита", "partly locked"], "по заявке": ["за заявкою", "by request"],
    "Скоро откроется": ["Скоро відкриється", "Opening soon"], "Сохранить": ["Зберегти", "Save"], "Удалить": ["Видалити", "Delete"],
    "Профиль": ["Профіль", "Profile"], "Поддержка": ["Підтримка", "Support"],

    // Главная
    "Сообщество C&C": ["Спільнота C&C", "C&C Community"],
    "Сайты, боты и первые клиенты вместе с нейросетями": ["Сайти, боти й перші клієнти разом із нейромережами", "Websites, bots and first clients with AI"],
    "Закрытое сообщество": ["Закрита спільнота", "Private community"],
    "Количество мест ограничено": ["Кількість місць обмежена", "Limited spots"],
    "Начать с первого урока": ["Почати з першого уроку", "Start with the first lesson"],
    "Продолжить курс": ["Продовжити курс", "Continue the course"],
    "Свежее в C&C": ["Нове в C&C", "Fresh in C&C"],
    "Навигация": ["Навігація", "Navigation"], "С чего начать, по шагам": ["З чого почати, крок за кроком", "Where to start, step by step"],
    "Курс с нуля": ["Курс з нуля", "Course from scratch"],
    "Навигация, для новичков": ["Навігація, для новачків", "Navigation, for beginners"],
    "Ты здесь впервые? Начни отсюда": ["Ти тут уперше? Почни звідси", "New here? Start here"],
    "Открыть навигацию": ["Відкрити навігацію", "Open navigation"],
    "Курс, бесплатно": ["Курс, безкоштовно", "Course, free"], "Курс, для резидентов": ["Курс, для резидентів", "Course, for residents"],
    "Подборка": ["Добірка", "Collection"], "Подборка, для резидентов": ["Добірка, для резидентів", "Collection, for residents"],
    "Чат резидентов": ["Чат резидентів", "Residents' chat"], "Оценка работ": ["Оцінка робіт", "Work review"],
    "Курс": ["Курс", "Course"], "Парсер": ["Парсер", "Parser"], "Скиллы": ["Скіли", "Skills"], "Плагины": ["Плагіни", "Plugins"],
    "Промпты": ["Промпти", "Prompts"], "Марафон": ["Марафон", "Marathon"], "AI-офис": ["AI-офіс", "AI office"],
    "Материалы": ["Матеріали", "Materials"], "Ресурсы": ["Ресурси", "Resources"],

    // Категории
    "Курс, инструменты и материалы C&C": ["Курс, інструменти й матеріали C&C", "C&C course, tools and materials"],
    "Навигация для новичков": ["Навігація для новачків", "Navigation for beginners"],
    "FreeBot-марафон": ["FreeBot-марафон", "FreeBot marathon"],
    "Первый сайт, бот или дашборд за 1–2 дня. Бесплатно": ["Перший сайт, бот або дашборд за 1–2 дні. Безкоштовно", "First website, bot or dashboard in 1–2 days. Free"],
    "Клиенты с карт по нише и городу, скрипты для переписки": ["Клієнти з мап за нішею та містом, скрипти для листування", "Clients from maps by niche and city, outreach scripts"],
    "Пришли сайт, команда разберёт": ["Надішли сайт, команда розбере", "Send a site, the team will review it"],
    "Первый заказ за 7 дней, бесплатно": ["Перше замовлення за 7 днів, безкоштовно", "First order in 7 days, free"],
    "Референсы, шрифты, иконки": ["Референси, шрифти, іконки", "References, fonts, icons"],
    "Помогаем друг другу, общаемся и делимся результатами": ["Допомагаємо одне одному, спілкуємося й ділимося результатами", "We help each other, talk and share results"],

    // Навигация
    "С чего начать, если ты здесь впервые. Иди по ступенькам сверху вниз": ["З чого почати, якщо ти тут уперше. Іди сходинками згори вниз", "Where to start if you're new. Go step by step from the top"],
    "Твой путь в C&C": ["Твій шлях у C&C", "Your path in C&C"], "следующий шаг": ["наступний крок", "next step"],
    "Ты здесь": ["Ти тут", "You are here"],
    "C&C Family — закрытое сообщество про вайбкодинг. Учишься делать сайты и ботов вместе с нейросетями и продаёшь их местному бизнесу. Код пишет нейросеть, ты ставишь задачу и проверяешь.":
      ["C&C Family — закрита спільнота про вайбкодинг. Вчишся робити сайти й ботів разом із нейромережами та продаєш їх місцевому бізнесу. Код пише нейромережа, ти ставиш задачу й перевіряєш.",
       "C&C Family is a private vibe-coding community. You learn to build websites and bots with AI and sell them to local businesses. The AI writes the code; you set the task and check the result."],
    "Пройди FreeBot-марафон": ["Пройди FreeBot-марафон", "Take the FreeBot marathon"],
    "1–2 дня, бесплатно: ставишь VPN и Claude или Codex, выбираешь сайт, бота или дашборд и делаешь первый проект по готовому промпту.":
      ["1–2 дні, безкоштовно: ставиш VPN і Claude або Codex, обираєш сайт, бота чи дашборд і робиш перший проєкт за готовим промптом.",
       "1–2 days, free: install a VPN and Claude or Codex, pick a website, bot or dashboard and build your first project from a ready prompt."],
    "Прочитай первый урок": ["Прочитай перший урок", "Read the first lesson"],
    "Пройди марафон «Первый заказ»": ["Пройди марафон «Перше замовлення»", "Take the “First order” marathon"],
    "Поставь скиллы и плагины": ["Встанови скіли й плагіни", "Install skills and plugins"],
    "Отдельно для Claude Code и для Codex. Начни с памятки и раздела «Strix и UI Skills»: безопасность и аккуратный интерфейс.":
      ["Окремо для Claude Code і для Codex. Почни з пам'ятки та розділу «Strix і UI Skills»: безпека й охайний інтерфейс.",
       "Separately for Claude Code and Codex. Start with the guide and the “Strix and UI Skills” section: security and a clean interface."],
    "Собери первый сайт по промпту": ["Збери перший сайт за промптом", "Build your first site from a prompt"],
    "Найди клиента и напиши ему": ["Знайди клієнта й напиши йому", "Find a client and message them"],
    "Парсер находит бизнесы без сайта по нише и городу. Во вкладке «Скрипты» — готовые сообщения, а свои варианты сохраняются в библиотеку.":
      ["Парсер знаходить бізнеси без сайту за нішею та містом. У вкладці «Скрипти» — готові повідомлення, а свої варіанти зберігаються в бібліотеку.",
       "The parser finds businesses without a website by niche and city. The “Scripts” tab has ready messages, and your own versions are saved to a library."],
    "Покажи работу команде": ["Покажи роботу команді", "Show your work to the team"],
    "Пришли сайт в «Оценку работ» — команда разберёт и скажет, что поправить перед отправкой клиенту.":
      ["Надішли сайт в «Оцінку робіт» — команда розбере й скаже, що виправити перед відправкою клієнту.",
       "Send your site to “Work review” — the team will tell you what to fix before sending it to a client."],
    "Стань резидентом": ["Стань резидентом", "Become a resident"], "Заходи в чат резидентов": ["Заходь у чат резидентів", "Join the residents' chat"],
    "Открываются весь курс, авторские скиллы и плагины, парсер без ограничений и чат резидентов.":
      ["Відкриваються весь курс, авторські скіли й плагіни, парсер без обмежень і чат резидентів.",
       "Unlocks the whole course, C&C skills and plugins, the unlimited parser and the residents' chat."],
    "Помогаем друг другу, делимся результатами и разбираем работы.": ["Допомагаємо одне одному, ділимося результатами й розбираємо роботи.", "We help each other, share results and review work."],
    "Что входит": ["Що входить", "What's included"], "Чат": ["Чат", "Chat"],
    "Где что лежит": ["Де що лежить", "Where things are"],
    "Видео, карусель и лента: новые уроки и подборки": ["Відео, карусель і стрічка: нові уроки й добірки", "Video, carousel and feed: new lessons and collections"],
    "Все разделы: курс, парсер, скиллы, плагины, промпты, чат": ["Усі розділи: курс, парсер, скіли, плагіни, промпти, чат", "All sections: course, parser, skills, plugins, prompts, chat"],
    "Доступ, тема, уведомления, поддержка": ["Доступ, тема, сповіщення, підтримка", "Access, theme, notifications, support"],
    "Застрял?": ["Застряг?", "Stuck?"], "Напиши в поддержку — ответит живой человек из команды.": ["Напиши в підтримку — відповість жива людина з команди.", "Message support — a real person from the team will reply."],
    "Написать в поддержку": ["Написати в підтримку", "Contact support"],
    "Скиллы": ["Скіли", "Skills"],

    // FreeBot
    "Первый сайт, бот или дашборд за 1–2 дня. Бесплатно и без опыта": ["Перший сайт, бот або дашборд за 1–2 дні. Безкоштовно й без досвіду", "First website, bot or dashboard in 1–2 days. Free, no experience needed"],
    "VPN, установка Claude или Codex и проверка, что всё работает. 30–40 минут.": ["VPN, встановлення Claude або Codex і перевірка, що все працює. 30–40 хвилин.", "VPN, installing Claude or Codex and checking that everything works. 30–40 minutes."],
    "Выбери, что делаешь": ["Обери, що робиш", "Choose what you'll build"], "Только что-то одно. Не знаешь — бери сайт.": ["Щось одне. Не знаєш — бери сайт.", "Just one thing. Not sure? Pick a website."],
    "Сайт": ["Сайт", "Website"], "Telegram-бот": ["Telegram-бот", "Telegram bot"], "Дашборд": ["Дашборд", "Dashboard"],
    "Приоритет": ["Пріоритет", "Top pick"],
    "Лендинг для местного бизнеса. Продаётся проще всего": ["Лендинг для місцевого бізнесу. Продається найпростіше", "Landing page for a local business. Easiest to sell"],
    "Бот записи для мастера или салона": ["Бот запису для майстра або салону", "Booking bot for a master or salon"],
    "Цифры бизнеса на одном экране": ["Цифри бізнесу на одному екрані", "Business numbers on one screen"],
    "День 2. Делаешь проект": ["День 2. Робиш проєкт", "Day 2. Build the project"],
    "Появится после выбора. Внутри — готовый промпт и как выложить по ссылке.": ["З'явиться після вибору. Усередині — готовий промпт і як викласти за посиланням.", "Appears after you choose. Inside: a ready prompt and how to publish it."],
    "Сделал": ["Зробив", "Done"], "Первый проект готов": ["Перший проєкт готовий", "First project is ready"],
    "Дальше — как найти клиента и продать.": ["Далі — як знайти клієнта й продати.", "Next: how to find a client and sell."],
    "Что дальше": ["Що далі", "What's next"], "К FreeBot-марафону": ["До FreeBot-марафону", "Back to FreeBot marathon"],
    "Вступить в C&C Family": ["Вступити в C&C Family", "Join C&C Family"],

    // Каталог
    "Готовые навыки для Claude Code и других агентов: ставишь одной командой": ["Готові навички для Claude Code та інших агентів: ставиш однією командою", "Ready-made skills for Claude Code and other agents: install with one command"],
    "Готовые навыки для Codex: ставишь одной командой или через $skill-installer": ["Готові навички для Codex: ставиш однією командою або через $skill-installer", "Ready-made skills for Codex: one command or $skill-installer"],
    "Команды, агенты и подключения для Claude Code: ставишь одной командой": ["Команди, агенти й підключення для Claude Code: ставиш однією командою", "Commands, agents and integrations for Claude Code: install with one command"],
    "Плагины для Codex: скиллы, подключения и команды, ставятся во вкладке Plugins": ["Плагіни для Codex: скіли, підключення й команди, ставляться у вкладці Plugins", "Plugins for Codex: skills, integrations and commands, installed from the Plugins tab"],
    "Как выбирать скиллы": ["Як обирати скіли", "How to choose skills"], "Как выбирать плагины": ["Як обирати плагіни", "How to choose plugins"],
    "Читать памятку": ["Читати пам'ятку", "Read the guide"],
    "Ставь в проект пять-восемь скиллов ровно под задачу, а не всё подряд: лишние занимают память агента и спорят друг с другом. Внутри схемы и готовые наборы.":
      ["Став у проєкт п'ять-вісім скілів рівно під задачу, а не все підряд: зайві займають пам'ять агента й сперечаються між собою. Усередині схеми й готові набори.",
       "Add five to eight skills that fit the task, not everything: extra ones eat the agent's memory and conflict. Diagrams and ready sets inside."],
    "Начни с трёх-четырёх плагинов, а сервисы подключай только в тех проектах, где они есть. Внутри: чем плагин отличается от скилла и готовые наборы.":
      ["Почни з трьох-чотирьох плагінів, а сервіси підключай лише в проєктах, де вони є. Усередині: чим плагін відрізняється від скіла й готові набори.",
       "Start with three or four plugins and connect services only in projects that use them. Inside: plugins vs skills and ready sets."],
    "Strix и UI Skills": ["Strix і UI Skills", "Strix and UI Skills"], "Самое важное": ["Найважливіше", "Most important"],
    "Strix ищет дыры в безопасности с доказательством, UI Skills доводят интерфейс до аккуратного. Ставь первыми.":
      ["Strix шукає діри в безпеці з доказом, UI Skills доводять інтерфейс до охайного. Став першими.", "Strix finds proven security holes, UI Skills polish the interface. Install these first."],
    "Главное для сайтов": ["Головне для сайтів", "Essentials for websites"], "Для сайтов": ["Для сайтів", "For websites"],
    "Интерфейс, UX и проверка вёрстки. С этого начинай любой сайт.": ["Інтерфейс, UX і перевірка верстки. З цього починай будь-який сайт.", "Interface, UX and layout checks. Start every website here."],
    "Полный доступ для резидентов": ["Повний доступ для резидентів", "Full access for residents"],
    "Стать резидентом": ["Стати резидентом", "Become a resident"], "Все скиллы": ["Усі скіли", "All skills"], "Все плагины": ["Усі плагіни", "All plugins"],
    "Авторский скилл C&C": ["Авторський скіл C&C", "C&C skill"], "Авторский плагин C&C": ["Авторський плагін C&C", "C&C plugin"],
    "Открыто резидентам": ["Відкрито резидентам", "Open to residents"], "Урок для резидентов": ["Урок для резидентів", "Lesson for residents"],
    "Откроется сразу после оплаты вместе с курсом, парсером, скиллами, плагинами и чатом резидентов.":
      ["Відкриється одразу після оплати разом із курсом, парсером, скілами, плагінами й чатом резидентів.", "Unlocks right after payment along with the course, parser, skills, plugins and residents' chat."],
    "Здесь продолжение: пошаговые действия, примеры и готовые формулировки, которые можно сразу применить в работе с клиентом.":
      ["Тут продовження: покрокові дії, приклади й готові формулювання, які можна одразу застосувати в роботі з клієнтом.", "The rest is here: step-by-step actions, examples and ready wording you can use with clients right away."],
    "Скиллы Claude": ["Скіли Claude", "Claude skills"], "Скиллы Codex": ["Скіли Codex", "Codex skills"],
    "Плагины Claude": ["Плагіни Claude", "Claude plugins"], "Плагины Codex": ["Плагіни Codex", "Codex plugins"], "Памятка": ["Пам'ятка", "Guide"],

    // Разделы
    "Курс в цифрах": ["Курс у цифрах", "Course in numbers"], "Раздел в цифрах": ["Розділ у цифрах", "Section in numbers"],
    "Начать бесплатно": ["Почати безкоштовно", "Start free"], "Получить доступ": ["Отримати доступ", "Get access"],
    "Полная программа открывается сразу после оплаты. Список ниже.": ["Повна програма відкривається одразу після оплати. Список нижче.", "The full program unlocks right after payment. List below."],
    "пройдено": ["пройдено", "done"], "бесплатно": ["безкоштовно", "free"],
    "Вайбкодинг с нуля: от первого промпта до сайта, за который платят. Сайты, боты, поиск клиентов и сдача работы.":
      ["Вайбкодинг з нуля: від першого промпту до сайту, за який платять. Сайти, боти, пошук клієнтів і здача роботи.", "Vibe coding from scratch: from your first prompt to a website people pay for. Sites, bots, finding clients and delivery."],
    "Проверенные постановки задач: копируй, подставляй своё и получай результат с первого раза.":
      ["Перевірені постановки задач: копіюй, підставляй своє й отримуй результат з першого разу.", "Proven task prompts: copy, fill in your details and get it right the first time."],
    "Бриф, чек-лист сдачи, конструктор цены, штрафы и разборы реальных задач.":
      ["Бриф, чек-лист здачі, конструктор ціни, штрафи й розбори реальних задач.", "Brief, delivery checklist, pricing builder, legal risks and real case reviews."],
    "Где брать референсы, компоненты, шрифты, иконки, цвета и анимации.": ["Де брати референси, компоненти, шрифти, іконки, кольори й анімації.", "Where to find references, components, fonts, icons, colors and animations."],
    "Помощники с готовыми ролями. Вставь роль в проект Claude или ChatGPT — и у тебя есть продажник, верстальщик и тестировщик.":
      ["Помічники з готовими ролями. Встав роль у проєкт Claude або ChatGPT — і в тебе є продажник, верстальник і тестувальник.", "Assistants with ready roles. Paste a role into a Claude or ChatGPT project and you have a salesperson, a developer and a tester."],

    // Чат
    "Закрытый чат единомышленников C&C Family": ["Закритий чат однодумців C&C Family", "Private C&C Family members' chat"],
    "Здесь резиденты помогают друг другу, общаются и делятся результатами: первыми заказами, сайтами, ботами и цифрами. Вопрос, на котором застрял один, другой уже решал на прошлой неделе.":
      ["Тут резиденти допомагають одне одному, спілкуються й діляться результатами: першими замовленнями, сайтами, ботами й цифрами. Питання, на якому застряг один, інший уже вирішував минулого тижня.",
       "Residents help each other, talk and share results here: first orders, sites, bots and numbers. Whatever one person is stuck on, someone solved last week."],
    "Помощь": ["Допомога", "Help"], "Результаты": ["Результати", "Results"], "Общение": ["Спілкування", "Community"], "Разборы": ["Розбори", "Reviews"],
    "Застрял с ботом, деплоем или клиентом — спроси, ответят те, кто уже прошёл": ["Застряг із ботом, деплоєм чи клієнтом — запитай, відповідять ті, хто вже пройшов", "Stuck with a bot, deploy or client? Ask — people who've been there will answer"],
    "Первые заказы, сайты и деньги: делимся и разбираем, что сработало": ["Перші замовлення, сайти й гроші: ділимося й розбираємо, що спрацювало", "First orders, sites and money: we share and break down what worked"],
    "Свои люди без спама, рекламы и продаж курсов": ["Свої люди без спаму, реклами й продажу курсів", "Your people, no spam, ads or course selling"],
    "Скидываешь работу — получаешь честный фидбек от резидентов": ["Надсилаєш роботу — отримуєш чесний фідбек від резидентів", "Share your work, get honest feedback from residents"],
    "Как попасть": ["Як потрапити", "How to join"], "Чат входит в доступ к C&C Family": ["Чат входить у доступ до C&C Family", "The chat is part of C&C Family access"],
    "Нажми «Подать заявку»": ["Натисни «Подати заявку»", "Tap “Request to join”"], "Откроется Telegram, подтверди заявку": ["Відкриється Telegram, підтверди заявку", "Telegram opens, confirm the request"],
    "Бот одобрит сам": ["Бот схвалить сам", "The bot approves it"], "Обычно за пару секунд. Если доступ закончится, бот уберёт из чата": ["Зазвичай за кілька секунд. Якщо доступ закінчиться, бот прибере з чату", "Usually within seconds. If access ends, the bot removes you from the chat"],
    "Правила": ["Правила", "Rules"], "Помогаем и отвечаем по делу, без снисхождения": ["Допомагаємо й відповідаємо по суті, без зверхності", "We help and answer to the point, no condescension"],
    "Делимся результатами и ошибками — на них учатся все": ["Ділимося результатами й помилками — на них вчаться всі", "We share results and mistakes — everyone learns from them"],
    "Без рекламы, ссылок на свои курсы и спама": ["Без реклами, посилань на свої курси й спаму", "No ads, course links or spam"],
    "Что обсуждают в чате, остаётся в чате": ["Що обговорюють у чаті, лишається в чаті", "What's said in the chat stays in the chat"],
    "Подать заявку": ["Подати заявку", "Request to join"], "Заявка откроется после оплаты доступа.": ["Заявка відкриється після оплати доступу.", "Requests open after you pay for access."],
    "Заявку одобряет бот: ты резидент, поэтому без ожидания.": ["Заявку схвалює бот: ти резидент, тому без очікування.", "The bot approves your request: you're a resident, so no waiting."],

    // Сообщество и тарифы
    "Закрытое сообщество про вайбкодинг и нейросети. Учишься с нуля, собираешь сайты и ботов вместе с агентами и продаёшь их местному бизнесу.":
      ["Закрита спільнота про вайбкодинг і нейромережі. Вчишся з нуля, збираєш сайти й ботів разом з агентами та продаєш їх місцевому бізнесу.",
       "A private community about vibe coding and AI. Learn from scratch, build sites and bots with agents and sell them to local businesses."],
    "Оплатить": ["Оплатити", "Pay"], "Ты резидент": ["Ти резидент", "You're a resident"], "Что внутри": ["Що всередині", "What's inside"],
    "Как это работает": ["Як це працює", "How it works"], "Учишься": ["Вчишся", "Learn"], "Собираешь": ["Збираєш", "Build"],
    "Находишь клиентов": ["Знаходиш клієнтів", "Find clients"], "Пишешь по скриптам": ["Пишеш за скриптами", "Message with scripts"],
    "Проект, за который платят": ["Проєкт, за який платять", "A project people pay for"],
    "Курс, словарь и промпты с нуля": ["Курс, словник і промпти з нуля", "Course, glossary and prompts from scratch"],
    "Сайты и боты вместе с нейросетью": ["Сайти й боти разом із нейромережею", "Sites and bots with AI"],
    "Парсер приносит бизнесы без сайта": ["Парсер приносить бізнеси без сайту", "The parser brings businesses without a site"],
    "Готовые сообщения и разговор о цене": ["Готові повідомлення й розмова про ціну", "Ready messages and the price talk"],
    "Сайт или бот для реального бизнеса": ["Сайт або бот для реального бізнесу", "A site or bot for a real business"],
    "Отзывы": ["Відгуки", "Reviews"], "Кому зайдёт": ["Кому підійде", "Who it's for"], "Чего не обещаем": ["Чого не обіцяємо", "What we don't promise"],
    "Только заходишь в нейросети и не хочешь месяцами сидеть на туториалах": ["Тільки заходиш у нейромережі й не хочеш місяцями сидіти на туторіалах", "You're new to AI and don't want months of tutorials"],
    "Фрилансеру, которому надоело работать за копейки": ["Фрилансеру, якому набридло працювати за копійки", "Freelancers tired of working for pennies"],
    "Дизайнеру или маркетологу, который хочет собирать продукты сам": ["Дизайнеру чи маркетологу, який хоче збирати продукти сам", "Designers or marketers who want to build products themselves"],
    "Тому, кто уже пробует вайбкодить, но не понимает, как продавать": ["Тим, хто вже пробує вайбкодити, але не розуміє, як продавати", "People already vibe coding who don't know how to sell"],
    "Сеньором за неделю ты не станешь, и деньги сами не придут. C&C даёт систему: что делать, в каком порядке и где брать клиентов. Дальше — твои руки и регулярность.":
      ["Сеньйором за тиждень ти не станеш, і гроші самі не прийдуть. C&C дає систему: що робити, в якому порядку й де брати клієнтів. Далі — твої руки й регулярність.",
       "You won't become a senior in a week, and money won't come by itself. C&C gives you a system: what to do, in what order and where to find clients. The rest is your effort and consistency."],
    "Тарифы": ["Тарифи", "Plans"], "Я уже оплатил": ["Я вже оплатив", "I've already paid"],
    "Проверим оплату и участие в группе, доступ откроется сразу": ["Перевіримо оплату й участь у групі, доступ відкриється одразу", "We'll check your payment and group membership; access opens immediately"],
    "Бесплатно до оплаты": ["Безкоштовно до оплати", "Free before paying"], "навсегда": ["назавжди", "forever"], "пока платишь": ["поки платиш", "while subscribed"],
    "Курс, парсер, скиллы, плагины, материалы": ["Курс, парсер, скіли, плагіни, матеріали", "Course, parser, skills, plugins, materials"],
    "Чат единомышленников и закрытая группа": ["Чат однодумців і закрита група", "Members' chat and private group"],
    "Чат единомышленников": ["Чат однодумців", "Members' chat"], "Доступ": ["Доступ", "Access"],
    "Наставник до первого кейса": ["Наставник до першого кейсу", "Mentor until your first case"],
    "Резидент": ["Резидент", "Resident"], "VIP Резидент": ["VIP Резидент", "VIP Resident"],
    "Все материалы и инструменты": ["Усі матеріали й інструменти", "All materials and tools"],
    "Всё из «Резидента» и наставник до первого кейса": ["Усе з «Резидента» і наставник до першого кейсу", "Everything in Resident plus a mentor until your first case"],
    "Мест нет до понедельника": ["Місць немає до понеділка", "No spots until Monday"],
    "Оплатить криптой": ["Оплатити криптою", "Pay with crypto"],
    "Курс с нуля": ["Курс з нуля", "Course from scratch"], "Парсер клиентов": ["Парсер клієнтів", "Client parser"],
    "Бизнесы с телефонами по нише и городу и скрипты для переписки": ["Бізнеси з телефонами за нішею та містом і скрипти для листування", "Businesses with phone numbers by niche and city, plus outreach scripts"],
    "Скиллы и плагины": ["Скіли й плагіни", "Skills and plugins"], "Команда разбирает твой сайт и говорит, что улучшить": ["Команда розбирає твій сайт і каже, що покращити", "The team reviews your site and tells you what to improve"],
    "Бриф, договор, деплой, абонентка": ["Бриф, договір, деплой, абонентка", "Brief, contract, deploy, retainer"],
    "Помогаем друг другу и делимся результатами": ["Допомагаємо одне одному й ділимося результатами", "We help each other and share results"],

    // Профиль
    "Гость": ["Гість", "Guest"], "Админ": ["Адмін", "Admin"], "Доступ к C&C Family": ["Доступ до C&C Family", "C&C Family access"],
    "Открытые уроки, марафон и бесплатные материалы уже доступны. Полный доступ — у резидентов сообщества.":
      ["Відкриті уроки, марафон і безкоштовні матеріали вже доступні. Повний доступ — у резидентів спільноти.", "Open lessons, the marathon and free materials are available. Full access is for community residents."],
    "Доступ навсегда.": ["Доступ назавжди.", "Lifetime access."], "Доступ через закрытую группу.": ["Доступ через закриту групу.", "Access via the private group."],
    "Все уроки, парсер и скрипты открыты.": ["Усі уроки, парсер і скрипти відкриті.", "All lessons, the parser and scripts are unlocked."],
    "Настройки": ["Налаштування", "Settings"], "Тёмная тема": ["Темна тема", "Dark theme"], "Цвет приложения": ["Колір застосунку", "App color"],
    "Уведомления": ["Сповіщення", "Notifications"], "Бот напишет, когда выйдет урок, промпт или пост": ["Бот напише, коли вийде урок, промпт або пост", "The bot will message you about new lessons, prompts or posts"],
    "Язык": ["Мова", "Language"], "Как на устройстве": ["Як на пристрої", "Same as device"],
    "Уроки и материалы пока на русском": ["Уроки й матеріали поки російською", "Lessons and materials are in Russian for now"],
    "Закрытая группа": ["Закрита група", "Private group"], "Подай заявку — бот одобрит сам": ["Подай заявку — бот схвалить сам", "Send a request — the bot approves it"],
    "Проверить доступ": ["Перевірити доступ", "Check access"], "Если уже состоишь в закрытой группе или оплатил": ["Якщо вже в закритій групі або оплатив", "If you're already in the private group or have paid"],
    "Связаться с командой": ["Зв'язатися з командою", "Contact the team"], "Админка": ["Адмінка", "Admin panel"],
    "Люди, оплаты, тарифы, материалы, рассылки": ["Люди, оплати, тарифи, матеріали, розсилки", "People, payments, plans, materials, broadcasts"],
    "Иконки Solar, 480 Design, CC BY 4.0 · Шрифт Onest, OFL": ["Іконки Solar, 480 Design, CC BY 4.0 · Шрифт Onest, OFL", "Solar icons, 480 Design, CC BY 4.0 · Onest font, OFL"],

    // Марафон и оценка
    "Марафон «Первый заказ»": ["Марафон «Перше замовлення»", "“First order” marathon"], "Все дни": ["Усі дні", "All days"],
    "Открыт, можно начинать": ["Відкрито, можна починати", "Open, you can start"], "Сначала закрой предыдущий день": ["Спершу закрий попередній день", "Finish the previous day first"],
    "Откроется завтра": ["Відкриється завтра", "Opens tomorrow"], "Марафон пройден": ["Марафон пройдено", "Marathon complete"],
    "Отправить на оценку": ["Надіслати на оцінку", "Send for review"],
    "Выбрать скриншоты или видео": ["Обрати скриншоти або відео", "Choose screenshots or video"],
    "Ссылка на сайт, если есть": ["Посилання на сайт, якщо є", "Website link, if any"],

    // Подписка на канал
    "Приложение C&C открывается подписчикам канала. Там гайды, промпты, разборы и новости сообщества.":
      ["Застосунок C&C відкривається підписникам каналу. Там гайди, промпти, розбори й новини спільноти.", "The C&C app is for channel subscribers. The channel has guides, prompts, reviews and community news."],
    "Подай заявку в канал": ["Подай заявку в канал", "Request to join the channel"], "Кнопка ниже откроет Telegram": ["Кнопка нижче відкриє Telegram", "The button below opens Telegram"],
    "Вернись и нажми «Проверить»": ["Повернись і натисни «Перевірити»", "Come back and tap “Check”"],
    "Бот увидит заявку и сразу всё откроет": ["Бот побачить заявку й одразу все відкриє", "The bot sees the request and unlocks everything"],
    "Подать заявку в канал": ["Подати заявку в канал", "Request to join the channel"], "Проверить": ["Перевірити", "Check"],


    // Разделы каталога
    "Главное: Strix и UI Skills": ["Головне: Strix і UI Skills", "Essentials: Strix and UI Skills"], "Авторские C&C": ["Авторські C&C", "C&C originals"],
    "Сайты: UI и UX": ["Сайти: UI та UX", "Websites: UI and UX"], "Агенты и Claude Code": ["Агенти й Claude Code", "Agents and Claude Code"],
    "Код и проверка": ["Код і перевірка", "Code and testing"], "Telegram-боты и мини-аппы": ["Telegram-боти й міні-апи", "Telegram bots and mini apps"],
    "Мобильные приложения": ["Мобільні застосунки", "Mobile apps"], "Бэкенд и деплой": ["Бекенд і деплой", "Backend and deploy"],
    "Видео и графика": ["Відео й графіка", "Video and graphics"], "Документы и файлы": ["Документи й файли", "Documents and files"],
    "Маркетинг и SEO": ["Маркетинг і SEO", "Marketing and SEO"], "Продукт и планирование": ["Продукт і планування", "Product and planning"],
    "Встроены в Codex": ["Вбудовані в Codex", "Built into Codex"], "Деплой": ["Деплой", "Deploy"],
    "Код, GitHub и агенты": ["Код, GitHub і агенти", "Code, GitHub and agents"], "Безопасность": ["Безпека", "Security"],
    "Документы, звук и данные": ["Документи, звук і дані", "Documents, audio and data"], "Задачи и сервисы": ["Задачі й сервіси", "Tasks and services"],
    "Деплой и хостинг": ["Деплой і хостинг", "Deploy and hosting"], "Код и ревью": ["Код і рев'ю", "Code and review"],
    "Настройка Claude Code": ["Налаштування Claude Code", "Claude Code setup"], "Базы, оплата и почта": ["Бази, оплата й пошта", "Databases, payments and email"],
    "Telegram и мессенджеры": ["Telegram і месенджери", "Telegram and messengers"], "Задачи и команда": ["Задачі й команда", "Tasks and team"],
    "Поиск и данные": ["Пошук і дані", "Search and data"], "Сайты": ["Сайти", "Websites"],
    "Сайты под нишу: уровень, за который платят": ["Сайти під нішу: рівень, за який платять", "Niche websites people pay for"],
    "Дизайн и правки": ["Дизайн і правки", "Design and edits"], "Тексты": ["Тексти", "Copy"], "Боты и мини-аппы": ["Боти й міні-апи", "Bots and mini apps"],
    "Клиенты и продажи": ["Клієнти й продажі", "Clients and sales"], "Код и баги": ["Код і баги", "Code and bugs"],
    "Сдача и рост": ["Здача й ріст", "Delivery and growth"], "Дашборды и админки": ["Дашборди й адмінки", "Dashboards and admin panels"],
    "Старт": ["Старт", "Start"], "Первый сайт": ["Перший сайт", "First website"], "Telegram-боты": ["Telegram-боти", "Telegram bots"],
    "Клиенты": ["Клієнти", "Clients"],
    // Всплывающие сообщения
    "Скопировано": ["Скопійовано", "Copied"], "Отмечено": ["Позначено", "Marked"], "Проверяю…": ["Перевіряю…", "Checking…"],
    "Сохранено": ["Збережено", "Saved"], "Готово": ["Готово", "Done"], "Нет связи с сервером": ["Немає зв'язку із сервером", "No connection to the server"],
    "День закрыт. Следующий откроется завтра": ["День закрито. Наступний відкриється завтра", "Day complete. The next one opens tomorrow"],
    "Оплата прошла, открываю доступ": ["Оплата пройшла, відкриваю доступ", "Payment received, unlocking access"],
    "После оплаты вернись сюда — доступ откроется сам": ["Після оплати повернись сюди — доступ відкриється сам", "Come back after paying — access opens automatically"],
    "Платёж не прошёл. Попробуй ещё раз или напиши в поддержку": ["Платіж не пройшов. Спробуй ще раз або напиши в підтримку", "Payment failed. Try again or contact support"],
    "Заявка откроется после оплаты доступа": ["Заявка відкриється після оплати доступу", "Requests open after you pay for access"],
    "Доступ открыт. Ссылка в группу — в чате с ботом": ["Доступ відкрито. Посилання в групу — у чаті з ботом", "Access unlocked. The group link is in your chat with the bot"],
    "Выдели текст и скопируй вручную": ["Виділи текст і скопіюй вручну", "Select the text and copy it manually"],
    "Подписку вижу, добро пожаловать": ["Підписку бачу, ласкаво просимо", "Subscription confirmed, welcome"],
    "Пока не вижу подписки или заявки. Подай заявку в канал и нажми «Проверить» ещё раз.": ["Поки не бачу підписки чи заявки. Подай заявку в канал і натисни «Перевірити» ще раз.", "No subscription or request yet. Request to join the channel and tap “Check” again."]
  };

  var NOUNS = {
    "урок": [["урок", "урока", "уроков"], ["урок", "уроки", "уроків"], ["lesson", "lessons"]],
    "модуль": [["модуль", "модуля", "модулей"], ["модуль", "модулі", "модулів"], ["module", "modules"]],
    "раздел": [["раздел", "раздела", "разделов"], ["розділ", "розділи", "розділів"], ["section", "sections"]],
    "промпт": [["промпт", "промпта", "промптов"], ["промпт", "промпти", "промптів"], ["prompt", "prompts"]],
    "материал": [["материал", "материала", "материалов"], ["матеріал", "матеріали", "матеріалів"], ["material", "materials"]],
    "подборка": [["подборка", "подборки", "подборок"], ["добірка", "добірки", "добірок"], ["collection", "collections"]],
    "помощник": [["помощник", "помощника", "помощников"], ["помічник", "помічники", "помічників"], ["assistant", "assistants"]],
    "скилл": [["скилл", "скилла", "скиллов"], ["скіл", "скіли", "скілів"], ["skill", "skills"]],
    "плагин": [["плагин", "плагина", "плагинов"], ["плагін", "плагіни", "плагінів"], ["plugin", "plugins"]],
    "день": [["день", "дня", "дней"], ["день", "дні", "днів"], ["day", "days"]],
    "участник": [["участник", "участника", "участников"], ["учасник", "учасники", "учасників"], ["member", "members"]],
    "ступенька": [["ступенька", "ступеньки", "ступенек"], ["сходинка", "сходинки", "сходинок"], ["step", "steps"]]
  };
  var FORM = {};
  Object.keys(NOUNS).forEach(function (k) { NOUNS[k][0].forEach(function (f) { FORM[f] = k; }); });

  function pl3(n, f) { var m = n % 10, h = n % 100; return m === 1 && h !== 11 ? f[0] : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? f[1] : f[2]; }
  function noun(n, ruWord, lang) {
    var k = FORM[ruWord]; if (!k) return null;
    return lang === "uk" ? pl3(n, NOUNS[k][1]) : (n === 1 ? NOUNS[k][2][0] : NOUNS[k][2][1]);
  }
  var L = 0;   // 0 — uk, 1 — en
  function lang() { return L === 0 ? "uk" : "en"; }
  function num(s) { return parseInt(String(s).replace(/\s/g, ""), 10); }

  // Строки с числами
  var RULES = [
    [/^(\d+) из (\d+) открыт[ыа] бесплатно$/, function (m) { return L ? m[1] + " of " + m[2] + " free" : m[1] + " з " + m[2] + " відкрито безкоштовно"; }],
    [/^Пройдено (\d+) из (\d+)$/, function (m) { return L ? "Done " + m[1] + " of " + m[2] : "Пройдено " + m[1] + " з " + m[2]; }],
    [/^из (\d+) ступенек$/, function (m) { return L ? "of " + m[1] + " steps" : "з " + m[1] + " сходинок"; }],
    [/^Ещё (\d+) (\S+) для резидентов$/, function (m) { var w = noun(num(m[1]), m[2], lang()); return w && (L ? m[1] + " more " + w + " for residents" : "Ще " + m[1] + " " + w + " для резидентів"); }],
    [/^(\d+) (\S+) для Claude и Codex$/, function (m) { var w = noun(num(m[1]), m[2], lang()); return w && m[1] + " " + w + (L ? " for Claude and Codex" : " для Claude і Codex"); }],
    [/^(\d+) (\S+) из этого раздела, включая авторские C&C, открываются после вступления в C&C Family\.$/, function (m) {
      var w = noun(num(m[1]), m[2], lang()); return w && (L ? m[1] + " " + w + " in this section, including C&C originals, unlock when you join C&C Family." :
        m[1] + " " + w + " з цього розділу, включно з авторськими C&C, відкриваються після вступу в C&C Family."); }],
    [/^(\d+) помощник\S* с готовыми ролями$/, function (m) { var w = noun(num(m[1]), "помощник", lang()); return m[1] + " " + w + (L ? " with ready roles" : " з готовими ролями"); }],
    [/^(\d+) промпт\S* под задачи$/, function (m) { var w = noun(num(m[1]), "промпт", lang()); return m[1] + " " + w + (L ? " for real tasks" : " під задачі"); }],
    [/^(\d+) материал\S*: бриф, договор, деплой$/, function (m) { var w = noun(num(m[1]), "материал", lang()); return m[1] + " " + w + (L ? ": brief, contract, deploy" : ": бриф, договір, деплой"); }],
    [/^Мест на неделе: (\d+)$/, function (m) { return (L ? "Spots this week: " : "Місць цього тижня: ") + m[1]; }],
    [/^Привет, (.+)$/, function (m) { return (L ? "Hi, " : "Привіт, ") + m[1]; }],
    [/^Открыть день (\d+)$/, function (m) { return (L ? "Open day " : "Відкрити день ") + m[1]; }],
    [/^День (\d+): (.+)$/, function (m) { return (L ? "Day " : "День ") + m[1] + ": " + m[2]; }],
    [/^Оплатить картой · (.+)$/, function (m) { return (L ? "Pay by card · " : "Оплатити карткою · ") + m[1]; }],
    [/^Оплатить звёздами · (.+)$/, function (m) { return (L ? "Pay with Stars · " : "Оплатити зірками · ") + m[1]; }],
    [/^Подпишись на канал (.+)$/, function (m) { return (L ? "Subscribe to " : "Підпишись на канал ") + m[1]; }],
    [/^Доступ до (.+)\.$/, function (m) { return (L ? "Access until " : "Доступ до ") + m[1] + "."; }],
    [/^(\d+) (\S+)$/, function (m) { var w = noun(num(m[1]), m[2], lang()); return w && m[1] + " " + w; }],
    [/^(\d+) бесплатно$/, function (m) { return m[1] + (L ? " free" : " безкоштовно"); }]
  ];

  function tr(s) {
    if (Object.prototype.hasOwnProperty.call(D, s)) return D[s][L];
    for (var i = 0; i < RULES.length; i++) {
      var m = RULES[i][0].exec(s);
      if (m) { var r = RULES[i][1](m); if (r) return r; }
    }
    if (s.indexOf(", ") > 0) {    // «5 модулей, 19 уроков, 9 бесплатно»
      var parts = s.split(", "), out = [];
      for (var k = 0; k < parts.length; k++) { var t = tr(parts[k]); if (t == null) return null; out.push(t); }
      return out.join(", ");
    }
    return null;
  }

  function current() { return window.CC_LANG || "ru"; }
  function walk(root) {
    if (!root) return;
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), n, list = [];
    while ((n = w.nextNode())) list.push(n);
    list.forEach(function (node) {
      var p = node.parentElement;
      if (!p || p.closest(".md, pre, code, .notr, .krow .row-text, .nrow .row-text, .lcard .row-text, .row[data-item] .row-text, .post h3, .post-text, .review, .lesson > h1, .lesson > .lead, .tariff ul, .tariff .muted")) return;
      var raw = node.nodeValue, t = raw.trim();
      if (!t || !/[А-Яа-яЁё]/.test(t)) return;
      var x = tr(t);
      if (x != null) node.nodeValue = raw.replace(t, x);
    });
    root.querySelectorAll("[placeholder],[aria-label]").forEach(function (el) {
      ["placeholder", "aria-label"].forEach(function (a) {
        var v = el.getAttribute(a); if (!v) return; var x = tr(v.trim()); if (x != null) el.setAttribute(a, x);
      });
    });
  }

  window.ccTr = function (s) { var l = current(); if (l === "ru") return s; L = l === "uk" ? 0 : 1; var x = tr(s); return x == null ? s : x; };
  window.ccTranslate = function () {
    var l = current();
    document.documentElement.lang = l;
    if (l === "ru") return;
    L = l === "uk" ? 0 : 1;
    ["app", "nav", "sheet"].forEach(function (id) { walk(document.getElementById(id)); });
  };
  window.ccDetectLang = function (code) {
    code = String(code || "").toLowerCase();
    if (/^uk/.test(code)) return "uk";
    if (!code || /^(ru|be|kk|ky|uz|tg|hy|az|ka|tk|mo)/.test(code)) return "ru";
    return "en";
  };
})();
