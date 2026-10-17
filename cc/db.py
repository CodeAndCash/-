"""База ядра C&C Family: люди, доступ, платежи, материалы, прогресс, настройки."""
from __future__ import annotations

import json
import re
import time
from contextlib import asynccontextmanager

import aiosqlite

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT, first_name TEXT, last_name TEXT, photo_url TEXT,
  created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL DEFAULT 0,
  started INTEGER NOT NULL DEFAULT 0,        -- нажимал /start (бот может писать)
  blocked_bot INTEGER NOT NULL DEFAULT 0,    -- остановил бота
  banned INTEGER NOT NULL DEFAULT 0,
  notify INTEGER NOT NULL DEFAULT 1,         -- «Бот напишет, когда выйдет урок»
  theme TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',           -- откуда пришёл (параметр /start)
  access_until INTEGER NOT NULL DEFAULT 0,   -- оплачено до (unix), 0 — нет
  access_forever INTEGER NOT NULL DEFAULT 0,
  tariff TEXT NOT NULL DEFAULT '',
  paid_ever INTEGER NOT NULL DEFAULT 0,
  group_member INTEGER NOT NULL DEFAULT 0,   -- состоит в закрытой группе
  group_checked INTEGER NOT NULL DEFAULT 0,
  modules_synced INTEGER NOT NULL DEFAULT 0, -- доступ к парсеру и скриптам выдан ядром
  expiry_warned INTEGER NOT NULL DEFAULT 0,
  expired_done INTEGER NOT NULL DEFAULT 0,
  abandon_at INTEGER NOT NULL DEFAULT 0,     -- когда напоминали о неоконченной оплате
  marathon_notified INTEGER NOT NULL DEFAULT 0,
  join_requested INTEGER NOT NULL DEFAULT 0, -- подал заявку в закрытую группу
  chat_requested INTEGER NOT NULL DEFAULT 0, -- ID чата резидентов, куда подал заявку без доступа
  channel_requested INTEGER NOT NULL DEFAULT 0, -- подал заявку в обязательный канал
  channel_ok_at INTEGER NOT NULL DEFAULT 0,     -- когда последний раз видели его в канале
  lang TEXT NOT NULL DEFAULT ''                 -- язык приложения: ru, uk, en; пусто — как на устройстве
);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, tariff TEXT NOT NULL, method TEXT NOT NULL,
  amount REAL NOT NULL, currency TEXT NOT NULL, days INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',    -- pending | paid | expired | cancelled
  external_id TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL, paid_at INTEGER NOT NULL DEFAULT 0,
  reminded INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS payments_user ON payments(user_id, status);
