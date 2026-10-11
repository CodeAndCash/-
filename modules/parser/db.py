import hashlib
import json
import time
import zlib
from datetime import date

import aiosqlite

from .config import ADMIN_IDS, ADMIN_USERNAMES, DB_PATH, DEFAULT_LIMIT, is_admin_user
from . import contacts as cn
from .lead_identity import LeadIdentityIndex, claim_tokens

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 0,
  daily_limit INTEGER NOT NULL DEFAULT 35,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS leads(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  osm_key TEXT NOT NULL,
  name TEXT NOT NULL,
  country TEXT NOT NULL,
  city TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  site TEXT NOT NULL,
  site_url TEXT NOT NULL DEFAULT '',
  reasons TEXT NOT NULL DEFAULT '[]',
  contacts TEXT NOT NULL DEFAULT '{}',
  hot INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  created_at INTEGER NOT NULL,
  UNIQUE(user_id, osm_key)
);
CREATE TABLE IF NOT EXISTS usage(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  cnt INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  total INTEGER NOT NULL,
  reserved INTEGER NOT NULL DEFAULT 0,
  usage_day TEXT NOT NULL,
  found INTEGER NOT NULL DEFAULT 0,
  checked INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',
  error TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_usage(
  provider TEXT NOT NULL,
  month TEXT NOT NULL,
  cnt INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(provider, month)
);
-- Глобальное закрепление: каждый признак бизнеса принадлежит ровно одному лиду.
CREATE TABLE IF NOT EXISTS lead_tokens(
  token TEXT PRIMARY KEY,
  lead_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL
);
-- Чёрный список бизнесов: такие признаки никогда не попадают в выдачу.
CREATE TABLE IF NOT EXISTS blocked(
  token TEXT PRIMARY KEY,
  label TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
-- Все проверенные бизнесы (для статистики спроса по нишам).
CREATE TABLE IF NOT EXISTS analyzed(
  key TEXT PRIMARY KEY,
  niche TEXT NOT NULL,
  country TEXT NOT NULL,
  city TEXT NOT NULL DEFAULT '',
  site TEXT NOT NULL,
  need TEXT NOT NULL DEFAULT '',
  tg_bot INTEGER NOT NULL DEFAULT 0,
  booking INTEGER NOT NULL DEFAULT 0,
  priority INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
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
  daily_limit INTEGER NOT NULL DEFAULT 35,
  bonus INTEGER NOT NULL DEFAULT 0,
  uses_left INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  used_by TEXT NOT NULL DEFAULT '',
  used_at INTEGER
);
CREATE TABLE IF NOT EXISTS scripts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL DEFAULT 0,
  niche INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
-- Кэш ответов карт (Overpass): одинаковый запрос повторно отдаётся мгновенно.
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS osm_cache(
  qhash TEXT PRIMARY KEY,
  body BLOB NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scripts_owner ON scripts(owner_id, niche);
CREATE INDEX IF NOT EXISTS idx_errors_time ON source_errors(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
"""


async def conn() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


# Лимит по умолчанию для новых участников. Владелец меняет его в админке (хранится в meta),
# переменная DEFAULT_LIMIT в Railway — только начальное значение.
_DEFAULTS = {"limit": DEFAULT_LIMIT}


def default_limit() -> int:
    return _DEFAULTS["limit"]


async def set_default_limit(value: int, scope: str = "standard") -> int:
    """Меняет лимит по умолчанию. scope: new — только новым; standard — ещё и тем,
    у кого стоял прежний стандартный лимит; all — всем участникам, кроме владельца.
    Возвращает, скольким пользователям поменяли лимит."""
    old = default_limit()
    db = await conn()
    try:
        await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('default_limit', ?)", (str(value),))
        changed = 0
        if scope == "all":
            cur = await db.execute("UPDATE users SET daily_limit=? WHERE is_admin=0", (value,))
            changed = cur.rowcount
        elif scope == "standard" and old != value:
            cur = await db.execute("UPDATE users SET daily_limit=? WHERE is_admin=0 AND daily_limit=?", (value, old))
            changed = cur.rowcount
        await db.commit()
        _DEFAULTS["limit"] = value
        return max(0, changed)
    finally:
        await db.close()


async def init() -> None:
    db = await conn()
    try:
        await db.executescript(SCHEMA)
        job_columns = {
            row["name"]
            for row in await (await db.execute("PRAGMA table_info(jobs)")).fetchall()
        }
        if "reserved" not in job_columns:
            await db.execute(
                "ALTER TABLE jobs ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0"
            )
        if "usage_day" not in job_columns:
            await db.execute(
                "ALTER TABLE jobs ADD COLUMN usage_day TEXT NOT NULL DEFAULT ''"
            )
        for column in ("trial", "refund"):
            if column not in job_columns:
                await db.execute(
                    f"ALTER TABLE jobs ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
        await _add_columns(db, "users", {
            "banned": "INTEGER NOT NULL DEFAULT 0",
            "trial_used": "INTEGER NOT NULL DEFAULT 0",
            "bonus": "INTEGER NOT NULL DEFAULT 0",
            "deleted": "INTEGER NOT NULL DEFAULT 0",
            "bot_started_at": "INTEGER",
            "app_opened_at": "INTEGER",
        })
        await _add_columns(db, "leads", {
            "need": "TEXT NOT NULL DEFAULT ''",
            "explain": "TEXT NOT NULL DEFAULT ''",
            "info": "TEXT NOT NULL DEFAULT '{}'",
            "source": "TEXT NOT NULL DEFAULT ''",
            "niche": "TEXT NOT NULL DEFAULT ''",
        })
        # Один раз: стандартный лимит 70 → новый стандарт (35). Ручные лимиты не трогаем.
        done = await (await db.execute("SELECT value FROM meta WHERE key='limit35'")).fetchone()
        if not done:
            await db.execute(
                "UPDATE users SET daily_limit=? WHERE daily_limit=70 AND is_admin=0", (DEFAULT_LIMIT,)
            )
            await db.execute(
                "UPDATE access_keys SET daily_limit=? WHERE daily_limit=70 AND used_by=''", (DEFAULT_LIMIT,)
            )
            await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('limit35', '1')")
        saved = await (await db.execute("SELECT value FROM meta WHERE key='default_limit'")).fetchone()
        try:
            _DEFAULTS["limit"] = max(0, min(5000, int(saved["value"]))) if saved else DEFAULT_LIMIT
        except (TypeError, ValueError):
            _DEFAULTS["limit"] = DEFAULT_LIMIT
        # Admin status belongs only to the configured owner. This also removes
        # privileges left behind by an older ADMIN_IDS setting.
        await db.execute("UPDATE users SET is_admin=0")
        for admin_id in ADMIN_IDS:
            await db.execute(
                """
                INSERT INTO users(id, is_admin, approved, daily_limit, created_at)
                VALUES(?, 1, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET is_admin=1, approved=1
                """,
                (admin_id, max(DEFAULT_LIMIT, 1000), int(time.time())),
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
    await _repair_contacts()
    await _dedupe_existing_leads()
    await _claim_existing_leads()
    await recover_interrupted_jobs()
    db = await conn()
    try:
        await db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_one_running_job_per_user
            ON jobs(user_id) WHERE status='running'
            """
        )
        await db.commit()
    finally:
        await db.close()


async def _add_columns(db, table: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"] for row in await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def _claim_existing_leads() -> None:
    """Закрепляет уже выданные лиды за их владельцами (первый выданный побеждает)."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        claimed = await (await db.execute("SELECT COUNT(*) AS n FROM lead_tokens")).fetchone()
        total = await (await db.execute("SELECT COUNT(*) AS n FROM leads")).fetchone()
        if total["n"] and not claimed["n"]:
            rows = await (await db.execute("SELECT * FROM leads ORDER BY id")).fetchall()
            for row in rows:
                lead = _identity_row(row)
                for token in claim_tokens(lead):
                    await db.execute(
                        "INSERT OR IGNORE INTO lead_tokens(token, lead_id, user_id) VALUES(?, ?, ?)",
                        (token, row["id"], row["user_id"]),
                    )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


def _identity_row(row) -> dict:
    lead = dict(row)
    try:
        lead["contacts"] = json.loads(lead.get("contacts") or "{}")
    except (TypeError, ValueError):
        lead["contacts"] = {}
    try:
        lead["reasons"] = json.loads(lead.get("reasons") or "[]")
    except (TypeError, ValueError):
        lead["reasons"] = []
    try:
        lead["info"] = json.loads(lead.get("info") or "{}")
    except (TypeError, ValueError):
        lead["info"] = {}
    return lead


def _merge_duplicate_leads(keeper: dict, duplicate: dict) -> dict:
    contacts = dict(keeper.get("contacts") or {})
    for key, value in (duplicate.get("contacts") or {}).items():
        if value and not contacts.get(key):
            contacts[key] = value

    reasons = list(dict.fromkeys(
        list(keeper.get("reasons") or []) + list(duplicate.get("reasons") or [])
    ))
    site_rank = {"none": 0, "weak": 1, "ok": 2}
    site = max(
        (keeper.get("site") or "none", duplicate.get("site") or "none"),
        key=lambda value: site_rank.get(value, 0),
    )
    status_rank = {"new": 0, "rejected": 1, "written": 2, "replied": 3, "client": 4}
    status = max(
        (keeper.get("status") or "new", duplicate.get("status") or "new"),
        key=lambda value: status_rank.get(value, 0),
    )
    keeper.update(
        {
            "name": keeper.get("name") or duplicate.get("name") or "",
            "country": keeper.get("country") or duplicate.get("country") or "",
            "city": (
                duplicate.get("city")
                if not keeper.get("city") or str(keeper.get("city")).casefold() == "не указан"
                else keeper.get("city")
            ) or "",
            "phone": keeper.get("phone") or duplicate.get("phone") or "",
            "site": site,
            "site_url": keeper.get("site_url") or duplicate.get("site_url") or "",
            "reasons": reasons,
            "contacts": contacts,
            "hot": max(int(keeper.get("hot") or 0), int(duplicate.get("hot") or 0)),
            "status": status,
            "created_at": min(
                int(keeper.get("created_at") or 0),
                int(duplicate.get("created_at") or 0),
            ),
        }
    )
    return keeper


async def _repair_contacts() -> None:
    """Убирает из сохранённых лидов битые ссылки (например vk.com/https)."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        rows = await (await db.execute("SELECT id, country, contacts FROM leads")).fetchall()
        for row in rows:
            try:
                current = json.loads(row["contacts"] or "{}")
            except (TypeError, ValueError):
                current = {}
            cleaned = cn.clean_contacts(current, row["country"])
            if cleaned != current:
                await db.execute(
                    "UPDATE leads SET contacts=? WHERE id=?",
                    (json.dumps(cleaned, ensure_ascii=False), row["id"]),
                )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


def _period(kind: str) -> str:
    return date.today().strftime("%Y-%m") if kind == "month" else date.today().isoformat()


async def reserve_api_call(
    provider: str, limit: int, *, period: str = "month", amount: int = 1
) -> bool:
    """Атомарно учитывает запрос к внешнему сервису. False, если лимит периода исчерпан."""
    key = _period(period)
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT OR IGNORE INTO api_usage(provider, month, cnt) VALUES(?, ?, 0)",
            (provider, key),
        )
        row = await (
            await db.execute(
                "SELECT cnt FROM api_usage WHERE provider=? AND month=?", (provider, key)
            )
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


async def api_calls_this_month(provider: str, period: str = "month") -> int:
    db = await conn()
    try:
        row = await (
            await db.execute(
                "SELECT cnt FROM api_usage WHERE provider=? AND month=?",
                (provider, _period(period)),
            )
        ).fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        await db.close()


async def _dedupe_existing_leads() -> None:
    """Collapse legacy duplicate leads while preserving their useful data."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        rows = await (await db.execute("SELECT * FROM leads ORDER BY user_id, id")).fetchall()
        indexes: dict[int, LeadIdentityIndex] = {}
        for row in rows:
            lead = _identity_row(row)
            user_id = int(lead["user_id"])
            index = indexes.setdefault(user_id, LeadIdentityIndex())
            keeper = index.find_duplicate(lead)
            if keeper is None:
                index.add(lead)
                continue

            keeper_id = int(keeper["id"])
            duplicate_id = int(lead["id"])
            merged = _merge_duplicate_leads(keeper, lead)
            await db.execute(
                """
                UPDATE leads SET name=?, country=?, city=?, phone=?, site=?, site_url=?,
                    reasons=?, contacts=?, hot=?, status=?, created_at=?
                WHERE id=? AND user_id=?
                """,
                (
                    merged["name"], merged["country"], merged["city"], merged["phone"],
                    merged["site"], merged["site_url"],
                    json.dumps(merged["reasons"], ensure_ascii=False),
                    json.dumps(merged["contacts"], ensure_ascii=False),
                    merged["hot"], merged["status"], merged["created_at"],
                    keeper_id, user_id,
                ),
            )
            await db.execute("DELETE FROM leads WHERE id=? AND user_id=?", (duplicate_id, user_id))
            index.add(keeper)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


def today() -> str:
    return date.today().isoformat()


async def upsert_user(uid: int, username: str | None, first_name: str | None) -> dict:
    db = await conn()
    try:
        is_admin = int(is_admin_user(uid, username))
        await db.execute(
            """
            INSERT INTO users(id, username, first_name, approved, is_admin,
                              daily_limit, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              username=excluded.username, first_name=excluded.first_name
            """,
            (
                uid, username, first_name, is_admin, is_admin, default_limit(),
                int(time.time()),
            ),
        )
        if is_admin:
            await db.execute(
                "UPDATE users SET is_admin=1, approved=1, banned=0, deleted=0, "
                "daily_limit=MAX(daily_limit, 1000) WHERE id=?",
                (uid,),
            )
        else:
            # убрали из ADMIN_IDS — админка пропадает, полный доступ остаётся
            await db.execute("UPDATE users SET is_admin=0 WHERE id=? AND is_admin=1", (uid,))
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_user(uid: int) -> dict | None:
    db = await conn()
    try:
        cur = await db.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def used_today(uid: int) -> int:
    db = await conn()
    try:
        cur = await db.execute(
            "SELECT cnt FROM usage WHERE user_id=? AND day=?", (uid, today())
        )
        row = await cur.fetchone()
        return row["cnt"] if row else 0
    finally:
        await db.close()


async def reserve_usage(uid: int, amount: int, daily_limit: int) -> tuple[bool, str]:
    """Atomically reserve quota before starting a background search."""
    usage_day = today()
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT OR IGNORE INTO usage(user_id, day, cnt) VALUES(?, ?, 0)",
            (uid, usage_day),
        )
        cur = await db.execute(
            "SELECT cnt FROM usage WHERE user_id=? AND day=?", (uid, usage_day)
        )
        row = await cur.fetchone()
        used = int(row["cnt"])
        if amount > max(0, daily_limit - used):
            await db.rollback()
            return False, usage_day
        await db.execute(
            "UPDATE usage SET cnt=cnt+? WHERE user_id=? AND day=?",
            (amount, uid, usage_day),
        )
        await db.commit()
        return True, usage_day
    finally:
        await db.close()


async def adjust_usage(uid: int, usage_day: str, delta: int) -> None:
    if delta == 0:
        return
    db = await conn()
    try:
        await db.execute(
            """
            UPDATE usage SET cnt=MAX(0, cnt+?)
            WHERE user_id=? AND day=?
            """,
            (delta, uid, usage_day),
        )
        await db.commit()
    finally:
        await db.close()


async def claim_leads(uid: int, leads: list[dict]) -> list[dict]:
    """Атомарно закрепляет лиды за пользователем и возвращает те, что достались ему.

    Проверка и запись идут в одной транзакции BEGIN IMMEDIATE: SQLite пускает
    в неё только одного писателя, поэтому при любом числе одновременных поисков
    бизнес достанется ровно одному человеку и больше никому не будет выдан."""
    db = await conn()
    claimed: list[dict] = []
    try:
        await db.execute("BEGIN IMMEDIATE")
        for lead in leads:
            tokens = sorted(claim_tokens(lead))
            if not tokens:
                continue
            marks = ",".join("?" for _ in tokens)
            busy = await (
                await db.execute(
                    f"SELECT 1 FROM lead_tokens WHERE token IN ({marks}) "
                    f"UNION ALL SELECT 1 FROM blocked WHERE token IN ({marks}) LIMIT 1",
                    (*tokens, *tokens),
                )
            ).fetchone()
            if busy:
                continue
            cur = await db.execute(
                """
                INSERT OR IGNORE INTO leads(
                  user_id, osm_key, name, country, city, phone, site, site_url,
                  reasons, contacts, hot, status, created_at, need, explain, info, source, niche
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid, lead["osm_key"], lead["name"], lead["country"], lead["city"],
                    lead["phone"], lead["site"], lead.get("site_url", ""),
                    json.dumps(lead.get("reasons") or [], ensure_ascii=False),
                    json.dumps(lead.get("contacts") or {}, ensure_ascii=False),
                    int(lead.get("hot") or 0), int(time.time()),
                    lead.get("need", ""), lead.get("explain", ""),
                    json.dumps(lead.get("info") or {}, ensure_ascii=False),
                    lead.get("source", ""), (lead.get("info") or {}).get("niche", ""),
                ),
            )
            if cur.rowcount <= 0:
                continue
            lead_id = cur.lastrowid
            await db.executemany(
                "INSERT OR IGNORE INTO lead_tokens(token, lead_id, user_id) VALUES(?, ?, ?)",
                [(token, lead_id, uid) for token in tokens],
            )
            claimed.append({**lead, "id": lead_id})
        await db.commit()
        return claimed
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def save_leads(uid: int, leads: list[dict]) -> int:
    return len(await claim_leads(uid, leads))


async def taken_tokens(tokens: set[str]) -> set[str]:
    """Какие из признаков уже закреплены за кем-то или стоят в чёрном списке."""
    items = list(tokens)
    found: set[str] = set()
    if not items:
        return found
    db = await conn()
    try:
        for start in range(0, len(items), 400):
            chunk = items[start:start + 400]
            marks = ",".join("?" for _ in chunk)
            rows = await (
                await db.execute(
                    f"SELECT token FROM lead_tokens WHERE token IN ({marks}) "
                    f"UNION SELECT token FROM blocked WHERE token IN ({marks})",
                    (*chunk, *chunk),
                )
            ).fetchall()
            found.update(row["token"] for row in rows)
        return found
    finally:
        await db.close()


def lead_row(row: aiosqlite.Row) -> dict:
    keys = row.keys()

    def load(name, default):
        if name not in keys:
            return default
        try:
            value = json.loads(row[name] or "null")
        except (TypeError, ValueError):
            return default
        return value if isinstance(value, type(default)) else default

    def text(name):
        return (row[name] or "") if name in keys else ""

    return {
        "id": row["id"],
        "name": row["name"],
        "country": row["country"],
        "city": row["city"],
        "phone": row["phone"],
        "site": row["site"],
        "url": row["site_url"] or "",
        "reasons": load("reasons", []),
        "c": load("contacts", {}),
        "hot": row["hot"],
        "status": row["status"],
        "need": text("need"),
        "explain": text("explain"),
        "info": load("info", {}),
        "source": text("source"),
        "niche": text("niche"),
    }


async def list_leads(uid: int, status: str = "all", limit: int = 300) -> list[dict]:
    db = await conn()
    try:
        if status in ("all", ""):
            query = (
                "SELECT * FROM leads WHERE user_id=? "
                "ORDER BY hot DESC, id DESC LIMIT ?"
            )
            params = (uid, limit)
        else:
            query = (
                "SELECT * FROM leads WHERE user_id=? AND status=? "
                "ORDER BY hot DESC, id DESC LIMIT ?"
            )
            params = (uid, status, limit)
        cur = await db.execute(query, params)
        rows = await cur.fetchall()
        return [lead_row(row) for row in rows]
    finally:
        await db.close()


async def existing_lead_keys(uid: int) -> set[str]:
    db = await conn()
    try:
        cur = await db.execute("SELECT osm_key FROM leads WHERE user_id=?", (uid,))
        return {row["osm_key"] for row in await cur.fetchall()}
    finally:
        await db.close()


async def existing_leads_for_dedupe(uid: int) -> list[dict]:
    db = await conn()
    try:
        cur = await db.execute("SELECT * FROM leads WHERE user_id=?", (uid,))
        return [_identity_row(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def set_status(uid: int, lead_id: int, status: str) -> bool:
    db = await conn()
    try:
        cur = await db.execute(
            "UPDATE leads SET status=? WHERE id=? AND user_id=?",
            (status, lead_id, uid),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def delete_lead(uid: int, lead_id: int) -> bool:
    """Удаляет лид из списка участника. Признаки бизнеса остаются закреплены (lead_tokens),
    поэтому неподходящий или нерабочий бизнес больше не попадёт в выдачу ни ему, ни другим."""
    db = await conn()
    try:
        cur = await db.execute("DELETE FROM leads WHERE id=? AND user_id=?", (lead_id, uid))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def stats(uid: int) -> dict:
    db = await conn()
    try:
        cur = await db.execute(
            """
            SELECT COUNT(*) AS total,
              SUM(status!='new') AS contacted,
              SUM(status IN ('replied', 'client')) AS replied,
              SUM(status='client') AS clients
            FROM leads WHERE user_id=?
            """,
            (uid,),
        )
        row = await cur.fetchone()
        return {
            "found": row["total"] or 0,
            "contacted": row["contacted"] or 0,
            "replied": row["replied"] or 0,
            "clients": row["clients"] or 0,
        }
    finally:
        await db.close()


async def all_users_stats() -> list[dict]:
    db = await conn()
    try:
        cur = await db.execute(
            """
            SELECT u.id, u.username, u.first_name, u.daily_limit,
              u.approved, u.is_admin, u.banned, u.trial_used, u.bonus, u.created_at,
              COALESCE((SELECT cnt FROM usage
                WHERE user_id=u.id AND day=?), 0) AS today,
              COALESCE((SELECT COUNT(*) FROM leads
                WHERE user_id=u.id), 0) AS found,
              COALESCE((SELECT COUNT(*) FROM leads
                WHERE user_id=u.id AND status!='new'), 0) AS contacted,
              COALESCE((SELECT COUNT(*) FROM leads
                WHERE user_id=u.id AND status IN ('replied', 'client')), 0) AS replied,
              COALESCE((SELECT COUNT(*) FROM leads
                WHERE user_id=u.id AND status='client'), 0) AS clients
            FROM users u WHERE u.deleted=0 ORDER BY u.approved DESC, found DESC, u.created_at DESC
            """,
            (today(),),
        )
        return [dict(row) for row in await cur.fetchall()]
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


async def approve(uid: int, approved: int = 1) -> None:
    db = await conn()
    try:
        await db.execute(
            """
            INSERT INTO users(id, approved, daily_limit, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET approved=excluded.approved
            """,
            (uid, approved, default_limit(), int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()


async def set_approved(uid: int, approved: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute(
            "UPDATE users SET approved=? WHERE id=?", (int(bool(approved)), uid)
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def approved_ids() -> list[int]:
    """Получатели рассылки: все, кто запускал бота и не заблокирован."""
    db = await conn()
    try:
        cur = await db.execute("SELECT id FROM users WHERE banned=0")
        return [row["id"] for row in await cur.fetchall()]
    finally:
        await db.close()


async def job_create(
    job_id: str, uid: int, total: int, reserved: int, usage_day: str, trial: bool = False
) -> None:
    db = await conn()
    try:
        await db.execute(
            """
            INSERT INTO jobs(id, user_id, total, reserved, usage_day, created_at, trial)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, uid, total, reserved, usage_day, int(time.time()), int(trial)),
        )
        await db.commit()
    finally:
        await db.close()


async def job_update(job_id: str, **values) -> None:
    allowed = {"found", "checked", "status", "error"}
    if not values:
        return
    if not set(values).issubset(allowed):
        raise ValueError("Unsupported job fields")
    assignments = ", ".join(f"{key}=?" for key in values)
    db = await conn()
    try:
        await db.execute(
            f"UPDATE jobs SET {assignments} WHERE id=?",
            (*values.values(), job_id),
        )
        await db.commit()
    finally:
        await db.close()


async def job_get(job_id: str, uid: int) -> dict | None:
    db = await conn()
    try:
        cur = await db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, uid)
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def recover_interrupted_jobs() -> None:
    """Return quota reserved by jobs left running after an unclean shutdown."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT id, user_id, reserved, usage_day, trial FROM jobs WHERE status='running'"
        )
        jobs = await cur.fetchall()
        for job in jobs:
            if job["trial"]:
                await db.execute(
                    "UPDATE users SET trial_used=MAX(0, trial_used-1) WHERE id=?",
                    (job["user_id"],),
                )
            await db.execute(
                """
                UPDATE usage SET cnt=MAX(0, cnt-?)
                WHERE user_id=? AND day=?
                """,
                (job["reserved"], job["user_id"], job["usage_day"]),
            )
            await db.execute(
                "UPDATE jobs SET status='error', error=? WHERE id=?",
                ("Сервер перезапустился во время поиска. Запустите поиск ещё раз.",
                 job["id"]),
            )
        await db.commit()
    finally:
        await db.close()


# ---------- Доступ: пробный период, бан, бонусные запросы ----------

def is_member(user: dict) -> bool:
    return bool(user.get("approved") or user.get("is_admin") or user.get("id") in ADMIN_IDS)


def trial_left(user: dict, trial_searches: int) -> int:
    return max(0, trial_searches + int(user.get("bonus") or 0) - int(user.get("trial_used") or 0))


async def reserve_trial(uid: int, trial_searches: int) -> bool:
    """Атомарно списывает один пробный (или купленный) запрос."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "UPDATE users SET trial_used=trial_used+1 "
            "WHERE id=? AND banned=0 AND trial_used < ? + bonus",
            (uid, trial_searches),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def refund_trial(uid: int) -> None:
    db = await conn()
    try:
        await db.execute("UPDATE users SET trial_used=MAX(0, trial_used-1) WHERE id=?", (uid,))
        await db.commit()
    finally:
        await db.close()


async def set_banned(uid: int, banned: bool) -> bool:
    db = await conn()
    try:
        if banned:
            cur = await db.execute("UPDATE users SET banned=1 WHERE id=?", (uid,))
        else:  # разбан возвращает и «удалённого» участника в списки
            cur = await db.execute("UPDATE users SET banned=0, deleted=0 WHERE id=?", (uid,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def add_bonus(uid: int, amount: int) -> int | None:
    """Добавляет (или убирает при отрицательном amount) поисковые запросы. Возвращает новый бонус."""
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "UPDATE users SET bonus=MAX(0, bonus+?) WHERE id=?", (amount, uid)
        )
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


async def grant_member(uid: int, daily_limit: int | None = None) -> None:
    db = await conn()
    try:
        await db.execute(
            """
            INSERT INTO users(id, approved, daily_limit, created_at)
            VALUES(?, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET approved=1, banned=0, deleted=0,
              daily_limit=COALESCE(?, daily_limit)
            """,
            (uid, daily_limit or default_limit(), int(time.time()), daily_limit),
        )
        await db.commit()
    finally:
        await db.close()


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
    """Активирует ключ. Возвращает (результат, ключ): ok | not_found | used | other_user | banned."""
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


# ---------- Чёрный список бизнесов ----------

async def block_tokens(tokens: set[str], label: str) -> int:
    db = await conn()
    try:
        await db.executemany(
            "INSERT OR IGNORE INTO blocked(token, label, created_at) VALUES(?, ?, ?)",
            [(token, label[:120], int(time.time())) for token in tokens],
        )
        await db.commit()
        return len(tokens)
    finally:
        await db.close()


async def list_blocked() -> list[dict]:
    db = await conn()
    try:
        rows = await (
            await db.execute(
                "SELECT label, COUNT(*) AS tokens, MIN(created_at) AS created_at "
                "FROM blocked GROUP BY label ORDER BY created_at DESC LIMIT 300"
            )
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def unblock(label: str) -> bool:
    db = await conn()
    try:
        cur = await db.execute("DELETE FROM blocked WHERE label=?", (label,))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def lead_by_id(lead_id: int) -> dict | None:
    db = await conn()
    try:
        row = await (await db.execute("SELECT * FROM leads WHERE id=?", (lead_id,))).fetchone()
        return _identity_row(row) if row else None
    finally:
        await db.close()


async def user_lead(uid: int, lead_id: int) -> dict | None:
    db = await conn()
    try:
        row = await (
            await db.execute("SELECT * FROM leads WHERE id=? AND user_id=?", (lead_id, uid))
        ).fetchone()
        return lead_row(row) if row else None
    finally:
        await db.close()


# ---------- Статистика спроса по нишам ----------

async def record_analyzed(lead: dict) -> None:
    info = lead.get("info") or {}
    key = sorted(claim_tokens(lead))
    if not key:
        return
    db = await conn()
    try:
        await db.execute(
            """
            INSERT INTO analyzed(key, niche, country, city, site, need, tg_bot, booking, priority, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET site=excluded.site, need=excluded.need,
              tg_bot=excluded.tg_bot, booking=excluded.booking, priority=excluded.priority,
              updated_at=excluded.updated_at
            """,
            (
                lead.get("osm_key") or key[0], info.get("niche") or "", lead.get("country", ""),
                lead.get("city", ""), lead.get("site", ""), lead.get("need", ""),
                int(bool(info.get("tg_bot"))),
                int(bool(info.get("booking"))), int(lead.get("hot") or 0), int(time.time()),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def niche_demand(country: str = "", days: int = 120, min_sample: int = 30) -> list[dict]:
    since = int(time.time()) - days * 86400
    db = await conn()
    try:
        params: list = [since]
        where = "updated_at>=?"
        if country:
            where += " AND country=?"
            params.append(country.upper())
        rows = await (
            await db.execute(
                f"""
                SELECT niche, COUNT(*) AS total,
                  SUM(site IN ('none','broken')) AS no_site,
                  SUM(site='weak') AS weak,
                  SUM(tg_bot=0) AS no_bot,
                  SUM(booking=0) AS no_booking,
                  AVG(priority) AS avg_priority
                FROM analyzed WHERE {where} AND niche!=''
                GROUP BY niche HAVING COUNT(*)>=?
                """,
                (*params, min_sample),
            )
        ).fetchall()
    finally:
        await db.close()
    result = []
    for row in rows:
        total = row["total"]
        result.append({
            "niche": row["niche"],
            "total": total,
            "no_site": round(100 * (row["no_site"] or 0) / total),
            "weak": round(100 * (row["weak"] or 0) / total),
            "no_bot": round(100 * (row["no_bot"] or 0) / total),
            "no_booking": round(100 * (row["no_booking"] or 0) / total),
            "avg_priority": round(row["avg_priority"] or 0),
        })
    result.sort(key=lambda item: (-(item["no_site"] + item["weak"]), -item["avg_priority"]))
    return result


# ---------- Ошибки источников ----------

async def log_source_error(provider: str, message: str) -> None:
    db = await conn()
    try:
        await db.execute(
            "INSERT INTO source_errors(provider, message, created_at) VALUES(?, ?, ?)",
            (provider, message[:400], int(time.time())),
        )
        await db.execute(
            "DELETE FROM source_errors WHERE id NOT IN "
            "(SELECT id FROM source_errors ORDER BY id DESC LIMIT 500)"
        )
        await db.commit()
    finally:
        await db.close()


async def source_errors(limit: int = 50) -> dict:
    db = await conn()
    try:
        recent = await (
            await db.execute(
                "SELECT provider, message, created_at FROM source_errors ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        ).fetchall()
        counts = await (
            await db.execute(
                "SELECT provider, COUNT(*) AS n FROM source_errors WHERE created_at>=? GROUP BY provider",
                (int(time.time()) - 86400,),
            )
        ).fetchall()
        return {
            "recent": [dict(row) for row in recent],
            "day": {row["provider"]: row["n"] for row in counts},
        }
    finally:
        await db.close()


# ---------- Админ: все лиды и статистика ----------

async def admin_leads(query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    db = await conn()
    try:
        params: list = []
        where = ""
        if query.strip():
            where = "WHERE l.name LIKE ? OR l.city LIKE ? OR l.phone LIKE ? OR u.username LIKE ?"
            like = f"%{query.strip()}%"
            params = [like, like, like, like]
        rows = await (
            await db.execute(
                f"""
                SELECT l.*, u.username, u.first_name FROM leads l
                LEFT JOIN users u ON u.id=l.user_id {where}
                ORDER BY l.id DESC LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
        ).fetchall()
        result = []
        for row in rows:
            item = lead_row(row)
            item["user_id"] = row["user_id"]
            item["owner"] = "@" + row["username"] if row["username"] else (row["first_name"] or f"id{row['user_id']}")
            result.append(item)
        return result
    finally:
        await db.close()


async def admin_overview() -> dict:
    db = await conn()
    try:
        async def one(sql, params=()):
            return await (await db.execute(sql, params)).fetchone()

        users = await one(
            "SELECT COUNT(*) AS total, SUM(approved=1) AS members, SUM(banned=1) AS banned, "
            "SUM(approved=0 AND trial_used>0) AS trial_used, "
            "SUM(approved=0 AND trial_used=0) AS trial_left FROM users"
        )
        leads = await one(
            "SELECT COUNT(*) AS total, SUM(status!='new') AS contacted, "
            "SUM(status='client') AS clients FROM leads"
        )
        niches = await (
            await db.execute(
                "SELECT CASE niche WHEN '' THEN 'Без ниши' ELSE niche END AS name, COUNT(*) AS leads, "
                "SUM(status='client') AS clients, ROUND(AVG(hot)) AS avg FROM leads "
                "GROUP BY name ORDER BY leads DESC LIMIT 30"
            )
        ).fetchall()
        cities = await (
            await db.execute(
                "SELECT country || ' · ' || city AS name, COUNT(*) AS leads, "
                "SUM(status='client') AS clients, ROUND(AVG(hot)) AS avg FROM leads "
                "GROUP BY country, city ORDER BY leads DESC LIMIT 30"
            )
        ).fetchall()
        return {
            "users": {key: users[key] or 0 for key in users.keys()},
            "leads": {key: leads[key] or 0 for key in leads.keys()},
            "niches": [dict(row) for row in niches],
            "cities": [dict(row) for row in cities],
        }
    finally:
        await db.close()


# ---------- Скрипты ----------

async def seed_scripts(defaults: list[dict]) -> None:
    db = await conn()
    try:
        await db.execute("BEGIN IMMEDIATE")
        have = {
            (row["niche"], row["kind"])
            for row in await (
                await db.execute("SELECT niche, kind FROM scripts WHERE owner_id=0")
            ).fetchall()
        }
        for item in defaults:
            if (item["niche"], item["kind"]) in have:
                continue
            await db.execute(
                "INSERT INTO scripts(owner_id, niche, kind, title, body, updated_at) VALUES(0, ?, ?, ?, ?, ?)",
                (item["niche"], item["kind"], item["title"], item["body"], int(time.time())),
            )
        await db.commit()
    finally:
        await db.close()


async def list_scripts(uid: int, niche: int | None = None) -> list[dict]:
    db = await conn()
    try:
        params: list = [uid]
        where = "owner_id IN (0, ?)"
        if niche is not None:
            where += " AND niche=?"
            params.append(niche)
        rows = await (
            await db.execute(
                f"SELECT * FROM scripts WHERE {where} ORDER BY niche, owner_id DESC, id",
                params,
            )
        ).fetchall()
        return [
            {
                "id": row["id"], "niche": row["niche"], "kind": row["kind"], "title": row["title"],
                "body": row["body"], "own": row["owner_id"] != 0,
            }
            for row in rows
        ]
    finally:
        await db.close()


async def get_script(script_id: int) -> dict | None:
    db = await conn()
    try:
        row = await (await db.execute("SELECT * FROM scripts WHERE id=?", (script_id,))).fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def save_script(owner_id: int, niche: int, kind: str, title: str, body: str,
                      script_id: int | None = None) -> int | None:
    db = await conn()
    try:
        now = int(time.time())
        if script_id:
            cur = await db.execute(
                "UPDATE scripts SET title=?, body=?, kind=?, updated_at=? WHERE id=? AND owner_id=?",
                (title, body, kind, now, script_id, owner_id),
            )
            await db.commit()
            return script_id if cur.rowcount > 0 else None
        cur = await db.execute(
            "INSERT INTO scripts(owner_id, niche, kind, title, body, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (owner_id, niche, kind, title, body, now),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def delete_script(owner_id: int, script_id: int) -> bool:
    db = await conn()
    try:
        cur = await db.execute(
            "DELETE FROM scripts WHERE id=? AND owner_id=?", (script_id, owner_id)
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


# ---------- кэш карт ----------

OSM_CACHE_TTL = 4 * 24 * 3600


def _qhash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


async def osm_cache_get(query: str, ttl: int = OSM_CACHE_TTL):
    db = await conn()
    try:
        row = await (await db.execute(
            "SELECT body, created_at FROM osm_cache WHERE qhash=?", (_qhash(query),)
        )).fetchone()
    finally:
        await db.close()
    if not row or int(time.time()) - row["created_at"] > ttl:
        return None
    try:
        return json.loads(zlib.decompress(row["body"]).decode("utf-8"))
    except (zlib.error, ValueError):
        return None


async def osm_cache_set(query: str, elements: list) -> None:
    body = zlib.compress(json.dumps(elements, ensure_ascii=False).encode("utf-8"), 6)
    now = int(time.time())
    db = await conn()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO osm_cache(qhash, body, created_at) VALUES(?,?,?)",
            (_qhash(query), body, now),
        )
        await db.execute("DELETE FROM osm_cache WHERE created_at < ?", (now - OSM_CACHE_TTL,))
        await db.commit()
    finally:
        await db.close()


# ---------- участники ----------

async def mark_bot_started(uid: int) -> None:
    db = await conn()
    try:
        await db.execute(
            "UPDATE users SET bot_started_at=COALESCE(bot_started_at, ?) WHERE id=?",
            (int(time.time()), uid),
        )
        await db.commit()
    finally:
        await db.close()


async def mark_app_opened(uid: int) -> None:
    db = await conn()
    try:
        await db.execute(
            "UPDATE users SET app_opened_at=? WHERE id=?", (int(time.time()), uid)
        )
        await db.commit()
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
            "started": bool(row["bot_started_at"]) or bool(row["created_at"]),
            "started_at": row["bot_started_at"] or row["created_at"],
            "app_opened": bool(row["app_opened_at"]),
            "app_opened_at": row["app_opened_at"],
            "banned": bool(row["banned"]),
        }
        for row in rows
    ]


async def delete_user(uid: int) -> bool:
    """«Удалить» участника: бан в боте + скрыть из списков. Лиды остаются закреплены,
    чтобы те же бизнесы не ушли повторно другим."""
    db = await conn()
    try:
        cur = await db.execute(
            "UPDATE users SET deleted=1, banned=1, approved=0 WHERE id=? AND is_admin=0", (uid,)
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def admin_ids() -> list[int]:
    db = await conn()
    try:
        rows = await (await db.execute("SELECT id FROM users WHERE is_admin=1")).fetchall()
        return [row["id"] for row in rows]
    finally:
        await db.close()
