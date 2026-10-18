"""Ниши поиска: какие объекты искать в каждом источнике.

Номера 0–5 совпадают с прежней версией (5 — своя ниша), новые ниши идут дальше.
Для каждой ниши несколько запросов: теги OpenStreetMap, поиск по названию,
категории Geoapify и текстовые запросы Google (если он подключён)."""

from __future__ import annotations

CUSTOM = 5

# Ключи OSM, у которых бывают организации. Поиск по названию ограничен ими,
# чтобы не попадали улицы, остановки и прочие объекты с похожим названием.
BUSINESS_KEYS = "shop|amenity|craft|office|leisure|healthcare|tourism|club"

NICHES: dict[int, dict] = {
    0: {
        "title": "Барбершопы",
        "short": "Барбершоп",
        "osm": [
            '["shop"="barber"]',
            '["shop"="hairdresser"]["hairdresser"~"barber|men",i]',
            '["shop"="hairdresser"]["male"="yes"]',
        ],
        "name": "барбер|barber|мужская парикмахерская|barbershop",
        "geoapify": ["service.beauty.hairdresser"],
        "name_filter": r"барбер|barber|мужск|men|gentle|бород|beard",
        "google_ru": ["барбершоп", "мужская парикмахерская"],
        "google_en": ["barber shop", "barbershop"],
    },
    1: {
        "title": "Салоны красоты",
        "short": "Салон красоты",
        "osm": ['["shop"="beauty"]', '["shop"="hairdresser"]'],
        "name": "салон красоты|beauty salon|студия красоты|salon kosmetyczny|salon urody|kosmetikstudio|grožio salonas",
        "geoapify": ["service.beauty"],
        "google_ru": ["салон красоты", "парикмахерская"],
        "google_en": ["beauty salon", "hair salon"],
    },
    2: {
        "title": "Автосервисы",
        "short": "Автосервис",
        "osm": ['["shop"="car_repair"]', '["shop"="tyres"]', '["craft"="car_repair"]'],
        "name": "автосервис|шиномонтаж|автотехцентр|кузовн|car service|auto service|warsztat|serwis samochod|autowerkstatt|kfz|autoservisas",
        "geoapify": ["service.vehicle.repair", "commercial.vehicle"],
        "google_ru": ["автосервис", "шиномонтаж"],
        "google_en": ["car repair", "auto service"],
    },
    3: {
        "title": "Стоматологии",
        "short": "Стоматология",
        "osm": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
        "name": "стоматолог|dental|dentist|дентал|stomatolog|zahnarzt|odontolog|dantų",
        "geoapify": ["healthcare.dentist"],
        "google_ru": ["стоматология", "стоматологическая клиника"],
        "google_en": ["dentist", "dental clinic"],
    },
    4: {
        "title": "Фитнес и спортзалы",
        "short": "Фитнес",
        "osm": [
            '["leisure"="fitness_centre"]',
            '["leisure"="sports_centre"]["sport"~"fitness|yoga|crossfit|boxing|martial",i]',
            '["sport"="yoga"]["leisure"]',
        ],
        "name": "фитнес|fitness|тренажерн|тренажёрн|gym$|gym |йога|yoga|кроссфит|crossfit|siłownia|sporto klubas",
        "geoapify": ["sport.fitness", "activity.sport_club"],
        "google_ru": ["фитнес клуб", "тренажёрный зал"],
        "google_en": ["fitness club", "gym"],
    },
    6: {
        "title": "Маникюр и ногти",
        "short": "Маникюр",
        "osm": ['["shop"="beauty"]["beauty"~"nails",i]', '["shop"="nails"]'],
        "name": "маникюр|ногт|nail|нейл|paznokci|nagelstudio|manikiūr",
        "geoapify": ["service.beauty"],
        "name_filter": r"маникюр|ногт|nail|нейл|педикюр",
        "google_ru": ["студия маникюра", "ногтевая студия"],
        "google_en": ["nail salon", "manicure"],
    },
    7: {
        "title": "Кофейни и кафе",
        "short": "Кафе",
        "osm": ['["amenity"="cafe"]'],
        "name": "кофейн|coffee|кафе|kawiarnia|kavinė",
        "geoapify": ["catering.cafe"],
        "google_ru": ["кофейня", "кафе"],
        "google_en": ["coffee shop", "cafe"],
    },
    8: {
        "title": "Рестораны",
        "short": "Ресторан",
        "osm": ['["amenity"="restaurant"]'],
        "name": "ресторан|restaurant|бистро|bistro|траттория|trattoria|restauracja|restoranas",
        "geoapify": ["catering.restaurant"],
        "google_ru": ["ресторан"],
        "google_en": ["restaurant"],
    },
    9: {
        "title": "Ветклиники",
        "short": "Ветклиника",
        "osm": ['["amenity"="veterinary"]', '["healthcare"="veterinary"]'],
        "name": "ветеринар|ветклиник|ветцентр|ветврач|зоовет|vet clinic|veterinar|weterynar|tierarzt|tierklinik",
        "geoapify": ["pet.veterinary"],
        "google_ru": ["ветеринарная клиника"],
        "google_en": ["veterinary clinic"],
    },
    10: {
        "title": "Языковые и детские школы",
        "short": "Школа",
        "osm": [
            '["amenity"="language_school"]',
            '["amenity"="prep_school"]',
            '["amenity"="music_school"]',
            '["amenity"="dancing_school"]',
        ],
        "name": "английск|языков|english|школа танц|детский центр|развивающ|лингв|szkoła językowa|sprachschule|kalbų mokykla",
        "geoapify": ["education.language_school", "education.music_school", "education.dancing_school"],
        "google_ru": ["школа английского языка", "детский развивающий центр"],
        "google_en": ["language school", "kids learning center"],
    },
}