CREATE INDEX IF NOT EXISTS payments_status ON payments(status, created_at);
CREATE TABLE IF NOT EXISTS content (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,          -- lesson | material | prompt | resource | marathon | review | post
  slug TEXT UNIQUE,
  module TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL, subtitle TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  icon TEXT NOT NULL DEFAULT '',
  free INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1,
  minutes INTEGER NOT NULL DEFAULT 0,
  media TEXT NOT NULL DEFAULT '[]',   -- картинки (подборки с сайтами), JSON-список адресов
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS content_kind ON content(kind, position);
CREATE TABLE IF NOT EXISTS progress (
  user_id INTEGER NOT NULL, content_id INTEGER NOT NULL, done_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, content_id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, created_at);
"""

USER_COLUMNS = {
    "photo_url": "TEXT", "abandon_at": "INTEGER NOT NULL DEFAULT 0",
    "marathon_notified": "INTEGER NOT NULL DEFAULT 0", "expired_done": "INTEGER NOT NULL DEFAULT 0",
    "join_requested": "INTEGER NOT NULL DEFAULT 0", "chat_requested": "INTEGER NOT NULL DEFAULT 0",
    "channel_requested": "INTEGER NOT NULL DEFAULT 0", "channel_ok_at": "INTEGER NOT NULL DEFAULT 0",
    "lang": "TEXT NOT NULL DEFAULT ''",
}


def now() -> int:
    return int(time.time())


@asynccontextmanager
async def connect():
    db = await aiosqlite.connect(config.CORE_DB, timeout=30)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA busy_timeout=30000")
        yield db
    finally:
        await db.close()


async def init() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with connect() as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(SCHEMA)
        cols = {row[1] for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
        for name, kind in USER_COLUMNS.items():
            if name not in cols:
                await db.execute(f"ALTER TABLE users ADD COLUMN {name} {kind}")
        ccols = {row[1] for row in await (await db.execute("PRAGMA table_info(content)")).fetchall()}
        if "media" not in ccols:
            await db.execute("ALTER TABLE content ADD COLUMN media TEXT NOT NULL DEFAULT '[]'")
        await db.commit()


def _row(row) -> dict | None:
    return dict(row) if row is not None else None


# ---------- Настройки (тарифы, тексты, ручные значения) ----------

async def get_setting(key: str, default=None):
    async with connect() as db:
        row = await (await db.execute("SELECT value FROM settings WHERE key=?", (key,))).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return default


async def set_setting(key: str, value) -> None:
    async with connect() as db:
        await db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        await db.commit()


# ---------- Люди ----------

async def upsert_user(uid: int, username: str | None = None, first_name: str | None = None,
                      last_name: str | None = None, photo_url: str | None = None, started: bool = False,
                      source: str = "") -> dict:
    ts = now()
    async with connect() as db:
        await db.execute(
            """INSERT INTO users(id, username, first_name, last_name, photo_url, created_at, last_seen, started, source)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 username=COALESCE(excluded.username, users.username),
                 first_name=COALESCE(excluded.first_name, users.first_name),
                 last_name=COALESCE(excluded.last_name, users.last_name),
                 photo_url=COALESCE(excluded.photo_url, users.photo_url),
                 last_seen=excluded.last_seen,
                 started=MAX(users.started, excluded.started),
                 blocked_bot=CASE WHEN excluded.started=1 THEN 0 ELSE users.blocked_bot END,
                 source=CASE WHEN users.source='' THEN excluded.source ELSE users.source END""",
            (uid, username, first_name, last_name, photo_url, ts, ts, int(started), source[:64]),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
    return dict(row)


async def get_user(uid: int) -> dict | None:
    async with connect() as db:
        return _row(await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone())


async def find_user(query: str) -> dict | None:
    query = (query or "").strip().lstrip("@")
    async with connect() as db:
        if query.isdigit():
            row = await (await db.execute("SELECT * FROM users WHERE id=?", (int(query),))).fetchone()
        else:
            row = await (await db.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (query,))).fetchone()
    return _row(row)


async def update_user(uid: int, **fields) -> None:
    if not fields:
        return
    allowed = {"notify", "theme", "banned", "blocked_bot", "group_member", "group_checked", "modules_synced",
               "expiry_warned", "expired_done", "abandon_at", "marathon_notified", "access_until",
               "access_forever", "tariff", "paid_ever", "started", "join_requested", "chat_requested",
               "channel_requested", "channel_ok_at", "lang"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"unknown fields {bad}")
    sets = ", ".join(f"{k}=?" for k in fields)
    async with connect() as db:
        await db.execute(f"UPDATE users SET {sets} WHERE id=?", (*fields.values(), uid))
        await db.commit()


def has_paid_access(user: dict, ts: int | None = None) -> bool:
    return bool(user.get("access_forever")) or int(user.get("access_until") or 0) > (ts or now())


def is_resident(user: dict | None) -> bool:
    """Резидент: оплачен доступ, или человек в закрытой группе, или админ."""
    if not user or user.get("banned"):
        return False
    if config.is_admin_user(user.get("id"), user.get("username")):
        return True
    return has_paid_access(user) or bool(user.get("group_member"))


async def extend_access(uid: int, tariff: str, days: int) -> dict:
    """Продлевает доступ: days=0 — навсегда. Возвращает обновлённого человека."""
    ts = now()
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        if row is None:
            await db.execute("INSERT INTO users(id, created_at, last_seen) VALUES(?, ?, ?)", (uid, ts, ts))
            row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        if days <= 0:
            await db.execute(
                "UPDATE users SET access_forever=1, tariff=?, paid_ever=1, expiry_warned=0, expired_done=0 WHERE id=?",
                (tariff, uid))
        else:
            base = max(ts, int(row["access_until"] or 0))
            await db.execute(
                "UPDATE users SET access_until=?, tariff=?, paid_ever=1, expiry_warned=0, expired_done=0 WHERE id=?",
                (base + days * 86400, tariff, uid))
        await db.commit()
        return dict(await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone())


async def access_until(uid: int, tariff: str, until: int) -> dict:
    """Доступ до конкретной даты (подписка Tribute). Уже оплаченный дольше срок не укорачивается."""
    ts = now()
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO users(id, created_at, last_seen) VALUES(?, ?, ?)", (uid, ts, ts))
        await db.execute(
            "UPDATE users SET access_until=MAX(access_until, ?), tariff=?, paid_ever=1, expiry_warned=0, expired_done=0 "
            "WHERE id=?", (until, tariff, uid))
        await db.commit()
        return dict(await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone())


async def revoke_access(uid: int) -> None:
    async with connect() as db:
        await db.execute(
            "UPDATE users SET access_until=0, access_forever=0, group_member=0, expired_done=1 WHERE id=?", (uid,))
        await db.commit()


async def list_users(query: str = "", filt: str = "all", limit: int = 100, offset: int = 0) -> list[dict]:
    where, args = ["1=1"], []
    query = (query or "").strip().lstrip("@")
    if query:
        if query.isdigit():
            where.append("id=?")
            args.append(int(query))
        else:
            where.append("(lower(username) LIKE ? OR lower(first_name) LIKE ? OR lower(last_name) LIKE ?)")
            args += [f"%{query.lower()}%"] * 3
    ts = now()
    if filt == "residents":
        where.append("(access_forever=1 OR access_until>? OR group_member=1)")
        args.append(ts)
    elif filt == "guests":
        where.append("access_forever=0 AND access_until<=? AND group_member=0")
        args.append(ts)
    elif filt == "banned":
        where.append("banned=1")
    async with connect() as db:
        rows = await (await db.execute(
            f"SELECT * FROM users WHERE {' AND '.join(where)} ORDER BY last_seen DESC LIMIT ? OFFSET ?",
            (*args, limit, offset))).fetchall()
    return [dict(r) for r in rows]


async def audience(kind: str) -> list[int]:
    """ID для рассылки: all | residents | guests | notify."""
    ts = now()
    sql = "SELECT id FROM users WHERE started=1 AND blocked_bot=0 AND banned=0"
    args: tuple = ()
    if kind == "residents":
        sql += " AND (access_forever=1 OR access_until>? OR group_member=1)"
        args = (ts,)
    elif kind == "guests":
        sql += " AND access_forever=0 AND access_until<=? AND group_member=0"
        args = (ts,)
    elif kind == "notify":
        sql += " AND notify=1"
    async with connect() as db:
        return [r[0] for r in await (await db.execute(sql, args)).fetchall()]


async def residents_count() -> int:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM users WHERE banned=0 AND (access_forever=1 OR access_until>? OR group_member=1)",
            (now(),))).fetchone()
    return int(row[0])


async def users_to_warn(before: int) -> list[dict]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT * FROM users WHERE access_forever=0 AND access_until>? AND access_until<=? AND expiry_warned=0",
            (now(), before))).fetchall()
    return [dict(r) for r in rows]


async def users_expired() -> list[dict]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT * FROM users WHERE access_forever=0 AND access_until>0 AND access_until<=? AND expired_done=0",
            (now(),))).fetchall()
    return [dict(r) for r in rows]


# ---------- Платежи ----------

async def create_payment(uid: int, tariff: str, method: str, amount: float, currency: str, days: int) -> int:
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO payments(user_id, tariff, method, amount, currency, days, created_at) VALUES(?,?,?,?,?,?,?)",
            (uid, tariff, method, amount, currency, days, now()))
        await db.commit()
        return int(cur.lastrowid)


async def set_payment_link(pid: int, external_id: str, url: str) -> None:
    async with connect() as db:
        await db.execute("UPDATE payments SET external_id=?, url=? WHERE id=?", (str(external_id), url, pid))
        await db.commit()


async def get_payment(pid: int) -> dict | None:
    async with connect() as db:
        return _row(await (await db.execute("SELECT * FROM payments WHERE id=?", (pid,))).fetchone())


async def payment_by_external(method: str, external_id: str) -> dict | None:
    async with connect() as db:
        return _row(await (await db.execute(
            "SELECT * FROM payments WHERE method=? AND external_id=?", (method, str(external_id)))).fetchone())


async def mark_paid(pid: int, note: str = "") -> bool:
    """Атомарно переводит платёж в «оплачен». False — уже был оплачен (повтор уведомления)."""
    async with connect() as db:
        cur = await db.execute(
            "UPDATE payments SET status='paid', paid_at=?, note=CASE WHEN ?='' THEN note ELSE ? END "
            "WHERE id=? AND status!='paid'", (now(), note, note, pid))
        await db.commit()
        return cur.rowcount == 1


async def set_payment_status(pid: int, status: str) -> None:
    async with connect() as db:
        await db.execute("UPDATE payments SET status=? WHERE id=? AND status='pending'", (status, pid))
        await db.commit()


async def pending_payments(method: str | None = None, newer_than: int = 0) -> list[dict]:
    sql, args = "SELECT * FROM payments WHERE status='pending' AND created_at>?", [newer_than]
    if method:
        sql += " AND method=?"
        args.append(method)
    async with connect() as db:
        return [dict(r) for r in await (await db.execute(sql, args)).fetchall()]


async def abandoned_checkouts(older_than: int) -> list[dict]:
    """Открыли оплату, не оплатили и ещё не получили напоминание."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT * FROM payments WHERE status='pending' AND reminded=0 AND created_at<=? ORDER BY created_at",
            (older_than,))).fetchall()
    return [dict(r) for r in rows]


