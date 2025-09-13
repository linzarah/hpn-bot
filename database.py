import os

import aiomysql
from dotenv import load_dotenv
from pymysql.err import IntegrityError

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


async def get_opponent_guilds_from_name(current):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT DISTINCT opponent_guild, opponent_server FROM submissions WHERE opponent_guild LIKE %s LIMIT 25",
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


async def add_guild(
    guild_name, server_number, user_id, username, registered_at
) -> bool:
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    """INSERT INTO guilds (guild_name, server_number, user_id, username, registered_at)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (guild_name, server_number, user_id, username, registered_at),
                )
            except IntegrityError as e:
                if e.args[0] == 1062:
                    return False
                else:
                    raise e
            return True


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
                    guild_id, points_scored, opponent_server, opponent_guild,
                    opponent_scored, date, total_points, league, division, submitted_by
                )
                SELECT m.guild_id, %s, %s, %s, %s, %s, %s, %s, %s, m.user_id
                FROM members m
                WHERE m.user_id = %s
                ON DUPLICATE KEY UPDATE
                    guild_id = VALUES(guild_id),
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
                    """SELECT id FROM submissions
                    WHERE submitted_by = %s AND date = %s""",
                    (submitted_by, date),
                )
                row = await cursor.fetchone()
                return row[0] if row else None


async def edit_label(record_id: int, label: str, new_value) -> bool:
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            if label not in {
                "points_scored",
                "opponent_server",
                "opponent_guild",
                "opponent_scored",
                "date",
                "total_points",
                "league",
                "division",
            }:
                raise ValueError(f"Invalid label: {label}")

            query = f"UPDATE submissions SET {label} = %s WHERE id = %s"
            try:
                await cursor.execute(query, (new_value, record_id))
            except IntegrityError as e:
                if e.args[0] == 1062:
                    await cursor.execute(
                        "DELETE FROM submissions WHERE id = %s", (record_id,)
                    )
                    return False
                else:
                    raise e
            return True


async def get_leaderboard(date):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT server_number, guild_name, total_points, league, division, RANK() OVER (ORDER BY total_points DESC)
                FROM submissions
                JOIN guilds ON guilds.id = guild_id
                WHERE date = %s;""",
                (date,),
            )
            return await cursor.fetchall()


async def get_date(current):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT DISTINCT date FROM submissions WHERE date LIKE %s ORDER BY date DESC LIMIT 25; ",
                (f"%{current}%",),
            )
            return await cursor.fetchall()


async def get_latest_date():
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT MAX(date) FROM submissions;")
            res = await cursor.fetchone()
            return res[0]


async def get_records_data(guild_id, since=None, until=None, opponent=False):
    if opponent:
        query = """SELECT server_number, guild_name, opponent_scored, points_scored, date, result
        FROM submissions
        JOIN guilds ON guilds.id = guild_id
        WHERE opponent_guild = %s AND opponent_server = %s"""
        params = guild_id
    else:
        query = """SELECT opponent_server, opponent_guild, points_scored, opponent_scored, date, result
        FROM submissions
        WHERE guild_id = %s"""
        params = [guild_id,]

    if since is not None:
        query += " AND date >= %s"
        params.append(since)
    if until is not None:
        query += " AND date <= %s"
        params.append(until)

    query += " ORDER BY date DESC"

    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchall()


async def get_missing_submissions(since):
    query = """SELECT g.id, g.guild_name, g.server_number, m.user_id
        FROM guilds g
        LEFT JOIN submissions s 
            ON g.id = s.guild_id
        AND s.date >= %s
        LEFT JOIN members m
            ON g.id = m.guild_id
        WHERE s.guild_id IS NULL;"""

    async with pool.acquire() as conn, conn.cursor() as cursor:
        await cursor.execute(query, (since,))
        rows = await cursor.fetchall()
        if not rows:
            return []

        guilds = {}
        for guild_id, guild_name, server_number, user_id in rows:
            if guild_id not in guilds:
                guilds[guild_id] = {
                    "guild_name": guild_name,
                    "server_number": server_number,
                    "members": [],
                }
            if user_id:
                guilds[guild_id]["members"].append(user_id)

    return list(guilds.values())


async def get_guild_from_member(user_id):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT guild_id FROM members WHERE user_id = %s",
                (user_id,),
            )
            return await cursor.fetchone()


async def rename_guild(guild_id, new_name):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE guilds SET guild_name = %s WHERE id = %s",
                (
                    new_name,
                    guild_id,
                ),
            )
            return cursor.rowcount > 0


async def reset_guild_server(guild_id, new_server):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE guilds SET server_number = %s WHERE id = %s",
                (
                    new_server,
                    guild_id,
                ),
            )
            return cursor.rowcount > 0


async def delete_guild_from_db(guild_id):
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "DELETE FROM guilds WHERE id = %s",
                (guild_id,),
            )
            return cursor.rowcount > 0
