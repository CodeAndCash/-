"""Проверки ядра C&C Family: доступ, оплата, напоминания, админка, марафон, оценка работ, бот."""
import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from conftest import ADMIN_ID, headers

from fastapi.testclient import TestClient

from cc import access, config, content, db, payments
from cc.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def run(coro):
    return asyncio.run(coro)


class Sent:
    """Подмена отправки сообщений: копит всё, что бот «отправил»."""

    def __init__(self):
        self.messages = []

    async def message(self, chat_id, text, **kw):
        self.messages.append((chat_id, text, kw))

    async def photo(self, chat_id, photo, caption=None, **kw):
        self.messages.append((chat_id, caption, kw))
        return type("M", (), {"photo": None})()


def fake_bot(sent: Sent):
    from cc.tg import bot
    return patch.multiple(bot, send_message=AsyncMock(side_effect=sent.message),
                          send_photo=AsyncMock(side_effect=sent.photo),
                          send_animation=AsyncMock(side_effect=sent.photo))


# ---------- Вход и материалы ----------

def test_bootstrap_requires_telegram(client):
    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/bootstrap", headers={"X-Init-Data": "user=1&hash=bad"}).status_code == 401


def test_bootstrap_guest(client):
    r = client.get("/api/bootstrap", headers=headers(1001))
    assert r.status_code == 200
    d = r.json()
    assert d["me"]["access"]["resident"] is False
    assert d["counts"]["lesson"] == 19 and d["counts"]["modules"] == 5
    assert {t["id"] for t in d["tariffs"]} == {"base", "mentor"}
    mentor = next(t for t in d["tariffs"] if t["id"] == "mentor")
    assert mentor["available"] is False          # тариф с наставником под замком
    assert set(d["methods"]) == {"card", "crypto"}
    assert d["marathon"]["total"] == 7 and d["marathon"]["days"][0]["open"]
    assert not d["marathon"]["days"][1]["open"]


def test_locked_lesson_hides_body_but_shows_outline(client):
    lessons = client.get("/api/content?kind=lesson", headers=headers(1002)).json()["items"]
    free = next(l for l in lessons if l["free"])
    closed = next(l for l in lessons if not l["free"])
    f = client.get(f"/api/content/{free['id']}", headers=headers(1002)).json()
    assert f["locked"] is False and len(f["body"]) > 200 and f["next"]
    c = client.get(f"/api/content/{closed['id']}", headers=headers(1002)).json()
    assert c["locked"] is True and c["body"] == "" and c["outline"] and c["intro"]
    # закрытое нельзя отметить пройденным
    assert client.post(f"/api/content/{closed['id']}/done", json={"done": True}, headers=headers(1002)).status_code == 403
    assert client.post(f"/api/content/{free['id']}/done", json={"done": True}, headers=headers(1002)).json()["done"]


def test_marathon_opens_next_day_tomorrow(client):
    uid = 1003
    days = client.get("/api/marathon", headers=headers(uid)).json()["days"]
    client.post(f"/api/content/{days[0]['id']}/done", json={"done": True}, headers=headers(uid))
    state = client.get("/api/marathon", headers=headers(uid)).json()
    assert state["done"] == 1
    assert state["days"][1]["open"] is False and state["days"][1]["reason"] == "Откроется завтра"

    async def yesterday():
        async with db.connect() as conn:
            await conn.execute("UPDATE progress SET done_at=done_at-90000 WHERE user_id=?", (uid,))
            await conn.commit()
    run(yesterday())
    state = client.get("/api/marathon", headers=headers(uid)).json()
    assert state["days"][1]["open"] is True and state["current"]["day"] == 2


# ---------- Оплата картой ----------