async def mark_reminded(uid: int) -> None:
    async with connect() as db:
        await db.execute("UPDATE payments SET reminded=1 WHERE user_id=? AND status='pending'", (uid,))
        await db.commit()


async def paid_after(uid: int, ts: int) -> bool:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT 1 FROM payments WHERE user_id=? AND status='paid' AND paid_at>=?", (uid, ts))).fetchone()
    return row is not None


async def list_payments(status: str = "", limit: int = 100) -> list[dict]:
    sql = ("SELECT p.*, u.username, u.first_name FROM payments p LEFT JOIN users u ON u.id=p.user_id")
    args: list = []
    if status:
        sql += " WHERE p.status=?"
        args.append(status)
    sql += " ORDER BY p.id DESC LIMIT ?"
    args.append(limit)
    async with connect() as db:
        return [dict(r) for r in await (await db.execute(sql, args)).fetchall()]


async def seats_taken(tariff: str, since: int) -> int:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM payments WHERE tariff=? AND status='paid' AND paid_at>=?", (tariff, since))).fetchone()
    return int(row[0])


# ---------- Материалы ----------

CONTENT_FIELDS = ("kind", "slug", "module", "title", "subtitle", "body", "icon", "free", "position",
                  "published", "minutes", "media")


SYNC_FIELDS = ("kind", "module", "title", "subtitle", "body", "icon", "free", "position", "minutes", "media")


