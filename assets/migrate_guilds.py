import asyncio
from datetime import datetime

from database import add_guild, get_guild


with open("guilds.csv", encoding="utf-8") as file:
    data = file.read()

async def main():
    for line in data.split("\n"):
        try:
            guild_name, server_number = line.split(";")
        except ValueError:
            break

        if await get_guild(guild_name, server_number):
            continue

        await add_guild(guild_name, server_number, 570001399161683988, "Linzarah", datetime.now().strftime(format="%d/%m/%Y, %H:%M:%S"))

asyncio.run(main())