import aiosqlite

DB_NAME = "spacenations.xyz:3306"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_name TEXT NOT NULL,
                server_number INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                active BOOLEAN DEFAULT TRUE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_number INTEGER NOT NULL,
                guild_name TEXT NOT NULL,
                points_scored INTEGER NOT NULL,
                opponent_server INTEGER NOT NULL,
                opponent_guild TEXT NOT NULL,
                opponent_scored INTEGER NOT NULL,
                date TEXT NOT NULL,
                total_points INTEGER NOT NULL,
                rank TEXT NOT NULL,
                submitted_by TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                guild_id INTEGER NOT NULL
            )
        """)
        await db.commit()


async def add_guild(guild_name, server_number, user_id, username, registered_at):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO guilds (guild_name, server_number, user_id, username, registered_at) VALUES (?, ?, ?, ?, ?)",
            (guild_name, server_number, user_id, username, registered_at),
        )
        await db.commit()


async def get_guild(guild_name, server_number):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT * FROM guilds WHERE guild_name = ? AND server_number = ?",
            (guild_name, server_number),
        ) as cursor:
            return await cursor.fetchone()


async def add_submission(
    server_number,
    guild_name,
    points_scored,
    opponent_server,
    opponent_guild,
    opponent_scored,
    date,
    total_points,
    rank,
    submitted_by,
):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO submissions
            (server_number, guild_name, points_scored, opponent_server, opponent_guild, opponent_scored, date, total_points, rank, submitted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server_number,
                guild_name,
                points_scored,
                opponent_server,
                opponent_guild,
                opponent_scored,
                date,
                total_points,
                rank,
                submitted_by,
            ),
        )
        await db.commit()
