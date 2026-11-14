import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta, timezone
from app.config import settings

async def init_db():
    Path(settings.database_url).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, language TEXT DEFAULT 'fa',
            daily_count INTEGER DEFAULT 0, daily_date TEXT, created_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT,
            content TEXT, created_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY, expires_at TEXT, plan TEXT,
            charge_id TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS payments (
            charge_id TEXT PRIMARY KEY, user_id INTEGER, payload TEXT,
            total_amount INTEGER, currency TEXT, created_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_summaries (
            user_id INTEGER PRIMARY KEY, summary TEXT NOT NULL DEFAULT '', updated_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS warnings (
            user_id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0,
            last_reason TEXT, updated_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY, reason TEXT, banned_at TEXT
        )""")
        await db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('daily_limit',?)",
                         (str(settings.free_daily_limit),))
        await db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('enable_stars',?)",
                         ("true" if settings.enable_stars else "false",))
        await db.commit()

async def ensure_user(user_id: int, username: str | None):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT INTO users(user_id, username, language, daily_count, daily_date, created_at) "
            "VALUES(?,?,?,0,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",
            (user_id, username, settings.default_language, datetime.now(timezone.utc).date().isoformat(), now)
        )
        await db.commit()

async def get_language(user_id: int) -> str:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else settings.default_language

async def set_language(user_id: int, lang: str):
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        await db.commit()

async def get_history(user_id: int, limit: int = 20):
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cur.fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

async def add_exchange(user_id: int, user_text: str, assistant_text: str):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute("INSERT INTO messages(user_id,role,content,created_at) VALUES(?,?,?,?)",
                         (user_id, "user", user_text, now))
        await db.execute("INSERT INTO messages(user_id,role,content,created_at) VALUES(?,?,?,?)",
                         (user_id, "assistant", assistant_text, now))
        await db.commit()

async def clear_history(user_id: int):
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM user_summaries WHERE user_id=?", (user_id,))
        await db.commit()

async def consume_free_quota(user_id: int) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT daily_count,daily_date FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return False
        count, day = row
        if day != today:
            count = 0
        limit = await get_daily_limit()
        if limit == 0 or count >= limit:
            await db.execute("UPDATE users SET daily_count=?,daily_date=? WHERE user_id=?",
                             (count, today, user_id))
            await db.commit()
            return limit == 0
        await db.execute("UPDATE users SET daily_count=?,daily_date=? WHERE user_id=?",
                         (count + 1, today, user_id))
        await db.commit()
        return True

async def is_pro(user_id: int) -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if not row:
        return False
    try:
        return datetime.fromisoformat(row[0]) > datetime.now(timezone.utc)
    except ValueError:
        return False

async def activate_pro(user_id: int, charge_id: str, days: int):
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        base = now
        if row:
            try:
                old = datetime.fromisoformat(row[0])
                if old > now:
                    base = old
            except ValueError:
                pass
        expiry = (base + timedelta(days=days)).isoformat()
        await db.execute(
            "INSERT INTO subscriptions(user_id,expires_at,plan,charge_id) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at,plan=excluded.plan,charge_id=excluded.charge_id",
            (user_id, expiry, "pro", charge_id)
        )
        await db.commit()

async def revoke_pro(user_id: int) -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount > 0

async def record_payment(charge_id, user_id, payload, amount, currency):
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT OR IGNORE INTO payments(charge_id,user_id,payload,total_amount,currency,created_at) VALUES(?,?,?,?,?,?)",
            (charge_id, user_id, payload, amount, currency, datetime.now(timezone.utc).isoformat())
        )
        await db.commit()

async def payment_exists(charge_id):
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT 1 FROM payments WHERE charge_id=?", (charge_id,))
        return await cur.fetchone() is not None

async def stats():
    async with aiosqlite.connect(settings.database_url) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM users")
        users = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT COUNT(*) FROM subscriptions WHERE expires_at > ?", (datetime.now(timezone.utc).isoformat(),))
        subs = (await c2.fetchone())[0]
    return users, subs

async def message_stats():
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        c1 = await db.execute("SELECT COUNT(*) FROM messages")
        total = (await c1.fetchone())[0]
        c2 = await db.execute("SELECT COUNT(*) FROM messages WHERE created_at LIKE ?", (f"{today}%",))
        today_count = (await c2.fetchone())[0]
    return total, today_count

async def all_user_ids():
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT user_id FROM users")
        return [row[0] for row in await cur.fetchall()]

async def get_daily_limit() -> int:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT value FROM app_settings WHERE key='daily_limit'")
        row = await cur.fetchone()
    return int(row[0]) if row else settings.free_daily_limit

async def set_daily_limit(limit: int):
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT INTO app_settings(key,value) VALUES('daily_limit',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(limit),)
        )
        await db.commit()

async def stars_enabled() -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT value FROM app_settings WHERE key='enable_stars'")
        row = await cur.fetchone()
    if row is None:
        return settings.enable_stars
    return row[0] == "true"

async def set_stars_enabled(value: bool):
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT INTO app_settings(key,value) VALUES('enable_stars',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("true" if value else "false",)
        )
        await db.commit()

async def add_warning(user_id: int, reason: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT count FROM warnings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        count = (row[0] if row else 0) + 1
        await db.execute(
            "INSERT INTO warnings(user_id,count,last_reason,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET count=excluded.count,"
            "last_reason=excluded.last_reason,updated_at=excluded.updated_at",
            (user_id, count, reason, now)
        )
        await db.commit()
    return count

async def warning_count(user_id: int) -> int:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT count FROM warnings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    return row[0] if row else 0

async def clear_warnings(user_id: int) -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("DELETE FROM warnings WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount > 0

async def recent_warnings(limit: int = 10):
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute(
            "SELECT user_id,count,last_reason,updated_at FROM warnings "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        return await cur.fetchall()

async def warning_total() -> int:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT COALESCE(SUM(count),0) FROM warnings")
        return (await cur.fetchone())[0]

async def ban_user(user_id: int, reason: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT INTO banned_users(user_id,reason,banned_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason,banned_at=excluded.banned_at",
            (user_id, reason, now)
        )
        await db.commit()

async def unban_user(user_id: int) -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount > 0

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None

async def banned_total() -> int:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT COUNT(*) FROM banned_users")
        return (await cur.fetchone())[0]

async def get_summary(user_id: int) -> str:
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT summary FROM user_summaries WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    return row[0] if row else ""

async def get_compaction_batch(user_id: int, keep_recent: int, threshold: int):
    async with aiosqlite.connect(settings.database_url) as db:
        cur = await db.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,))
        count = (await cur.fetchone())[0]
        if count <= threshold:
            return []
        cur = await db.execute(
            "SELECT id,role,content FROM messages WHERE user_id=? ORDER BY id ASC LIMIT ?",
            (user_id, count - keep_recent),
        )
        return await cur.fetchall()

async def save_summary_and_delete(user_id: int, summary: str, message_ids: list[int]):
    if not message_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.database_url) as db:
        await db.execute(
            "INSERT INTO user_summaries(user_id,summary,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET summary=excluded.summary,updated_at=excluded.updated_at",
            (user_id, summary[:6000], now),
        )
        placeholders = ",".join("?" for _ in message_ids)
        await db.execute(f"DELETE FROM messages WHERE user_id=? AND id IN ({placeholders})",
                         [user_id, *message_ids])
        await db.commit()
