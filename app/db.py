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

async def get_history(user_id: int, limit: int = 12):
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
        if count >= settings.free_daily_limit:
            return False
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