async def seed_content(items: list[dict], retired: list[str] | tuple = ()) -> int:
    """Добавляет стартовые материалы, которых ещё нет (по slug). Удалённые админом не возвращаются.
    Материалы, которые админ ни разу не правил, обновляются до свежей версии из кода.
    retired — устаревшие материалы: их скрываем, если админ их не трогал."""
    removed = set(await get_setting("removed_slugs", []) or [])
    added = 0
    ts = now()
    async with connect() as db:
        rows = await (await db.execute("SELECT * FROM content WHERE slug IS NOT NULL")).fetchall()
        have = {r["slug"]: dict(r) for r in rows}
        for item in items:
            values = {k: item.get(k, "" if k not in ("free", "position", "published", "minutes") else 0)
                      for k in CONTENT_FIELDS}
            values["media"] = json.dumps(item.get("media") or [], ensure_ascii=False)
            values["free"] = int(bool(values["free"]))
            old = have.get(item["slug"])
            if old:
                if old["updated_at"] == old["created_at"]:      # админ не правил — обновляем
                    changed = {k: values[k] for k in SYNC_FIELDS if old.get(k) != values[k]}
                    if changed:
                        sets = ", ".join(f"{k}=?" for k in changed)
                        await db.execute(f"UPDATE content SET {sets} WHERE id=?", (*changed.values(), old["id"]))
                elif not old["module"] and item.get("module"):
                    await db.execute("UPDATE content SET module=?, position=? WHERE id=?",
                                     (item["module"], item.get("position", 0), old["id"]))
                continue
            if item["slug"] in removed:
                continue
            if "published" not in item:
                values["published"] = 1
            await db.execute(
                f"INSERT INTO content({', '.join(CONTENT_FIELDS)}, created_at, updated_at) "
                f"VALUES({', '.join('?' * len(CONTENT_FIELDS))}, ?, ?)",
                (*values.values(), ts, ts))
            added += 1
        for slug in retired:
            old = have.get(slug)
            if old and old["published"] and old["updated_at"] == old["created_at"]:
                await db.execute("UPDATE content SET published=0 WHERE id=?", (old["id"],))
        await db.commit()
    return added


