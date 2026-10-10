"""SQLite-хранилище Script C&C: пользователи, лимиты, ключи, библиотека скриптов, мои скрипты."""

from __future__ import annotations

import time
from datetime import date

import aiosqlite

from .config import ADMIN_IDS, ADMIN_USERNAMES, DB_PATH, MEMBER_DAILY_LIMIT, TRIAL_GENERATIONS, is_admin_user

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 0,
  daily_limit INTEGER NOT NULL DEFAULT 20,
  created_at INTEGER NOT NULL,
  banned INTEGER NOT NULL DEFAULT 0,
  trial_used INTEGER NOT NULL DEFAULT 0,
  bonus INTEGER NOT NULL DEFAULT 0,
  deleted INTEGER NOT NULL DEFAULT 0,
  bot_started_at INTEGER,
  app_opened_at INTEGER
);
CREATE TABLE IF NOT EXISTS usage(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  cnt INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS api_usage(
  provider TEXT NOT NULL,
  month TEXT NOT NULL,
  cnt INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(provider, month)
);
CREATE TABLE IF NOT EXISTS source_errors(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS access_keys(
  code TEXT PRIMARY KEY,
  for_user TEXT NOT NULL DEFAULT '',
  daily_limit INTEGER NOT NULL DEFAULT 20,
  bonus INTEGER NOT NULL DEFAULT 0,
  uses_left INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  used_by TEXT NOT NULL DEFAULT '',
  used_at INTEGER
);
CREATE TABLE IF NOT EXISTS library(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  free INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS saved(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  niche TEXT NOT NULL DEFAULT '',
  purpose TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_owner ON saved(owner_id);
CREATE TABLE IF NOT EXISTS generations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  niche TEXT NOT NULL DEFAULT '',
  purpose TEXT NOT NULL DEFAULT '',
  channel TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'ai',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gen_user ON generations(user_id);
CREATE INDEX IF NOT EXISTS idx_gen_time ON generations(created_at);
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


async def conn() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


def today() -> str:
    return date.today().isoformat()


def _period(kind: str) -> str:
    return date.today().strftime("%Y-%m") if kind == "month" else date.today().isoformat()


# Лимит генераций по умолчанию для новых участников. Владелец меняет его в админке (хранится в meta),
# переменная MEMBER_DAILY_LIMIT в Railway — только начальное значение.
_DEFAULTS = {"limit": MEMBER_DAILY_LIMIT}


def default_limit() -> int:
    return _DEFAULTS["limit"]


async def set_default_limit(value: int, scope: str = "standard") -> int:
    """scope: new — только новым; standard — ещё и тем, у кого стоял прежний стандартный лимит;
    all — всем участникам, кроме владельца. Возвращает, скольким поменяли лимит."""
    old = default_limit()
    db = await conn()
    try:
        await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('default_limit', ?)", (str(value),))
        changed = 0
        if scope == "all":
            changed = (await db.execute("UPDATE users SET daily_limit=? WHERE is_admin=0", (value,))).rowcount
        elif scope == "standard" and old != value:
            changed = (await db.execute(
                "UPDATE users SET daily_limit=? WHERE is_admin=0 AND daily_limit=?", (value, old)
            )).rowcount
        await db.commit()
        _DEFAULTS["limit"] = value
        return max(0, changed)
    finally:
        await db.close()


async def init() -> None:
    db = await conn()
    try:
        await db.executescript(SCHEMA)
        saved = await (await db.execute("SELECT value FROM meta WHERE key='default_limit'")).fetchone()
        try:
            _DEFAULTS["limit"] = max(0, min(5000, int(saved["value"]))) if saved else MEMBER_DAILY_LIMIT
        except (TypeError, ValueError):
            _DEFAULTS["limit"] = MEMBER_DAILY_LIMIT
        # Права владельца даёт только ADMIN_IDS / ADMIN_USERNAMES.
        await db.execute("UPDATE users SET is_admin=0")
        for admin_id in ADMIN_IDS:
            await db.execute(
                """
                INSERT INTO users(id, is_admin, approved, daily_limit, created_at)
                VALUES(?, 1, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET is_admin=1, approved=1
                """,
                (admin_id, max(MEMBER_DAILY_LIMIT, 1000), int(time.time())),
            )
        for name in ADMIN_USERNAMES:
            await db.execute(
                "UPDATE users SET is_admin=1, approved=1, banned=0, deleted=0, "
                "daily_limit=MAX(daily_limit, 1000) WHERE lower(username)=?",
                (name,),
            )
        await db.commit()
    finally:
        await db.close()


# ---------- Пользователи ----------

async def upsert_user(uid: int, username: str | None, first_name: str | None) -> dict:
    db = await conn()
    try:
        admin = int(is_admin_user(uid, username))
        await db.execute(
            """
            INSERT INTO users(id, username, first_name, approved, is_admin, daily_limit, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
            """,
            (uid, username, first_name, admin, admin, default_limit(), int(time.time())),
        )
        if admin:
            await db.execute(
                "UPDATE users SET is_admin=1, approved=1, banned=0, deleted=0, "
                "daily_limit=MAX(daily_limit, 1000) WHERE id=?",
                (uid,),
            )
        else:
            await db.execute("UPDATE users SET is_admin=0 WHERE id=? AND is_admin=1", (uid,))
        await db.commit()
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_user(uid: int) -> dict | None:
    db = await conn()
    try:
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


def is_member(user: dict) -> bool:
    return bool(user.get("approved") or user.get("is_admin") or user.get("id") in ADMIN_IDS)


def trial_left(user: dict, trial: int = TRIAL_GENERATIONS) -> int:
    return max(0, trial + int(user.get("bonus") or 0) - int(user.get("trial_used") or 0))


async def used_today(uid: int) -> int:
    db = await conn()
    try:
        row = await (
            await db.execute("SELECT cnt FROM usage WHERE user_id=? AND day=?", (uid, today()))
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        await db.close()


async def reserve_generation(uid: int) -> tuple[str, str, str]:
    """Атомарно списывает одну генерацию.

    Возвращает (статус, вид, день): статус — ok | trial_over | limit | banned | missing;
    вид — member | trial (нужен для возврата при ошибке)."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        user = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        if not user:
            await db.rollback()
            return "missing", "", ""
        user = dict(user)
        if user["banned"] and not is_admin_user(uid, user.get("username")):
            await db.rollback()
            return "banned", "", ""
        if is_member(user):
            day = today()
            await db.execute("INSERT OR IGNORE INTO usage(user_id, day, cnt) VALUES(?, ?, 0)", (uid, day))
            row = await (
                await db.execute("SELECT cnt FROM usage WHERE user_id=? AND day=?", (uid, day))
            ).fetchone()
            if int(row["cnt"]) >= int(user["daily_limit"]):
                # Дневной лимит кончился — тратим бонусные генерации, если они есть.
                if int(user.get("bonus") or 0) > 0:
                    await db.execute("UPDATE users SET bonus=bonus-1 WHERE id=?", (uid,))
                    await db.commit()
                    return "ok", "bonus", day
                await db.rollback()
                return "limit", "member", day
            await db.execute("UPDATE usage SET cnt=cnt+1 WHERE user_id=? AND day=?", (uid, day))
            await db.commit()
            return "ok", "member", day
        if trial_left(user) <= 0:
            await db.rollback()
            return "trial_over", "trial", ""
        await db.execute("UPDATE users SET trial_used=trial_used+1 WHERE id=?", (uid,))
        await db.commit()
        return "ok", "trial", ""
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def refund_generation(uid: int, kind: str, day: str) -> None:
    db = await conn()
    try:
        if kind == "member" and day:
            await db.execute("UPDATE usage SET cnt=MAX(0, cnt-1) WHERE user_id=? AND day=?", (uid, day))
        elif kind == "trial":
            await db.execute("UPDATE users SET trial_used=MAX(0, trial_used-1) WHERE id=?", (uid,))
        elif kind == "bonus":
            await db.execute("UPDATE users SET bonus=bonus+1 WHERE id=?", (uid,))
        await db.commit()
    finally:
        await db.close()


async def reserve_api_call(provider: str, limit: int, *, period: str = "day", amount: int = 1) -> bool:
    """Атомарно учитывает запрос к нейросети. False, если лимит периода исчерпан."""
    key = _period(period)
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("INSERT OR IGNORE INTO api_usage(provider, month, cnt) VALUES(?, ?, 0)", (provider, key))
        row = await (
            await db.execute("SELECT cnt FROM api_usage WHERE provider=? AND month=?", (provider, key))
        ).fetchone()
        if int(row["cnt"]) + amount > limit:
            await db.rollback()
            return False
        await db.execute(
            "UPDATE api_usage SET cnt=cnt+? WHERE provider=? AND month=?", (amount, provider, key)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def refund_api_call(provider: str, *, period: str = "day") -> None:
    db = await conn()
    try:
        await db.execute(
            "UPDATE api_usage SET cnt=MAX(0, cnt-1) WHERE provider=? AND month=?", (provider, _period(period))
        )
        await db.commit()
    finally:
        await db.close()


async def api_calls(provider: str, period: str = "day") -> int:
    db = await conn()
    try:
        row = await (
            await db.execute("SELECT cnt FROM api_usage WHERE provider=? AND month=?", (provider, _period(period)))
        ).fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        await db.close()


async def set_limit(uid: int, value: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute("UPDATE users SET daily_limit=? WHERE id=?", (value, uid))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def set_approved(uid: int, approved: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute("UPDATE users SET approved=? WHERE id=? AND is_admin=0", (approved, uid))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def grant_member(uid: int, daily_limit: int | None = None) -> None:
    db = await conn()
    try:
        await db.execute(
            """
            INSERT INTO users(id, approved, daily_limit, created_at) VALUES(?, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET approved=1, banned=0, deleted=0,
              daily_limit=COALESCE(?, daily_limit)
            """,
            (uid, daily_limit or default_limit(), int(time.time()), daily_limit),
        )
        await db.commit()
    finally:
        await db.close()


async def set_banned(uid: int, banned: bool) -> bool:
    db = await conn()
    try:
        if banned:
            cur = await db.execute("UPDATE users SET banned=1 WHERE id=? AND is_admin=0", (uid,))
        else:  # разбан возвращает и «удалённого» участника в списки
            cur = await db.execute("UPDATE users SET banned=0, deleted=0 WHERE id=?", (uid,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def add_bonus(uid: int, amount: int) -> int | None:
    """Добавляет (или убирает при отрицательном amount) бонусные генерации."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("UPDATE users SET bonus=MAX(0, bonus+?) WHERE id=?", (amount, uid))
        if cur.rowcount <= 0:
            await db.rollback()
            return None
        row = await (await db.execute("SELECT bonus FROM users WHERE id=?", (uid,))).fetchone()
        await db.commit()
        return int(row["bonus"])
    finally:
        await db.close()


async def find_user(query: str) -> dict | None:
    """Ищет пользователя по числовому ID или @username."""
    value = (query or "").strip()
    db = await conn()
    try:
        if value.isdigit():
            row = await (await db.execute("SELECT * FROM users WHERE id=?", (int(value),))).fetchone()
        else:
            name = value.lstrip("@").lower()
            if not name:
                return None
            row = await (
                await db.execute("SELECT * FROM users WHERE lower(username)=?", (name,))
            ).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_user(uid: int) -> bool:
    """«Удалить» участника: бан + скрыть из списков + убрать его сохранённые скрипты."""
    db = await conn()
    try:
        cur = await db.execute(
            "UPDATE users SET deleted=1, banned=1, approved=0 WHERE id=? AND is_admin=0", (uid,)
        )
        if cur.rowcount > 0:
            await db.execute("DELETE FROM saved WHERE owner_id=?", (uid,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def broadcast_ids() -> list[int]:
    db = await conn()
    try:
        rows = await (await db.execute("SELECT id FROM users WHERE banned=0 AND deleted=0")).fetchall()
        return [row["id"] for row in rows]
    finally:
        await db.close()


async def admin_ids() -> list[int]:
    db = await conn()
    try:
        rows = await (await db.execute("SELECT id FROM users WHERE is_admin=1")).fetchall()
        return [row["id"] for row in rows]
    finally:
        await db.close()


async def mark_bot_started(uid: int) -> None:
    db = await conn()
    try:
        await db.execute(
            "UPDATE users SET bot_started_at=COALESCE(bot_started_at, ?) WHERE id=?", (int(time.time()), uid)
        )
        await db.commit()
    finally:
        await db.close()


async def mark_app_opened(uid: int) -> None:
    db = await conn()
    try:
        await db.execute("UPDATE users SET app_opened_at=? WHERE id=?", (int(time.time()), uid))
        await db.commit()
    finally:
        await db.close()


async def all_users_stats() -> list[dict]:
    db = await conn()
    try:
        rows = await (
            await db.execute(
                """
                SELECT u.id, u.username, u.first_name, u.daily_limit, u.approved, u.is_admin, u.banned,
                  u.trial_used, u.bonus, u.created_at,
                  COALESCE((SELECT cnt FROM usage WHERE user_id=u.id AND day=?), 0) AS today,
                  COALESCE((SELECT COUNT(*) FROM generations WHERE user_id=u.id), 0) AS gens,
                  COALESCE((SELECT COUNT(*) FROM saved WHERE owner_id=u.id), 0) AS saved
                FROM users u WHERE u.deleted=0
                ORDER BY u.approved DESC, gens DESC, u.created_at DESC
                """,
                (today(),),
            )
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def members(query: str = "", limit: int = 500) -> list[dict]:
    """Все, кто запускал бота или открывал мини‑апп (удалённые не показываются)."""
    sql = (
        "SELECT id, username, first_name, created_at, bot_started_at, app_opened_at, banned "
        "FROM users WHERE deleted=0"
    )
    args: list = []
    query = (query or "").strip().lstrip("@")
    if query:
        sql += " AND (CAST(id AS TEXT) LIKE ? OR username LIKE ? OR first_name LIKE ?)"
        like = f"%{query}%"
        args += [like, like, like]
    sql += " ORDER BY COALESCE(app_opened_at, bot_started_at, created_at) DESC LIMIT ?"
    args.append(limit)
    db = await conn()
    try:
        rows = await (await db.execute(sql, args)).fetchall()
    finally:
        await db.close()
    return [
        {
            "id": row["id"],
            "username": row["username"] or "",
            "first_name": row["first_name"] or "",
            "app_opened": bool(row["app_opened_at"]),
            "app_opened_at": row["app_opened_at"],
            "banned": bool(row["banned"]),
        }
        for row in rows
    ]


# ---------- Ключи доступа ----------

async def create_key(
    code: str, for_user: str = "", daily_limit: int | None = None,
    bonus: int = 0, uses: int = 1, note: str = "",
) -> bool:
    db = await conn()
    try:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO access_keys(code, for_user, daily_limit, bonus, uses_left, note, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (code, for_user.strip().lstrip("@").lower(), default_limit() if daily_limit is None else daily_limit,
             bonus, uses, note, int(time.time())),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def list_keys() -> list[dict]:
    db = await conn()
    try:
        rows = await (
            await db.execute("SELECT * FROM access_keys ORDER BY created_at DESC LIMIT 200")
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def delete_key(code: str) -> bool:
    db = await conn()
    try:
        cur = await db.execute("DELETE FROM access_keys WHERE code=?", (code,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def redeem_key(uid: int, username: str | None, code: str) -> tuple[str, dict | None]:
    """Активирует ключ. Результат: ok | not_found | used | other_user | banned."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        key = await (
            await db.execute("SELECT * FROM access_keys WHERE code=?", (code.strip(),))
        ).fetchone()
        if not key:
            await db.rollback()
            return "not_found", None
        key = dict(key)
        user = await (await db.execute("SELECT banned FROM users WHERE id=?", (uid,))).fetchone()
        if user and user["banned"]:
            await db.rollback()
            return "banned", key
        bound = key["for_user"]
        if bound and bound not in (str(uid), (username or "").lower()):
            await db.rollback()
            return "other_user", key
        if key["uses_left"] <= 0:
            await db.rollback()
            return "used", key
        if str(uid) in [part for part in str(key["used_by"] or "").split(",") if part]:
            await db.rollback()
            return "already", key
        await db.execute(
            "UPDATE access_keys SET uses_left=uses_left-1, used_by=?, used_at=? WHERE code=?",
            ((key["used_by"] + "," if key["used_by"] else "") + str(uid), int(time.time()), key["code"]),
        )
        if key["daily_limit"] > 0:
            await db.execute(
                "UPDATE users SET approved=1, banned=0, deleted=0, daily_limit=MAX(daily_limit, ?) WHERE id=?",
                (key["daily_limit"], uid),
            )
        if key["bonus"] > 0:
            await db.execute("UPDATE users SET bonus=bonus+? WHERE id=?", (key["bonus"], uid))
        await db.commit()
        return "ok", key
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


# ---------- Библиотека скриптов (общая, правит владелец) ----------

async def seed_library(items: list[dict]) -> None:
    """Заполняет библиотеку готовыми скриптами один раз. Если владелец всё удалил — не возвращает."""
    db = await conn()
    try:
        done = await (await db.execute("SELECT value FROM meta WHERE key='library_seeded'")).fetchone()
        if done:
            return
        now = int(time.time())
        for index, item in enumerate(items):
            await db.execute(
                "INSERT INTO library(category, title, body, free, sort, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
                (item["category"], item["title"], item["body"], int(item.get("free", 0)), index, now),
            )
        await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('library_seeded', '1')")
        await db.commit()
    finally:
        await db.close()


async def list_library() -> list[dict]:
    db = await conn()
    try:
        rows = await (await db.execute("SELECT * FROM library ORDER BY sort, id")).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_library_item(item_id: int) -> dict | None:
    db = await conn()
    try:
        row = await (await db.execute("SELECT * FROM library WHERE id=?", (item_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def save_library_item(
    category: str, title: str, body: str, free: bool, item_id: int | None = None
) -> int:
    db = await conn()
    try:
        now = int(time.time())
        if item_id:
            await db.execute(
                "UPDATE library SET category=?, title=?, body=?, free=?, updated_at=? WHERE id=?",
                (category, title, body, int(free), now, item_id),
            )
            await db.commit()
            return item_id
        row = await (await db.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM library")).fetchone()
        cur = await db.execute(
            "INSERT INTO library(category, title, body, free, sort, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (category, title, body, int(free), row["n"], now),
        )
        await db.commit()
        return int(cur.lastrowid)
    finally:
        await db.close()


async def delete_library_item(item_id: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute("DELETE FROM library WHERE id=?", (item_id,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


# ---------- Мои скрипты ----------

async def list_saved(uid: int) -> list[dict]:
    db = await conn()
    try:
        rows = await (
            await db.execute("SELECT * FROM saved WHERE owner_id=? ORDER BY updated_at DESC, id DESC LIMIT 300", (uid,))
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def count_saved(uid: int) -> int:
    db = await conn()
    try:
        row = await (await db.execute("SELECT COUNT(*) AS n FROM saved WHERE owner_id=?", (uid,))).fetchone()
        return int(row["n"])
    finally:
        await db.close()


async def save_saved(
    uid: int, title: str, body: str, niche: str = "", purpose: str = "", saved_id: int | None = None
) -> int | None:
    db = await conn()
    try:
        now = int(time.time())
        if saved_id:
            cur = await db.execute(
                "UPDATE saved SET title=?, body=?, updated_at=? WHERE id=? AND owner_id=?",
                (title, body, now, saved_id, uid),
            )
            await db.commit()
            return saved_id if cur.rowcount > 0 else None
        cur = await db.execute(
            "INSERT INTO saved(owner_id, title, body, niche, purpose, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (uid, title, body, niche, purpose, now, now),
        )
        await db.commit()
        return int(cur.lastrowid)
    finally:
        await db.close()


async def delete_saved(uid: int, saved_id: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute("DELETE FROM saved WHERE id=? AND owner_id=?", (saved_id, uid))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


# ---------- Генерации, ошибки, статистика ----------

async def log_generation(uid: int, niche: str, purpose: str, channel: str, source: str) -> None:
    db = await conn()
    try:
        await db.execute(
            "INSERT INTO generations(user_id, niche, purpose, channel, source, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (uid, niche.strip()[:80], purpose, channel, source, int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()


async def user_stats(uid: int) -> dict:
    db = await conn()
    try:
        row = await (
            await db.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(created_at >= ?), 0) AS week FROM generations WHERE user_id=?",
                (int(time.time()) - 7 * 86400, uid),
            )
        ).fetchone()
        saved = await (await db.execute("SELECT COUNT(*) AS n FROM saved WHERE owner_id=?", (uid,))).fetchone()
        return {"generated": int(row["total"]), "week": int(row["week"]), "saved": int(saved["n"])}
    finally:
        await db.close()


async def log_source_error(provider: str, message: str) -> None:
    db = await conn()
    try:
        await db.execute(
            "INSERT INTO source_errors(provider, message, created_at) VALUES(?, ?, ?)",
            (provider, message[:400], int(time.time())),
        )
        await db.execute(
            "DELETE FROM source_errors WHERE id NOT IN (SELECT id FROM source_errors ORDER BY id DESC LIMIT 500)"
        )
        await db.commit()
    finally:
        await db.close()


async def source_errors(limit: int = 50) -> dict:
    db = await conn()
    try:
        recent = await (
            await db.execute(
                "SELECT provider, message, created_at FROM source_errors ORDER BY id DESC LIMIT ?", (limit,)
            )
        ).fetchall()
        counts = await (
            await db.execute(
                "SELECT provider, COUNT(*) AS n FROM source_errors WHERE created_at>=? GROUP BY provider",
                (int(time.time()) - 86400,),
            )
        ).fetchall()
        return {"recent": [dict(row) for row in recent], "day": {row["provider"]: row["n"] for row in counts}}
    finally:
        await db.close()


async def admin_overview() -> dict:
    db = await conn()
    try:
        async def one(sql, params=()):
            return await (await db.execute(sql, params)).fetchone()

        now = int(time.time())
        day_start = now - (now % 86400)
        users = await one(
            "SELECT COUNT(*) AS total, SUM(approved=1) AS members, SUM(banned=1) AS banned, "
            "SUM(approved=0 AND trial_used>0) AS trial_used, "
            "SUM(approved=0 AND trial_used=0) AS trial_left, "
            "SUM(app_opened_at IS NOT NULL) AS opened FROM users WHERE deleted=0"
        )
        gens = await one(
            "SELECT COUNT(*) AS total, COALESCE(SUM(created_at>=?), 0) AS today, "
            "COALESCE(SUM(created_at>=?), 0) AS week, "
            "COALESCE(SUM(source='ai'), 0) AS ai, COALESCE(SUM(source!='ai'), 0) AS template, "
            "COUNT(DISTINCT user_id) AS people FROM generations",
            (day_start, now - 7 * 86400),
        )
        purposes = await (
            await db.execute(
                "SELECT purpose AS name, COUNT(*) AS n FROM generations GROUP BY purpose ORDER BY n DESC LIMIT 12"
            )
        ).fetchall()
        niches = await (
            await db.execute(
                "SELECT lower(niche) AS name, COUNT(*) AS n FROM generations WHERE niche!='' "
                "GROUP BY lower(niche) ORDER BY n DESC LIMIT 15"
            )
        ).fetchall()
        series = await (
            await db.execute(
                "SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS n FROM generations "
                "WHERE created_at>=? GROUP BY day ORDER BY day",
                (now - 6 * 86400 - (now % 86400),),
            )
        ).fetchall()
        saved = await one("SELECT COUNT(*) AS n FROM saved")
        library = await one("SELECT COUNT(*) AS n FROM library")
        return {
            "users": {key: users[key] or 0 for key in users.keys()},
            "gens": {key: gens[key] or 0 for key in gens.keys()},
            "purposes": [dict(row) for row in purposes],
            "niches": [dict(row) for row in niches],
            "series": [dict(row) for row in series],
            "saved": int(saved["n"]),
            "library": int(library["n"]),
        }
    finally:
        await db.close()


async def recent_requests(limit: int = 40) -> list[dict]:
    db = await conn()
    try:
        rows = await (
            await db.execute(
                """
                SELECT g.niche, g.purpose, g.channel, g.source, g.created_at, u.username, u.first_name, g.user_id
                FROM generations g LEFT JOIN users u ON u.id=g.user_id
                ORDER BY g.id DESC LIMIT ?
                """,
                (limit,),
            )
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()
