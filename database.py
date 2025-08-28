import os

import aiomysql
from dotenv import load_dotenv

load_dotenv()

pool: aiomysql.Pool = None


async def connect_db():
    global pool
    pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        autocommit=True,
    )


async def close_db():
    pool.close()
    await pool.wait_closed()


async def init_db():
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_name VARCHAR(255) NOT NULL,
                    server_number INT NOT NULL,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    registered_at DATETIME NOT NULL,
                    active TINYINT(1) DEFAULT 1
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    server_number INT NOT NULL,
                    guild_name VARCHAR(255) NOT NULL,
                    points_scored INT NOT NULL,
                    opponent_server INT NOT NULL,
                    opponent_guild VARCHAR(255) NOT NULL,
                    opponent_scored INT NOT NULL,
                    date VARCHAR(50) NOT NULL,
                    total_points INT NOT NULL,
                    league VARCHAR(50) NOT NULL,
                    division INT NOT NULL,
                    submitted_by VARCHAR(255) NOT NULL
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    guild_id INT NOT NULL
                )
            """)


async def get_guild(guild_name, server_number):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM guilds WHERE guild_name = %s AND server_number = %s",
                (guild_name, server_number),
            )
            return await cursor.fetchone()


async def get_guilds_from_name(current):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, guild_name, server_number FROM guilds WHERE guild_name LIKE %s LIMIT 25",
                (f"%{current}%",),
            )
            return await cursor.fetchall()


async def get_guild_by_id(guild):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, guild_name, server_number FROM guilds WHERE id = %s",
                (guild,),
            )
            return await cursor.fetchone()


async def add_guild(guild_name, server_number, user_id, username, registered_at):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO guilds (guild_name, server_number, user_id, username, registered_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (guild_name, server_number, user_id, username, registered_at),
            )


async def add_member(member, guild_id):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO members (user_id, username, guild_id)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE username = VALUES(username), guild_id = VALUES(guild_id)
                """,
                (member.id, member.name, guild_id),
            )


async def add_submission(
    server_number,
    guild_name,
    points_scored,
    opponent_server,
    opponent_guild,
    opponent_scored,
    date,
    total_points,
    league,
    division,
    submitted_by,
):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO submissions (
                    server_number, guild_name, points_scored, opponent_server, opponent_guild,
                    opponent_scored, date, total_points, league, division, submitted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    points_scored = VALUES(points_scored),
                    opponent_server = VALUES(opponent_server),
                    opponent_guild = VALUES(opponent_guild),
                    opponent_scored = VALUES(opponent_scored),
                    total_points = VALUES(total_points),
                    league = VALUES(league),
                    division = VALUES(division),
                    submitted_by = VALUES(submitted_by)
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
                    league,
                    division,
                    submitted_by,
                ),
            )

            if cursor.lastrowid:
                return cursor.lastrowid
            else:
                await cursor.execute(
                    """
                    SELECT id FROM submissions
                    WHERE server_number = %s AND guild_name = %s AND date = %s
                    """,
                    (server_number, guild_name, date),
                )
                row = await cursor.fetchone()
                return row[0] if row else None


async def edit_label(record_id: int, label: str, new_value):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            if label not in {
                "server_number",
                "guild_name",
                "points_scored",
                "opponent_server",
                "opponent_guild",
                "opponent_scored",
                "date",
                "total_points",
                "league",
                "division",
                "submitted_by",
            }:
                raise ValueError(f"Invalid label: {label}")

            query = f"UPDATE submissions SET {label} = %s WHERE id = %s"
            await cursor.execute(query, (new_value, record_id))
            await conn.commit()


async def get_leaderboard(date):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT server_number, guild_name, total_points, league, division, RANK() OVER (ORDER BY total_points DESC) AS num
                FROM submissions WHERE date = %s
                ORDER BY total_points DESC;
                """,
                (date,),
            )
            return await cursor.fetchall()


async def get_latest_date(current):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT date FROM submissions WHERE date LIKE %s LIMIT 25",
                (f"%{current}%",),
            )
            return await cursor.fetchall()