async def list_content(kind: str | None = None, published_only: bool = True) -> list[dict]:
    sql, args = "SELECT * FROM content WHERE 1=1", []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if published_only:
        sql += " AND published=1"
    sql += " ORDER BY kind, position, id"
    async with connect() as db:
        return [dict(r) for r in await (await db.execute(sql, args)).fetchall()]


async def get_content(cid: int) -> dict | None:
    async with connect() as db:
        return _row(await (await db.execute("SELECT * FROM content WHERE id=?", (cid,))).fetchone())


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9а-яё]+", "-", (title or "").lower()).strip("-")[:40] or "item"
    return f"{base}-{int(time.time() * 1000) % 10_000_000}"


async def save_content(data: dict, cid: int | None = None) -> int:
    ts = now()
    fields = {k: data[k] for k in CONTENT_FIELDS if k in data and k != "slug"}
    if "media" in fields and not isinstance(fields["media"], str):
        fields["media"] = json.dumps(fields["media"] or [], ensure_ascii=False)
    async with connect() as db:
        if cid:
            sets = ", ".join(f"{k}=?" for k in fields)
            await db.execute(f"UPDATE content SET {sets}, updated_at=? WHERE id=?", (*fields.values(), ts, cid))
            await db.commit()
            return cid
        fields.setdefault("published", 1)
        fields["slug"] = _slugify(data.get("title", ""))
        cols = ", ".join(fields)
        cur = await db.execute(
            f"INSERT INTO content({cols}, created_at, updated_at) VALUES({', '.join('?' * len(fields))}, ?, ?)",
            (*fields.values(), ts, ts))
        await db.commit()
        return int(cur.lastrowid)


async def delete_content(cid: int) -> None:
    item = await get_content(cid)
    if not item:
        return
    async with connect() as db:
        await db.execute("DELETE FROM content WHERE id=?", (cid,))
        await db.execute("DELETE FROM progress WHERE content_id=?", (cid,))
        await db.commit()
    if item.get("slug"):
        removed = list(await get_setting("removed_slugs", []) or [])
        if item["slug"] not in removed:
            removed.append(item["slug"])
            await set_setting("removed_slugs", removed)