def test_card_checkout_and_payment_grant_everything(client):
    uid = 2001
    client.get("/api/bootstrap", headers=headers(uid))
    with patch("cc.tg.bot.create_invoice_link", AsyncMock(return_value="https://t.me/$invoice")) as link:
        r = client.post("/api/checkout", json={"tariff": "base", "method": "card"}, headers=headers(uid))
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "invoice"
    kw = link.call_args.kwargs
    assert kw["currency"] == "RUB" and kw["prices"][0].amount == 2990 * 100 and kw["payload"] == f"cc:{r.json()['payment']}"

    payment = run(db.get_payment(r.json()["payment"]))
    assert payment["status"] == "pending"

    from cc.bot import complete_payment
    sent = Sent()
    with fake_bot(sent):
        assert run(complete_payment(payment, note="charge-1")) is True
        assert run(complete_payment(payment, note="charge-1")) is False   # повтор ничего не делает
    user = run(db.get_user(uid))
    assert db.is_resident(user) and user["access_until"] > time.time() + 29 * 86400
    assert any(m[0] == uid and "Оплата прошла" in m[1] for m in sent.messages)
    assert any(m[0] == ADMIN_ID and "Оплата" in m[1] for m in sent.messages)

    # парсер и скрипты открылись, оценки добавились
    from modules.evaluation import db as eval_db
    from modules.parser import db as parser_db
    assert parser_db.is_member(run(parser_db.get_user(uid)))
    assert eval_db.quota(run(eval_db.get_user(uid)))["credits"] == config.EVAL_RESIDENT_CREDITS

    # закрытый урок теперь открыт
    lessons = client.get("/api/content?kind=lesson", headers=headers(uid)).json()["items"]
    closed = next(l for l in lessons if not l["free"])
    assert client.get(f"/api/content/{closed['id']}", headers=headers(uid)).json()["body"]


def test_pre_checkout_checks_amount_and_owner():
    from cc.bot import pre_checkout
    pid = run(db.create_payment(2002, "base", "card", 2990, "RUB", 30))
    answers = []

    class Q:
        def __init__(self, uid, total):
            self.invoice_payload = f"cc:{pid}"
            self.from_user = type("U", (), {"id": uid})()
            self.total_amount = total

        async def answer(self, ok, error_message=None):
            answers.append(ok)

    run(pre_checkout(Q(2002, 299000)))
    run(pre_checkout(Q(2002, 100)))      # чужая сумма
    run(pre_checkout(Q(9999, 299000)))   # чужой счёт
    assert answers == [True, False, False]


def test_mentor_tariff_locked_until_opened(client):
    r = client.post("/api/checkout", json={"tariff": "mentor", "method": "card"}, headers=headers(2003))
    assert r.status_code == 409 and "скоро" in r.json()["detail"].lower()


# ---------- Крипта ----------

def test_crypto_webhook_signature_and_grant(client):
    uid = 3001
    client.get("/api/bootstrap", headers=headers(uid))
    with patch("cc.payments.crypto_call", AsyncMock(return_value={"invoice_id": 777, "mini_app_invoice_url": "https://t.me/CryptoBot/app?startapp=x"})) as call:
        r = client.post("/api/checkout", json={"tariff": "base", "method": "crypto"}, headers=headers(uid))
    assert r.json() == {"payment": r.json()["payment"], "kind": "link", "url": "https://t.me/CryptoBot/app?startapp=x"}
    assert call.call_args.args[1]["fiat"] == "RUB" and call.call_args.args[1]["amount"] == "2990.00"

    body = json.dumps({"update_type": "invoice_paid", "payload": {"invoice_id": 777, "status": "paid"}}).encode()
    assert client.post("/api/pay/crypto", content=body, headers={"crypto-pay-api-signature": "bad"}).status_code == 401
    secret = hashlib.sha256(config.CRYPTO_PAY_TOKEN.encode()).digest()
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    sent = Sent()
    with fake_bot(sent):
        assert client.post("/api/pay/crypto", content=body, headers={"crypto-pay-api-signature": sig}).status_code == 200
    assert db.is_resident(run(db.get_user(uid)))


