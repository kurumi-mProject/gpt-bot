import aiosqlite

DB = "/root/vpn_bot/vpn.db"

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                model TEXT,
                role TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                user_id INTEGER PRIMARY KEY,
                model TEXT DEFAULT 'gpt-5-nano',
                system_prompt TEXT DEFAULT NULL,
                mode TEXT DEFAULT 'default',
                msg_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for col, defn in [("system_prompt","TEXT DEFAULT NULL"),("msg_count","INTEGER DEFAULT 0"),("mode","TEXT DEFAULT 'default'")]:
            try:
                await db.execute(f"ALTER TABLE chat_sessions ADD COLUMN {col} {defn}")
            except Exception:
                pass
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def get_session(user_id: int):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chat_sessions WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def set_model(user_id: int, model: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chat_sessions (user_id, model, updated_at) VALUES (?,?,datetime('now'))",
            (user_id, model)
        )
        await db.commit()

async def set_system_prompt(user_id: int, prompt: str | None):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO chat_sessions (user_id, system_prompt) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET system_prompt=excluded.system_prompt",
            (user_id, prompt)
        )
        await db.commit()

async def get_history(user_id: int, model: str, limit: int = 12):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM chat_history WHERE user_id=? AND model=? ORDER BY id DESC LIMIT ?",
            (user_id, model, limit)
        ) as cur:
            rows = await cur.fetchall()
    return list(reversed(rows))

async def add_message(user_id: int, model: str, role: str, content: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO chat_history (user_id, model, role, content) VALUES (?,?,?,?)",
            (user_id, model, role, content)
        )
        if role == "user":
            await db.execute(
                "INSERT INTO chat_sessions (user_id, msg_count) VALUES (?,1) "
                "ON CONFLICT(user_id) DO UPDATE SET msg_count=msg_count+1",
                (user_id,)
            )
        await db.commit()

async def clear_history(user_id: int, model: str = None):
    async with aiosqlite.connect(DB) as db:
        if model:
            await db.execute("DELETE FROM chat_history WHERE user_id=? AND model=?", (user_id, model))
        else:
            await db.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
        await db.commit()

async def get_msg_count(user_id: int) -> int:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT msg_count FROM chat_sessions WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def get_last_user_message(user_id: int, model: str) -> str | None:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT content FROM chat_history WHERE user_id=? AND model=? AND role='user' ORDER BY id DESC LIMIT 1",
            (user_id, model)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None
