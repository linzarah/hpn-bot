import aiosqlite

DB_NAME = "hpn_bot.db"

async def init_db():
  import aiosqlite

async def init_db():
    async with aiosqlite.connect("hpn_bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_name TEXT NOT NULL,
                guild_server INTEGER NOT NULL,
                opponent_name TEXT NOT NULL,
                opponent_server INTEGER NOT NULL,
                points_scored INTEGER NOT NULL,
                points_total INTEGER NOT NULL,
                rank TEXT,
                submitted_by TEXT NOT NULL,
                submission_time TEXT NOT NULL
            )
        """)
        await db.commit()


async def add_guild(guild_name, server_number, registered_by):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO guilds (guild_name, server_number, registered_by) VALUES (?, ?, ?)",
            (guild_name, server_number, registered_by)
        )
        await db.commit()

async def get_guild_by_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, guild_name, server_number FROM guilds WHERE registered_by = ?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone()

async def add_submission(guild_id, opponent_guild, opponent_server, points_scored, points_total, rank, submitted_by):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO submissions
            (guild_id, opponent_guild, opponent_server, points_scored, points_total, rank, submitted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, opponent_guild, opponent_server, points_scored, points_total, rank, submitted_by)
        )
        await db.commit()

async def get_latest_submissions(limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            """
            SELECT s.id, g.guild_name, g.server_number, s.opponent_guild, s.opponent_server,
                   s.points_scored, s.points_total, s.rank, s.timestamp
            FROM submissions s
            JOIN guilds g ON s.guild_id = g.id
            ORDER BY s.timestamp DESC
            LIMIT ?
            """,
            (limit,)
        ) as cursor:
            return await cursor.fetchall()