def test_access_check_polls_crypto(client):
    uid = 3002
    client.get("/api/bootstrap", headers=headers(uid))
    with patch("cc.payments.crypto_call", AsyncMock(return_value={"invoice_id": 888, "bot_invoice_url": "https://t.me/CryptoBot?start=x"})):
        client.post("/api/checkout", json={"tariff": "base", "method": "crypto"}, headers=headers(uid))
    sent = Sent()
    with fake_bot(sent), patch("cc.payments.crypto_call", AsyncMock(return_value={"items": [{"invoice_id": 888, "status": "paid"}]})):
        r = client.post("/api/access/check", headers=headers(uid))
    assert r.json()["access"]["resident"] is True


# ---------- Напоминания и окончание доступа ----------

def test_abandoned_checkout_reminder_once():
    uid = 4001
    run(db.upsert_user(uid, "abandon", "А", started=True))
    pid = run(db.create_payment(uid, "base", "card", 2990, "RUB", 30))

    async def age():
        async with db.connect() as conn:
            await conn.execute("UPDATE payments SET created_at=created_at-200 WHERE id=?", (pid,))
            await conn.commit()
    run(age())
    sent = Sent()
    with fake_bot(sent):
        run(access.process_abandoned())
        run(access.process_abandoned())
    mine = [m for m in sent.messages if m[0] == uid]
    assert len(mine) == 1 and "открывал оплату" in mine[0][1]
    buttons = [b.text for row in mine[0][2]["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["Открыть C&C", "Написать лично"]


def test_no_reminder_for_fresh_or_paid():
    uid = 4002
    run(db.upsert_user(uid, "fresh", "Ф", started=True))
    run(db.create_payment(uid, "base", "card", 2990, "RUB", 30))  # только что
    sent = Sent()
    with fake_bot(sent):
        run(access.process_abandoned())
    assert not [m for m in sent.messages if m[0] == uid]


def test_expiry_warns_then_kicks_and_closes_modules():
    from modules.parser import db as parser_db
    uid = 5001
    run(db.upsert_user(uid, "exp", "Е", started=True))
    sent = Sent()
    with fake_bot(sent), patch("cc.access.kick", AsyncMock()) as kick:
        run(access.grant(uid, "base", 30, notify=False, eval_credits=0))
        assert parser_db.is_member(run(parser_db.get_user(uid)))

        async def shift(seconds):
            async with db.connect() as conn:
                await conn.execute("UPDATE users SET access_until=? WHERE id=?", (int(time.time()) + seconds, uid))
                await conn.commit()
        run(shift(2 * 86400))
        run(access.process_expiry())
        assert any(m[0] == uid and "заканчивается" in m[1] for m in sent.messages)
        run(shift(-10))
        run(access.process_expiry())
        kick.assert_awaited_with(uid)
    assert not db.is_resident(run(db.get_user(uid)))
    assert not parser_db.is_member(run(parser_db.get_user(uid)))
    assert any(m[0] == uid and "закончился" in m[1] for m in sent.messages)


def test_module_access_given_by_module_admin_is_kept():
    """Доступ, выданный в админке парсера, ядро не забирает."""
    from modules.parser import db as parser_db
    uid = 5002
    run(parser_db.grant_member(uid))
    run(access.sync_modules(run(db.upsert_user(uid, "keep", "К"))))
    assert parser_db.is_member(run(parser_db.get_user(uid)))


# ---------- Админка ----------

def test_admin_only(client):
    for path in ("/api/admin/overview", "/api/admin/users", "/api/admin/tariffs", "/api/admin/texts"):
        assert client.get(path, headers=headers(6001)).status_code == 403


def test_admin_grant_revoke_and_lists(client):
    uid = 6002
    client.get("/api/bootstrap", headers=headers(uid))
    a = headers(ADMIN_ID, username="boss_admin")
    sent = Sent()
    with fake_bot(sent), patch("cc.access.kick", AsyncMock()):
        r = client.post(f"/api/admin/users/{uid}/grant", json={"days": 0, "tariff": "base"}, headers=a)
        assert r.json()["user"]["access"]["forever"] is True
        assert client.get("/api/admin/users?filter=residents", headers=a).json()["users"]
        r = client.post(f"/api/admin/users/{uid}/revoke", headers=a)
        assert r.json()["user"]["access"]["resident"] is False
    ov = client.get("/api/admin/overview", headers=a).json()
    assert ov["users"] > 0 and len(ov["days"]) == 14
    assert client.get("/api/admin/payments?status=paid", headers=a).json()["payments"]


def test_admin_tariffs_open_mentor(client):
    a = headers(ADMIN_ID, username="boss_admin")
    tariffs = client.get("/api/admin/tariffs", headers=a).json()["tariffs"]
    for t in tariffs:
        if t["id"] == "mentor":
            t.update(active=True, weekly_seats=1, price=15000)
        if t["id"] == "base":
            t.update(price=3490)
    assert client.put("/api/admin/tariffs", json=tariffs, headers=a).status_code == 200
    boot = client.get("/api/bootstrap", headers=headers(6003)).json()
    base = next(t for t in boot["tariffs"] if t["id"] == "base")
    mentor = next(t for t in boot["tariffs"] if t["id"] == "mentor")
    assert base["price"] == 3490 and mentor["available"] and mentor["seats_left"] == 1
    # вернуть как было, чтобы другие проверки видели исходные цены
    for t in tariffs:
        if t["id"] == "mentor":
            t.update(active=False)
        if t["id"] == "base":
            t.update(price=2990)
    client.put("/api/admin/tariffs", json=tariffs, headers=a)


def test_admin_content_crud_and_review(client):
    a = headers(ADMIN_ID, username="boss_admin")
    item = client.post("/api/admin/content", headers=a, json={
        "kind": "lesson", "module": "Новый", "title": "Тестовый урок", "body": "## Раз\nТекст", "free": True, "position": 999,
    }).json()["item"]
    assert any(l["title"] == "Тестовый урок" for l in client.get("/api/bootstrap", headers=headers(6004)).json()["lessons"])
    client.put(f"/api/admin/content/{item['id']}", headers=a, json={**{k: item[k] for k in ("kind", "module", "body", "icon", "position", "minutes")},
                                                                    "title": "Скрытый", "free": True, "published": False})
    assert client.get(f"/api/content/{item['id']}", headers=headers(6004)).status_code == 404
    assert client.delete(f"/api/admin/content/{item['id']}", headers=a).json()["ok"]
    client.post("/api/admin/content", headers=a, json={"kind": "review", "title": "Иван", "subtitle": "барбершоп, Казань",
                                                       "body": "Первый сайт сдал за неделю", "free": True})
    assert client.get("/api/bootstrap", headers=headers(6004)).json()["reviews"][0]["name"] == "Иван"


def test_deleted_seed_does_not_come_back(client):
    a = headers(ADMIN_ID, username="boss_admin")
    prompts = client.get("/api/admin/content?kind=prompt", headers=a).json()["items"]
    client.delete(f"/api/admin/content/{prompts[-1]['id']}", headers=a)
    from cc.content_seed import ITEMS
    assert run(db.seed_content(ITEMS)) == 0


def test_admin_texts_override(client):
    a = headers(ADMIN_ID, username="boss_admin")
    r = client.put("/api/admin/texts/fallback", json={"text": "Всё в <b>приложении</b> <script>x</script>"}, headers=a)
    assert "<script>" not in r.json()["text"] and "<b>приложении</b>" in r.json()["text"]
    assert "приложении" in run(access.text("fallback"))
    client.put("/api/admin/texts/fallback", json={"text": ""}, headers=a)
    assert "Бот только открывает приложение" in run(access.text("fallback"))


def test_members_manual(client):
    a = headers(ADMIN_ID, username="boss_admin")
    client.put("/api/admin/settings", json={"members_manual": 265}, headers=a)
    assert client.get("/api/bootstrap", headers=headers(6005)).json()["community"]["members"] == 265
    client.put("/api/admin/settings", json={"members_manual": 0}, headers=a)


# ---------- Оценка работ из приложения ----------

def test_eval_submit_from_app(client):
    uid = 7001
    client.get("/api/bootstrap", headers=headers(uid))
    media = [{"type": "photo", "file_id": "F1", "size": 10}]
    with patch("cc.api._store_media", AsyncMock(return_value=media)) as store, \
         patch("modules.evaluation.bot.say", AsyncMock()), \
         patch("modules.evaluation.bot.notify_admins_new", AsyncMock()) as notify:
        r = client.post("/api/eval/submit", headers=headers(uid), data={"url": "mysite.ru", "comment": "посмотрите запись"},
                        files=[("files", ("a.png", b"\x89PNG....", "image/png"))])
        assert r.status_code == 200, r.text
        assert store.await_count == 1
    assert r.json()["quota"]["free_left"] == 1
    mine = client.get("/api/eval", headers=headers(uid)).json()
    assert mine["reviews"][0]["url"] == "mysite.ru"
    assert notify.call_count <= 1


def test_eval_rejects_bad_files(client):
    r = client.post("/api/eval/submit", headers=headers(7002), files=[("files", ("a.txt", b"hi", "text/plain"))])
    assert r.status_code == 422


# ---------- Модули на своих адресах ----------

def test_modules_mounted(client):
    assert client.get("/parser/api/me", headers=headers(8001)).status_code == 200
    assert client.get("/eval/api/me", headers=headers(8001)).status_code == 403   # админка оценок — только админам
    for path in ("/", "/parser/", "/eval/", "/cc/embed.js", "/icons.js", "/fonts/Onest.woff"):
        assert client.get(path).status_code == 200, path


def test_resident_unlocks_parser_trial(client):
    uid = 8002
    client.get("/api/bootstrap", headers=headers(uid))
    assert client.get("/parser/api/me", headers=headers(uid)).json()["access"]["plan"] == "trial"
    sent = Sent()
    with fake_bot(sent):
        run(access.grant(uid, "base", 30, notify=False))
    assert client.get("/parser/api/me", headers=headers(uid)).json()["access"]["plan"] == "member"


def test_join_link_points_to_main_app():
    from modules.parser import config as pconf
    assert pconf.JOIN_URL == "https://t.me/CodeAndCash_bot?startapp=join"
    assert pconf.WEBAPP_URL == "https://cc.example.com/parser/"
    assert str(pconf.DB_PATH).endswith("parser.db")


def test_content_helpers():
    body = "Вступление про сайт.\n\n## Первый\nтекст\n\n## Второй\n- пункт"
    assert content.outline(body) == ["Первый", "Второй"]
    assert content.intro(body) == "Вступление про сайт."
    assert payments.expected_total({"method": "stars", "amount": 35}) == 35
    assert payments.expected_total({"method": "card", "amount": 2990}) == 299000


# ---------- Tribute и группа с заявками ----------

def _set_tribute(client, link, tid):
    a = headers(ADMIN_ID, username="boss_admin")
    tariffs = client.get("/api/admin/tariffs", headers=a).json()["tariffs"]
    for t in tariffs:
        if t["id"] == "base":
            t.update(tribute_link=link, tribute_id=tid)
    assert client.put("/api/admin/tariffs", json=tariffs, headers=a).status_code == 200


def _tribute_post(client, payload, good=True):
    body = json.dumps(payload).encode()
    sig = hmac.new(config.TRIBUTE_API_KEY.encode(), body, hashlib.sha256).hexdigest() if good else "bad"
    return client.post("/api/pay/tribute", content=body, headers={"trbt-signature": sig})


def test_tribute_product_payment(client):
    config.TRIBUTE_API_KEY = "tribute_test_key"
    _set_tribute(client, "https://t.me/tribute/app?startapp=pAbC", 4242)
    uid = 9101
    boot = client.get("/api/bootstrap", headers=headers(uid)).json()
    assert next(t for t in boot["tariffs"] if t["id"] == "base")["card"] is True
    r = client.post("/api/checkout", json={"tariff": "base", "method": "card"}, headers=headers(uid)).json()
    assert r["kind"] == "link" and r["url"] == "https://t.me/tribute/app?startapp=pAbC"

    event = {"name": "new_digital_product", "created_at": "2026-10-10T10:00:00Z", "sent_at": "2026-10-10T10:00:01Z",
             "payload": {"product_id": 4242, "product_name": "C&C", "amount": 299000, "currency": "rub",
                         "purchase_id": 77, "transaction_id": 1, "purchase_created_at": "2026-10-10T10:00:00Z",
                         "telegram_user_id": uid}}
    assert _tribute_post(client, event, good=False).status_code == 401
    sent = Sent()
    with fake_bot(sent):
        assert _tribute_post(client, event).status_code == 200
        assert _tribute_post(client, event).status_code == 200   # повтор от Tribute
    user = run(db.get_user(uid))
    assert db.is_resident(user) and user["access_until"] < time.time() + 31 * 86400
    paid = [p for p in run(db.list_payments("paid", 500)) if p["user_id"] == uid]
    assert len(paid) == 1 and paid[0]["method"] == "tribute" and paid[0]["amount"] == 2990
    assert sum(1 for m in sent.messages if m[0] == uid and "Оплата прошла" in (m[1] or "")) == 1


def test_tribute_subscription_until_date(client):
    config.TRIBUTE_API_KEY = "tribute_test_key"
    uid = 9102
    until = "2030-01-15T12:00:00Z"
    event = {"name": "new_subscription", "payload": {"subscription_name": "C&C", "subscription_id": 4242, "period_id": 1,
             "period": "monthly", "price": 299000, "amount": 260000, "currency": "rub", "user_id": 1, "trb_user_id": "x",
             "telegram_user_id": uid, "channel_id": 1, "channel_name": "C&C", "expires_at": until}}
    with fake_bot(Sent()):
        assert _tribute_post(client, event).status_code == 200
    user = run(db.get_user(uid))
    assert user["access_until"] == 1894708800 and db.is_resident(user)


def test_join_request_guest_then_paid_approves():
    from cc.bot import join_request
    config.GROUP_ID = -100777
    uid = 9201
    calls = []

    class Req:
        chat = type("C", (), {"id": -100777})()
        from_user = type("U", (), {"id": uid, "username": "jr", "first_name": "Ж", "last_name": None})()
        user_chat_id = uid

        async def approve(self):
            calls.append("approve")

    sent = Sent()
    try:
        with fake_bot(sent):
            run(join_request(Req()))
            assert calls == [] and run(db.get_user(uid))["join_requested"] == 1
            assert any(m[0] == uid and "для резидентов" in m[1] for m in sent.messages)
            with patch("cc.tg.bot.approve_chat_join_request", AsyncMock(return_value=True)) as approve, \
                 patch("cc.access.group_status", AsyncMock(return_value=False)):
                run(access.grant(uid, "base", 30, eval_credits=0))
            approve.assert_awaited_once()
            assert any(m[0] == uid and "ты уже внутри" in m[1] for m in sent.messages)
            run(join_request(Req()))     # резидент — сразу внутрь
            assert calls == ["approve"]
    finally:
        config.GROUP_ID = None


# ---------- Скиллы, плагины, памятки, промпты, чат резидентов ----------

def test_skills_plugins_prompts_catalog(client):
    d = client.get("/api/bootstrap", headers=headers(1301)).json()
    c = d["counts"]
    assert c["skill"] >= 80 and c["plugin"] >= 30 and 50 <= c["prompt"] <= 100 and c["material"] == 10
    assert d["links"]["chat"] == ""                       # гостю ссылку на чат не отдаём
    skills = client.get("/api/content?kind=skill", headers=headers(1301)).json()["items"]
    assert sum(s["free"] for s in skills) == 10
    authored = [s for s in skills if s["module"] == "Авторские C&C"]
    assert len(authored) == 10 and all(s["locked"] for s in authored)
    assert any(s["module"] == "Сайты: UI и UX" for s in skills)
    prompts = client.get("/api/content?kind=prompt", headers=headers(1301)).json()["items"]
    assert sum(p["free"] for p in prompts) == 10 and all(p["module"] for p in prompts)
    # бесплатный скилл открыт и содержит команду установки
    free = next(s for s in skills if s["free"])
    body = client.get(f"/api/content/{free['id']}", headers=headers(1301)).json()["body"]
    assert "npx skills add" in body and "github.com/" in body
    # авторский закрыт: видно описание, текста SKILL.md нет
    closed = client.get(f"/api/content/{authored[0]['id']}", headers=headers(1301)).json()
    assert closed["locked"] and closed["body"] == "" and closed["intro"]
    guides = client.get("/api/content?kind=guide", headers=headers(1301)).json()["items"]
    assert {g["module"] for g in guides} >= {"Скиллы", "Плагины"} and not any(g["locked"] for g in guides)
    plugins = client.get("/api/content?kind=plugin", headers=headers(1301)).json()["items"]
    pfree = next(p for p in plugins if p["free"])
    assert "@claude-plugins-official" in client.get(f"/api/content/{pfree['id']}", headers=headers(1301)).json()["body"]


def test_resident_gets_chat_link(client):
    run(access.grant(1302, "base", 30, notify=False, eval_credits=0))
    d = client.get("/api/bootstrap", headers=headers(1302)).json()
    assert d["links"]["chat"] == config.CHAT_LINK and d["links"]["chat"].startswith("https://t.me/+")


def test_chat_join_request_guest_then_paid_approves():
    from cc.bot import join_request
    config.GROUP_ID, config.CHAT_ID = -100777, -100888
    uid = 9301
    calls = []

    class Req:
        chat = type("C", (), {"id": -100888})()
        from_user = type("U", (), {"id": uid, "username": "cj", "first_name": "Ч", "last_name": None})()
        user_chat_id = uid

        async def approve(self):
            calls.append("approve")

    sent = Sent()
    try:
        with fake_bot(sent):
            run(join_request(Req()))
            user = run(db.get_user(uid))
            assert calls == [] and user["chat_requested"] == -100888 and user["join_requested"] == 0
            assert any(m[0] == uid and "Чат резидентов" in m[1] for m in sent.messages)
            with patch("cc.tg.bot.approve_chat_join_request", AsyncMock(return_value=True)) as approve, \
                 patch("cc.access.group_status", AsyncMock(return_value=True)):
                run(access.grant(uid, "base", 30, eval_credits=0))
            approve.assert_awaited_once_with(-100888, uid)
            assert run(db.get_user(uid))["chat_requested"] == 0
            run(join_request(Req()))
            assert calls == ["approve"]
    finally:
        config.GROUP_ID, config.CHAT_ID = None, None


def test_old_prompts_get_sections():
    async def go():
        async with db.connect() as conn:
            await conn.execute("UPDATE content SET module='' WHERE slug='prompt-landing'")
            await conn.commit()
        from cc.content_seed import ITEMS
        await db.seed_content(ITEMS)
        return [i for i in await db.list_content("prompt") if i["slug"] == "prompt-landing"][0]
    assert run(go())["module"] == "Сайты"


def test_parser_own_scripts_library(client):
    h = headers(1303)
    r = client.post("/parser/api/scripts", json={"niche": 2, "kind": "call", "title": "Звонок — мой вариант", "body": "Текст"}, headers=h)
    assert r.status_code == 200
    mine = client.get("/parser/api/scripts?own=1", headers=h).json()["scripts"]
    assert len(mine) == 1 and mine[0]["own"] and mine[0]["niche"] == 2
    assert all(s["own"] for s in mine)
    assert len(client.get("/parser/api/scripts?niche=2", headers=h).json()["scripts"]) > 1
