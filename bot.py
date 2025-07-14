import asyncio
import io
import logging
import os
import re
from datetime import datetime

import discord
import pytesseract
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image

from database import (
    add_guild,
    add_member,
    add_submission,
    connect_db,
    get_guild_by_id,
    get_guilds_from_name,
)

logging.basicConfig()
load_dotenv()

TOKEN = os.getenv("TOKEN")
COORDS = {
    "mine": (830, 140, 1075, 300),
    "opponent": (1470, 140, 1740, 300),
    "date": (1800, 130, 1990, 190),
    "total": (1090, 177, 1320, 215),
    "rank": (500, 300, 710, 430),
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    print(f"✅ {bot.user}: Bot started")


@bot.command()
async def sync(ctx):
    try:
        print("🔄 Attempting to sync slash commands globally...")
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands globally:")
        for cmd in synced:
            print(f" - {cmd.name}")
    except Exception as e:
        print(f"⚠️ Error syncing commands: {e}")
    await ctx.send("Commands synced!")


@bot.tree.command(description="Register your guild and server")
async def register_guild(i: discord.Interaction, guild_name: str, server_number: str):
    if not i.user.guild_permissions.manage_guild:
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to register a guild.",
            ephemeral=True,
        )
        return

    await add_guild(
        guild_name,
        server_number,
        i.user.id,
        i.user.display_name,
        datetime.now(),
    )

    await i.response.send_message(
        f"✅ Guild **{guild_name}** (Server {server_number}) registered successfully!"
    )


async def guild_name_autocomplete(
    _: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    guild_data = await get_guilds_from_name(current)
    for guild_id, guild_name, server_number in guild_data:
        choices.append(
            app_commands.Choice(
                name=f"{guild_name} (S{server_number})", value=str(guild_id)
            )
        )
    return choices


@bot.tree.command(description="Register a member to a guild")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def register_member(i: discord.Interaction, guild: str, member: discord.Member):
    await i.response.defer()
    row = await get_guild_by_id(guild)

    if not row:
        return await i.followup.send(
            "❌ Guild not found. Please register your guild first.",
            ephemeral=True,
        )
    guild_id, guild_name, server_number = row

    await add_member(member, guild_id)

    await i.followup.send(
        f"✅ {member.mention}, you have been registered to guild **{guild_name}** (Server {server_number}).",
    )


def get_info_from_title(text: str) -> tuple[int, str, int]:
    for n, line in enumerate(text.split("\n")):
        if not line:
            continue
        if n == 0:
            server_number = int(line.split("Server: ")[1])
        if n == 1:
            guild = line
        if n == 3:
            points = int(re.search(r"\d+\.?\d*", line).group())
    return server_number, guild, points


async def extract_war_log(war):
    war_image = Image.open(io.BytesIO(await war.read()))

    mytext = pytesseract.image_to_string(war_image.crop(COORDS["mine"]))
    opptext = pytesseract.image_to_string(war_image.crop(COORDS["opponent"]))

    server_number, guild_name, points_scored = get_info_from_title(mytext)
    opponent_server, opponent_guild, opponent_scored = get_info_from_title(opptext)
    date = pytesseract.image_to_string(war_image.crop(COORDS["date"]))
    return (
        server_number,
        guild_name,
        points_scored,
        opponent_server,
        opponent_guild,
        opponent_scored,
        date,
    )


async def extract_league(league):
    league_image = Image.open(io.BytesIO(await league.read()))

    total_points = pytesseract.image_to_string(
        league_image.crop(COORDS["total"])
    ).replace(" ", "")
    rank = pytesseract.image_to_string(league_image.crop(COORDS["rank"])).replace(
        "\n", " "
    )

    return total_points, rank


@bot.tree.command(description="Submit screenshots to register results")
@app_commands.describe(
    war="Screenshot of Guild War Log", league="Screenshot of Championsip League"
)
async def submit(
    i: discord.Interaction, war: discord.Attachment, league: discord.Attachment
):
    await i.response.defer()
    war_data = await extract_war_log(war)
    league_data = await extract_league(league)

    await add_submission(*war_data, *league_data, i.user.display_name)

    await i.followup.send("Screenshots recorded! ✅")


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