async def done_ids(uid: int) -> dict[int, int]:
    async with connect() as db:
        rows = await (await db.execute("SELECT content_id, done_at FROM progress WHERE user_id=?", (uid,))).fetchall()
    return {r[0]: r[1] for r in rows}


async def set_done(uid: int, cid: int, done: bool) -> None:
    async with connect() as db:
        if done:
            await db.execute("INSERT OR IGNORE INTO progress(user_id, content_id, done_at) VALUES(?,?,?)",
                             (uid, cid, now()))
        else:
            await db.execute("DELETE FROM progress WHERE user_id=? AND content_id=?", (uid, cid))
        await db.commit()


async def marathon_participants() -> list[int]:
    """Кто начал марафон (отметил хотя бы один день)."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT DISTINCT p.user_id FROM progress p JOIN content c ON c.id=p.content_id WHERE c.kind='marathon'"
        )).fetchall()
    return [r[0] for r in rows]


# ---------- События и статистика ----------

async def log_event(uid: int, kind: str, data: str = "") -> None:
    async with connect() as db:
        await db.execute("INSERT INTO events(user_id, kind, data, created_at) VALUES(?,?,?,?)",
                         (uid, kind, data[:200], now()))
        await db.commit()


async def overview() -> dict:
    ts = now()
    day = ts - 86400
    week = ts - 7 * 86400
    month = ts - 30 * 86400
    async with connect() as db:
        async def one(sql, *args):
            row = await (await db.execute(sql, args)).fetchone()
            return row[0] or 0

        users = await one("SELECT COUNT(*) FROM users")
        started = await one("SELECT COUNT(*) FROM users WHERE started=1")
        residents = await one(
            "SELECT COUNT(*) FROM users WHERE banned=0 AND (access_forever=1 OR access_until>? OR group_member=1)", ts)
        new_day = await one("SELECT COUNT(*) FROM users WHERE created_at>?", day)
        new_week = await one("SELECT COUNT(*) FROM users WHERE created_at>?", week)
        active_day = await one("SELECT COUNT(*) FROM users WHERE last_seen>?", day)
        active_week = await one("SELECT COUNT(*) FROM users WHERE last_seen>?", week)
        revenue_month = await one(
            "SELECT SUM(amount) FROM payments WHERE status='paid' AND currency='RUB' AND paid_at>?", month)
        revenue_all = await one("SELECT SUM(amount) FROM payments WHERE status='paid' AND currency='RUB'")
        paid_month = await one("SELECT COUNT(*) FROM payments WHERE status='paid' AND paid_at>?", month)
        checkouts_month = await one(
            "SELECT COUNT(DISTINCT user_id) FROM payments WHERE created_at>?", month)
        buyers_month = await one(
            "SELECT COUNT(DISTINCT user_id) FROM payments WHERE status='paid' AND paid_at>?", month)
        lessons_done = await one("SELECT COUNT(*) FROM progress")
        days = []
        for i in range(13, -1, -1):
            start = ts - (i + 1) * 86400
            end = ts - i * 86400
            days.append({
                "new": await one("SELECT COUNT(*) FROM users WHERE created_at>? AND created_at<=?", start, end),
                "paid": await one("SELECT COUNT(*) FROM payments WHERE status='paid' AND paid_at>? AND paid_at<=?",
                                  start, end),
            })
    return {
        "users": users, "started": started, "residents": residents, "new_day": new_day, "new_week": new_week,
        "active_day": active_day, "active_week": active_week, "revenue_month": revenue_month,
        "revenue_all": revenue_all, "paid_month": paid_month, "checkouts_month": checkouts_month,
        "buyers_month": buyers_month, "lessons_done": lessons_done, "days": days,
    }
