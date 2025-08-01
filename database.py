import os

import aiomysql
from dotenv import load_dotenv

load_dotenv()

pool = None


async def connect_db():
    global pool
    pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        autocommit=True,
    )


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
                    rank VARCHAR(50) NOT NULL,
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
            results = await cursor.fetchall()
            return results


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
    rank,
    submitted_by,
):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO submissions
                (server_number, guild_name, points_scored, opponent_server, opponent_guild,
                 opponent_scored, date, total_points, rank, submitted_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