# ---- Дополнительные ниши (версия 4): всего 35 ниш ----
_MORE = [
    (11, "Массаж и SPA", "Массаж", ['["shop"="massage"]', '["leisure"="spa"]', '["amenity"="spa"]'],
     "массаж|спа-|спа |спа$|spa |spa$|massage|masaż|masažas", ["service.beauty.massage", "service.beauty.spa"],
     ["массажный салон", "спа салон"], ["massage salon", "spa"]),
    (12, "Косметология", "Косметология", ['["shop"="beauty"]["beauty"~"cosmetics|skin|face",i]', '["healthcare"="clinic"]["healthcare:speciality"~"cosmetology|dermatology",i]'],
     "косметолог|cosmetolog|эстетической медицин|skin clinic|kosmetolog", ["service.beauty"],
     ["косметология", "косметологический кабинет"], ["cosmetology clinic", "aesthetic clinic"]),
    (13, "Тату-салоны", "Тату", ['["shop"="tattoo"]'],
     "тату|tattoo|татуир|tatuaż|tätowier", ["service.beauty"],
     ["тату салон"], ["tattoo studio"]),
    (14, "Парикмахерские", "Парикмахерская", ['["shop"="hairdresser"]'],
     "парикмахер|hair studio|hairdresser|fryzjer|friseur|kirpykla", ["service.beauty.hairdresser"],
     ["парикмахерская"], ["hairdresser"]),
    (15, "Медицинские центры", "Медцентр", ['["amenity"="clinic"]', '["healthcare"="clinic"]', '["amenity"="doctors"]'],
     "медицинский центр|медцентр|клиника|medical center|clinic|przychodnia|klinika", ["healthcare.clinic_or_praxis"],
     ["медицинский центр", "частная клиника"], ["medical center", "private clinic"]),
    (16, "Танцевальные студии", "Танцы", ['["amenity"="dancing_school"]', '["leisure"="dance"]'],
     "танцев|танца|танцы|dance|хореограф|szkoła tańca|tanzschule|šokių", [],
     ["студия танцев"], ["dance studio"]),
    (17, "Бани и сауны", "Баня", ['["leisure"="sauna"]', '["amenity"="public_bath"]'],
     "баня|бани|сауна|sauna|hamam|хамам|łaźnia|pirtis", [],
     ["баня", "сауна"], ["sauna", "bathhouse"]),
    (18, "Гостиницы и хостелы", "Гостиница", ['["tourism"="hotel"]', '["tourism"="hostel"]', '["tourism"="guest_house"]'],
     "гостиниц|отель|хостел|hotel|hostel|гостевой дом|hotel|nakvynė", ["accommodation.hotel", "accommodation.hostel", "accommodation.guest_house"],
     ["гостиница", "хостел"], ["hotel", "hostel"]),
    (19, "Пекарни и кондитерские", "Пекарня", ['["shop"="bakery"]', '["shop"="confectionery"]', '["shop"="pastry"]'],
     "пекарн|кондитер|bakery|cake|торты|piekarnia|cukiernia|bäckerei|konditorei|kepykla", ["commercial.food_and_drink.bakery", "commercial.food_and_drink.confectionery"],
     ["пекарня", "кондитерская"], ["bakery", "pastry shop"]),
    (20, "Пиццерии и суши", "Пиццерия", ['["amenity"~"fast_food|restaurant"]["cuisine"~"pizza|sushi|japanese",i]'],
     "пицц|суши|роллы|pizza|sushi|pizzeria", ["catering.restaurant.pizza", "catering.fast_food.pizza", "catering.restaurant.sushi"],
     ["пиццерия", "доставка суши"], ["pizzeria", "sushi delivery"]),
    (21, "Цветочные магазины", "Цветы", ['["shop"="florist"]'],
     "цветы|цветоч|флорист|букет|flower|florist|kwiaciarnia|blumen|gėlės", ["commercial.florist"],
     ["цветочный магазин", "доставка цветов"], ["florist", "flower shop"]),
    (22, "Фотостудии", "Фотостудия", ['["craft"="photographer"]', '["shop"="photo"]'],
     "фотостуди|фотограф|photo studio|photographer|studio fotograficzne|fotostudio", [],
     ["фотостудия"], ["photo studio"]),
    (23, "Юристы", "Юрист", ['["office"="lawyer"]', '["office"="notary"]'],
     "юрист|юридическ|адвокат|нотариус|lawyer|law firm|kancelaria|rechtsanwalt|advokat", [],
     ["юридические услуги", "адвокат"], ["law firm", "lawyer"]),
    (24, "Бухгалтерия", "Бухгалтерия", ['["office"="accountant"]', '["office"="tax_advisor"]'],
     "бухгалтер|accounting|accountant|biuro rachunkowe|steuerberater|buhalter", [],
     ["бухгалтерские услуги"], ["accounting services"]),
    (25, "Агентства недвижимости", "Недвижимость", ['["office"="estate_agent"]'],
     "агентство недвижимост|агентство недвижимости|риелтор|риэлтор|real estate|realty|biuro nieruchomości|immobilienmakler|nekilnojamojo turto agentūra", [],
     ["агентство недвижимости"], ["real estate agency"]),
    (26, "Ремонт и строительство", "Ремонт", ['["craft"~"builder|carpenter|plumber|electrician|tiler|painter|plasterer|roofer|window_construction"]', '["office"="construction_company"]'],
     "ремонт квартир|строительн|отделк|сантехник|электрик|окна|кровл|remont|budow|renovation|bauunternehmen", [],
     ["ремонт квартир", "строительная компания"], ["renovation company", "construction company"]),
    (27, "Мебель на заказ", "Мебель", ['["shop"="furniture"]', '["shop"="kitchen"]', '["craft"="carpenter"]'],
     "мебел|кухни на заказ|шкаф|furniture|meble|möbel|baldai", ["commercial.furniture_and_interior.furniture"],
     ["мебель на заказ", "кухни на заказ"], ["custom furniture", "kitchen furniture"]),
    (28, "Автомойки и детейлинг", "Автомойка", ['["amenity"="car_wash"]', '["shop"="car"]["service"~"detailing",i]'],
     "автомойк|мойка|детейлинг|car wash|detailing|myjnia|autowäsche|plovykla", ["service.vehicle.car_wash"],
     ["автомойка", "детейлинг"], ["car wash", "car detailing"]),
    (29, "Автошколы", "Автошкола", ['["amenity"="driving_school"]'],
     "автошкол|driving school|szkoła jazdy|fahrschule|vairavimo", ["education.driving_school"],
     ["автошкола"], ["driving school"]),
    (30, "Детские центры", "Детский центр", ['["amenity"="kindergarten"]["operator:type"!="public"]["name"~"[Чч]астн|[Рр]азвива|[Цц]ентр|[Кк]луб|[Mm]ontessori",i]', '["amenity"="childcare"]'],
     "детский центр|развивающ|детский клуб|монтессори|montessori|kids club|детский сад", ["childcare.kindergarten"],
     ["детский развивающий центр", "частный детский сад"], ["kids center", "private kindergarten"]),
    (31, "Зоомагазины и груминг", "Зоотовары", ['["shop"="pet"]', '["shop"="pet_grooming"]'],
     "зоомагазин|зоотовар|груминг|grooming|pet shop|zoo|sklep zoologiczny|tierbedarf", ["commercial.pet"],
     ["зоомагазин", "груминг"], ["pet shop", "pet grooming"]),
    (32, "Магазины одежды", "Одежда", ['["shop"="clothes"]', '["shop"="boutique"]', '["shop"="shoes"]'],
     "одежд|бутик|шоурум|showroom|boutique|clothes|odzież|modehaus|drabužiai", ["commercial.clothing"],
     ["магазин одежды", "шоурум"], ["clothing store", "boutique"]),
    (33, "Ремонт телефонов и техники", "Ремонт техники", ['["craft"="electronics_repair"]', '["shop"="mobile_phone"]["repair"]', '["shop"="computer"]["repair"]', '["service:electronics:repair"="yes"]'],
     "ремонт телефон|ремонт техники|сервисный центр|ремонт ноутбук|phone repair|serwis telefon|handy reparatur|telefonų taisymas", [],
     ["ремонт телефонов", "сервисный центр"], ["phone repair", "electronics repair"]),
    (34, "Химчистки и прачечные", "Химчистка", ['["shop"="dry_cleaning"]', '["shop"="laundry"]'],
     "химчистк|прачечн|dry cleaning|laundry|pralnia|reinigung|valykla", ["service.cleaning.dry_cleaning", "service.cleaning.laundry"],
     ["химчистка", "прачечная"], ["dry cleaning", "laundry"]),
    (35, "Ювелирные мастерские", "Ювелирка", ['["shop"="jewelry"]', '["craft"="jeweller"]'],
     "ювелир|jewel|złotnik|juwelier|juvelyr", ["commercial.jewelry"],
     ["ювелирная мастерская"], ["jewelry store"]),
]
for _id, _title, _short, _osm, _name, _geo, _gru, _gen in _MORE:
    NICHES[_id] = {"title": _title, "short": _short, "osm": _osm, "name": _name,
                   "geoapify": _geo, "google_ru": _gru, "google_en": _gen}

# От самых популярных к редким: так они идут в списке выбора.
ORDER = [0, 1, 6, 2, 3, 4, 7, 8, 11, 12, 15, 20, 19, 21, 28, 26, 25, 23, 9, 10,
         30, 16, 13, 14, 18, 17, 22, 24, 27, 29, 31, 32, 33, 34, 35]


def get(niche: int) -> dict:
    return NICHES.get(niche, NICHES[0])


def title(niche: int, custom: str = "") -> str:
    if niche == CUSTOM:
        return (custom or "Своя ниша").strip()[:80]
    return get(niche)["title"]


def valid(niche: int) -> bool:
    return niche == CUSTOM or niche in NICHES


def public_list() -> list[dict]:
    items = [{"id": key, "title": NICHES[key]["title"], "short": NICHES[key]["short"]} for key in ORDER]
    items.append({"id": CUSTOM, "title": "Своя ниша", "short": "Своя"})
    return items
