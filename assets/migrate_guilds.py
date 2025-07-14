import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database import add_guild, connect_db, get_guild, init_db

with open("assets/guilds.csv", encoding="utf-8") as file:
    data = file.read()


async def main():
    await connect_db()
    await init_db()

    for line in data.split("\n"):
        try:
            guild_name, server_number = line.split(";")
            if "guild_name" in guild_name:
                continue
        except ValueError:
            break

        if await get_guild(guild_name, server_number):
            continue

        await add_guild(
            guild_name,
            server_number,
            570001399161683988,
            "Linzarah",
            datetime.now(),
        )


asyncio.run(main())
