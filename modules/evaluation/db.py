"""SQLite: пользователи, заявки на оценку, переписка, оплаты."""
from __future__ import annotations

import json
import time

import aiosqlite

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL DEFAULT '',
  first_name TEXT NOT NULL DEFAULT '',
  free_used INTEGER NOT NULL DEFAULT 0,
  credits INTEGER NOT NULL DEFAULT 0,
  banned INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  kind TEXT NOT NULL DEFAULT 'free',
  url TEXT NOT NULL DEFAULT '',
  comment TEXT NOT NULL DEFAULT '',
  media TEXT NOT NULL DEFAULT '[]',
  admin_id INTEGER,
  admin_name TEXT NOT NULL DEFAULT '',
  scores TEXT NOT NULL DEFAULT '{}',
  notes TEXT NOT NULL DEFAULT '{}',
  total REAL,
  pros TEXT NOT NULL DEFAULT '',
  cons TEXT NOT NULL DEFAULT '',
  advice TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  taken_at INTEGER,
  done_at INTEGER
);
CREATE INDEX IF NOT EXISTS reviews_status ON reviews(status, id);
CREATE INDEX IF NOT EXISTS reviews_user ON reviews(user_id, id);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  from_admin INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_review ON messages(review_id, id);
CREATE TABLE IF NOT EXISTS texts(
  key TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  image BLOB,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  credits INTEGER NOT NULL DEFAULT 1,
  charge_id TEXT UNIQUE,
  admin_id INTEGER,
  created_at INTEGER NOT NULL
);
"""

CRITERIA = (
    ("design", "Дизайн"),
    ("ux", "Удобство"),
    ("mobile", "Мобильная версия"),
    ("text", "Тексты"),
    ("trust", "Доверие и продажи"),
)
CRITERIA_KEYS = tuple(key for key, _ in CRITERIA)


def now() -> int:
    return int(time.time())


async def conn() -> aiosqlite.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(config.DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    return db


async def init() -> None:
    db = await conn()
    try:
        await db.executescript(SCHEMA)
        cols = {r["name"] for r in await (await db.execute("PRAGMA table_info(reviews)")).fetchall()}
        if "notes" not in cols:
            await db.execute("ALTER TABLE reviews ADD COLUMN notes TEXT NOT NULL DEFAULT '{}'")
        if "body" not in cols:
            await db.execute("ALTER TABLE reviews ADD COLUMN body TEXT NOT NULL DEFAULT ''")
        # AI-оценка: статус (pending, done, error), балл 1–5, разбор в JSON
        for name, kind in (("ai_status", "TEXT NOT NULL DEFAULT ''"), ("ai_score", "INTEGER"),
                           ("ai_json", "TEXT NOT NULL DEFAULT '{}'"), ("ai_error", "TEXT NOT NULL DEFAULT ''"),
                           ("ai_at", "INTEGER")):
            if name not in cols:
                await db.execute(f"ALTER TABLE reviews ADD COLUMN {name} {kind}")
        await db.commit()
    finally:
        await db.close()


# ---------- Пользователи и баланс ----------

def quota(user: dict | None) -> dict:
    user = user or {}
    free_left = max(0, config.FREE_REVIEWS - int(user.get("free_used") or 0))
    credits = max(0, int(user.get("credits") or 0))
    return {"free_left": free_left, "credits": credits, "available": free_left + credits}


async def upsert_user(uid: int, username: str | None, first_name: str | None) -> dict:
    db = await conn()
    try:
        await db.execute(
            """INSERT INTO users(id, username, first_name, created_at) VALUES(?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name""",
            (uid, username or "", first_name or "", now()),
        )
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


async def find_user(query: str) -> dict | None:
    query = query.strip().lstrip("@")
    db = await conn()
    try:
        if query.isdigit():
            row = await (await db.execute("SELECT * FROM users WHERE id=?", (int(query),))).fetchone()
        else:
            row = await (await db.execute("SELECT * FROM users WHERE lower(username)=?", (query.lower(),))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def create_review(uid: int, url: str, comment: str, media: list[dict]) -> tuple[int | None, str]:
    """Атомарно списывает одну оценку (сначала бесплатные, потом оплаченные) и создаёт заявку.
    Возвращает (id заявки, вид) или (None, 'no_quota' | 'banned')."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (uid,))).fetchone()
        if not row:
            await db.rollback()
            return None, "no_quota"
        user = dict(row)
        if user["banned"]:
            await db.rollback()
            return None, "banned"
        q = quota(user)
        if q["free_left"] > 0:
            kind = "free"
            await db.execute("UPDATE users SET free_used=free_used+1 WHERE id=?", (uid,))
        elif q["credits"] > 0:
            kind = "paid"
            await db.execute("UPDATE users SET credits=credits-1 WHERE id=?", (uid,))
        else:
            await db.rollback()
            return None, "no_quota"
        cur = await db.execute(
            "INSERT INTO reviews(user_id, kind, url, comment, media, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (uid, kind, url[:300], comment[:1500], json.dumps(media[: config.MAX_MEDIA]), now()),
        )
        await db.commit()
        return cur.lastrowid, kind
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def _refund(db, review: dict) -> None:
    if review["kind"] == "free":
        await db.execute("UPDATE users SET free_used=MAX(0, free_used-1) WHERE id=?", (review["user_id"],))
    else:
        await db.execute("UPDATE users SET credits=credits+1 WHERE id=?", (review["user_id"],))


async def add_credits(uid: int, amount: int, admin_id: int | None = None) -> int:
    db = await conn()
    try:
        await db.execute("UPDATE users SET credits=MAX(0, credits+?) WHERE id=?", (amount, uid))
        if amount > 0:
            await db.execute(
                "INSERT INTO payments(user_id, kind, amount, credits, admin_id, created_at) VALUES(?, 'manual', ?, ?, ?, ?)",
                (uid, amount * config.PRICE_RUB, amount, admin_id, now()),
            )
        await db.commit()
        row = await (await db.execute("SELECT credits FROM users WHERE id=?", (uid,))).fetchone()
        return int(row["credits"]) if row else 0
    finally:
        await db.close()


async def record_star_payment(uid: int, stars: int, charge_id: str) -> bool:
    """Зачисляет оплаченную оценку. Повтор того же платежа ничего не начисляет."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "INSERT OR IGNORE INTO payments(user_id, kind, amount, credits, charge_id, created_at) VALUES(?, 'stars', ?, 1, ?, ?)",
            (uid, stars, charge_id, now()),
        )
        if cur.rowcount > 0:
            await db.execute("UPDATE users SET credits=credits+1 WHERE id=?", (uid,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def set_banned(uid: int, banned: bool) -> bool:
    db = await conn()
    try:
        cur = await db.execute("UPDATE users SET banned=? WHERE id=?", (int(banned), uid))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


# ---------- Заявки ----------

def review_row(row) -> dict:
    data = dict(row)
    for key, default in (("media", []), ("scores", {}), ("notes", {}), ("ai_json", {})):
        try:
            data[key] = json.loads(data.get(key) or "null") or default
        except ValueError:
            data[key] = default
    return data


async def get_review(review_id: int) -> dict | None:
    db = await conn()
    try:
        row = await (await db.execute(
            "SELECT r.*, u.username, u.first_name FROM reviews r LEFT JOIN users u ON u.id=r.user_id WHERE r.id=?",
            (review_id,),
        )).fetchone()
        if not row:
            return None
        review = review_row(row)
        msgs = await (await db.execute(
            "SELECT * FROM messages WHERE review_id=? ORDER BY id", (review_id,)
        )).fetchall()
        review["messages"] = [dict(m) for m in msgs]
        return review
    finally:
        await db.close()


async def list_reviews(status: str = "open", query: str = "", limit: int = 200) -> list[dict]:
    where, params = [], []
    if status == "open":
        where.append("r.status IN ('new','work')")
    elif status in ("new", "work", "done", "rejected"):
        where.append("r.status=?")
        params.append(status)
    if query:
        q = query.strip().lstrip("@").lower()
        where.append("(lower(u.username) LIKE ? OR lower(r.url) LIKE ? OR CAST(r.id AS TEXT)=? OR CAST(r.user_id AS TEXT)=?)")
        params += [f"%{q}%", f"%{q}%", q, q]
    sql = (
        "SELECT r.*, u.username, u.first_name, "
        "(SELECT COUNT(*) FROM messages m WHERE m.review_id=r.id) AS msg_count "
        "FROM reviews r LEFT JOIN users u ON u.id=r.user_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + (" ORDER BY r.id ASC" if status in ("open", "new", "work") else " ORDER BY r.id DESC")
        + " LIMIT ?"
    )
    db = await conn()
    try:
        rows = await (await db.execute(sql, (*params, limit))).fetchall()
        return [review_row(r) for r in rows]
    finally:
        await db.close()


async def user_reviews(uid: int, limit: int = 20) -> list[dict]:
    db = await conn()
    try:
        rows = await (await db.execute(
            "SELECT * FROM reviews WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)
        )).fetchall()
        return [review_row(r) for r in rows]
    finally:
        await db.close()


async def take_review(review_id: int, admin_id: int, admin_name: str) -> dict | None:
    """Берёт заявку в работу. Возвращает заявку, если статус поменялся с «new»."""
    db = await conn()
    try:
        cur = await db.execute(
            "UPDATE reviews SET status='work', admin_id=?, admin_name=?, taken_at=? WHERE id=? AND status='new'",
            (admin_id, admin_name, now(), review_id),
        )
        await db.commit()
    finally:
        await db.close()
    return await get_review(review_id) if cur.rowcount > 0 else None


async def finish_review(review_id: int, admin_id: int, admin_name: str, scores: dict, total: float | None,
                        pros: str, cons: str, advice: str, notes: dict | None = None, body: str = "") -> bool:
    db = await conn()
    try:
        cur = await db.execute(
            """UPDATE reviews SET status='done', admin_id=?, admin_name=?, scores=?, notes=?, total=?, pros=?, cons=?,
               advice=?, body=?, done_at=?, taken_at=COALESCE(taken_at, ?) WHERE id=? AND status IN ('new','work')""",
            (admin_id, admin_name, json.dumps(scores), json.dumps(notes or {}, ensure_ascii=False), total, pros, cons,
             advice, body, now(), now(), review_id),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def reject_review(review_id: int, admin_id: int, admin_name: str, reason: str) -> dict | None:
    """Отклоняет заявку и возвращает человеку списанную оценку."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute("SELECT * FROM reviews WHERE id=?", (review_id,))).fetchone()
        if not row or row["status"] not in ("new", "work"):
            await db.rollback()
            return None
        review = dict(row)
        await db.execute(
            "UPDATE reviews SET status='rejected', admin_id=?, admin_name=?, reason=?, done_at=? WHERE id=?",
            (admin_id, admin_name, reason, now(), review_id),
        )
        await _refund(db, review)
        await db.commit()
        return review
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def add_message(review_id: int, author_id: int, from_admin: bool, text: str) -> int:
    db = await conn()
    try:
        cur = await db.execute(
            "INSERT INTO messages(review_id, author_id, from_admin, text, created_at) VALUES(?, ?, ?, ?, ?)",
            (review_id, author_id, int(from_admin), text[:3500], now()),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


# ---------- Админка ----------

async def admin_chat_ids() -> list[int]:
    """Кому слать уведомления: админы по ID и админы по @username, которые уже писали боту."""
    ids = set(config.ADMIN_IDS)
    if config.ADMIN_USERNAMES:
        marks = ",".join("?" for _ in config.ADMIN_USERNAMES)
        db = await conn()
        try:
            rows = await (await db.execute(
                f"SELECT id FROM users WHERE lower(username) IN ({marks})", tuple(config.ADMIN_USERNAMES)
            )).fetchall()
            ids.update(int(r["id"]) for r in rows)
        finally:
            await db.close()
    return sorted(ids)


async def list_users(query: str = "", limit: int = 300) -> list[dict]:
    q = query.strip().lstrip("@").lower()
    sql = (
        "SELECT u.*, (SELECT COUNT(*) FROM reviews r WHERE r.user_id=u.id) AS reviews, "
        "(SELECT COALESCE(SUM(p.credits),0) FROM payments p WHERE p.user_id=u.id) AS paid "
        "FROM users u"
    )
    params: list = []
    if q:
        sql += " WHERE lower(u.username) LIKE ? OR lower(u.first_name) LIKE ? OR CAST(u.id AS TEXT)=?"
        params = [f"%{q}%", f"%{q}%", q]
    sql += " ORDER BY u.created_at DESC LIMIT ?"
    db = await conn()
    try:
        rows = await (await db.execute(sql, (*params, limit))).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item.update(quota(item))
            result.append(item)
        return result
    finally:
        await db.close()


async def overview() -> dict:
    db = await conn()
    try:
        async def one(sql, *params):
            row = await (await db.execute(sql, params)).fetchone()
            return row[0] or 0

        week = now() - 7 * 86400
        return {
            "users": await one("SELECT COUNT(*) FROM users"),
            "new": await one("SELECT COUNT(*) FROM reviews WHERE status='new'"),
            "work": await one("SELECT COUNT(*) FROM reviews WHERE status='work'"),
            "done": await one("SELECT COUNT(*) FROM reviews WHERE status='done'"),
            "done_week": await one("SELECT COUNT(*) FROM reviews WHERE status='done' AND done_at>=?", week),
            "paid_reviews": await one("SELECT COUNT(*) FROM reviews WHERE kind='paid'"),
            "stars": await one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE kind='stars'"),
            "manual_rub": await one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE kind='manual'"),
            "avg_total": round(await one("SELECT AVG(total) FROM reviews WHERE status='done'"), 1),
        }
    finally:
        await db.close()


# ---------- Тексты бота ----------

async def get_text(key: str) -> tuple[str, bytes | None, bool]:
    """(текст, картинка, изменён ли) — изменённый админом или стандартный."""
    from . import texts

    db = await conn()
    try:
        row = await (await db.execute("SELECT text, image FROM texts WHERE key=?", (key,))).fetchone()
    finally:
        await db.close()
    if row:
        return row["text"], row["image"], True
    return texts.DEFAULTS[key]["text"], None, False


async def all_texts() -> dict[str, dict]:
    db = await conn()
    try:
        rows = await (await db.execute("SELECT key, text, image IS NOT NULL AS has_image, updated_at FROM texts")).fetchall()
        return {r["key"]: dict(r) for r in rows}
    finally:
        await db.close()


async def get_text_image(key: str) -> bytes | None:
    db = await conn()
    try:
        row = await (await db.execute("SELECT image FROM texts WHERE key=?", (key,))).fetchone()
        return row["image"] if row else None
    finally:
        await db.close()


async def set_text(key: str, text: str, image: bytes | None, keep_image: bool) -> None:
    db = await conn()
    try:
        if keep_image:
            row = await (await db.execute("SELECT image FROM texts WHERE key=?", (key,))).fetchone()
            image = row["image"] if row else None
        await db.execute(
            "INSERT INTO texts(key, text, image, updated_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET text=excluded.text, image=excluded.image, updated_at=excluded.updated_at",
            (key, text, image, now()),
        )
        await db.commit()
    finally:
        await db.close()


async def reset_text(key: str) -> None:
    db = await conn()
    try:
        await db.execute("DELETE FROM texts WHERE key=?", (key,))
        await db.commit()
    finally:
        await db.close()


# ---------- Рассылка и графики ----------

SEGMENT_SQL = {
    "all": "SELECT id FROM users WHERE banned=0",
    "sent": "SELECT id FROM users WHERE banned=0 AND id IN (SELECT user_id FROM reviews)",
    "not_sent": "SELECT id FROM users WHERE banned=0 AND id NOT IN (SELECT user_id FROM reviews)",
    "paid": "SELECT id FROM users WHERE banned=0 AND id IN (SELECT user_id FROM payments)",
}


async def segment_ids(segment: str) -> list[int]:
    db = await conn()
    try:
        rows = await (await db.execute(SEGMENT_SQL.get(segment, SEGMENT_SQL["all"]))).fetchall()
        return [int(r["id"]) for r in rows]
    finally:
        await db.close()


async def segment_counts() -> dict[str, int]:
    return {key: len(await segment_ids(key)) for key in SEGMENT_SQL}


async def daily(days: int = 14) -> list[dict]:
    """Заявки и готовые оценки по дням (UTC) за последние days дней."""
    start = (now() // 86400 - days + 1) * 86400
    db = await conn()
    try:
        made = await (await db.execute(
            "SELECT created_at/86400 AS d, COUNT(*) AS n FROM reviews WHERE created_at>=? GROUP BY d", (start,)
        )).fetchall()
        done = await (await db.execute(
            "SELECT done_at/86400 AS d, COUNT(*) AS n FROM reviews WHERE status='done' AND done_at>=? GROUP BY d", (start,)
        )).fetchall()
    finally:
        await db.close()
    m = {int(r["d"]): r["n"] for r in made}
    f = {int(r["d"]): r["n"] for r in done}
    first = start // 86400
    return [{"day": (first + i) * 86400, "new": m.get(first + i, 0), "done": f.get(first + i, 0)} for i in range(days)]


# ---------- AI-оценка ----------

async def set_ai(review_id: int, status: str, score: int | None = None, result: dict | None = None,
                 error: str = "") -> None:
    db = await conn()
    try:
        await db.execute("UPDATE reviews SET ai_status=?, ai_score=?, ai_json=?, ai_error=?, ai_at=? WHERE id=?",
                         (status, score, json.dumps(result or {}, ensure_ascii=False), error[:500], now(), review_id))
        await db.commit()
    finally:
        await db.close()


async def ai_list(query: str = "", score: int = 0, limit: int = 300) -> list[dict]:
    """Все присланные работы с AI-оценкой — для админки."""
    where, params = [], []
    if score:
        where.append("r.ai_score=?")
        params.append(score)
    if query:
        q = query.strip().lstrip("@").lower()
        where.append("(lower(u.username) LIKE ? OR lower(u.first_name) LIKE ? OR lower(r.url) LIKE ? "
                     "OR CAST(r.id AS TEXT)=? OR CAST(r.user_id AS TEXT)=?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%", q, q]
    sql = ("SELECT r.*, u.username, u.first_name FROM reviews r LEFT JOIN users u ON u.id=r.user_id"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY r.id DESC LIMIT ?")
    db = await conn()
    try:
        rows = await (await db.execute(sql, (*params, limit))).fetchall()
        return [review_row(r) for r in rows]
    finally:
        await db.close()


async def ai_stats() -> dict:
    db = await conn()
    try:
        rows = await (await db.execute(
            "SELECT ai_score, COUNT(*) AS n FROM reviews WHERE ai_status='done' GROUP BY ai_score")).fetchall()
        total = await (await db.execute("SELECT COUNT(*) FROM reviews")).fetchone()
        return {"by_score": {int(r["ai_score"]): r["n"] for r in rows if r["ai_score"]}, "total": total[0] or 0}
    finally:
        await db.close()
