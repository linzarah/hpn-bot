import asyncio
import io
import logging
import os
import re
import traceback
from datetime import datetime

import cv2
import discord
import numpy as np
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
    "mine": (0.318, 0.13, 0.462, 0.3),
    "opponent": (0.617, 0.13, 0.765, 0.3),
    "date": (0.76, 0.13, 0.85, 0.167),
    "total": (0.44, 0.15, 0.65, 0.21),
    "rank": (0.142, 0.287, 0.3, 0.39),
    "rank2": (0.35, 0.288, 0.45, 0.39),
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    print(f"✅ {bot.user}: Bot started")


@bot.command()
@commands.is_owner()
async def sync(ctx):
    await bot.tree.sync()
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
        i.user.name,
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


def extract_war_info(img_bytes):
    img_array = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (10, 50, 50), (30, 255, 255))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = (
        cv2.boundingRect(max(contours, key=cv2.contourArea))
        if contours
        else (0, 0, image.shape[1], image.shape[0])
    )

    panel = Image.fromarray(
        cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2RGB)
    )
    W, H = panel.size

    coords = {
        "server_number": (0.37, 0.1, 0.457, 0.14),
        "guild_name": (0.23, 0.15, 0.457, 0.2),
        "points_scored": (0.335, 0.21, 0.405, 0.26),
        "opponent_server": (0.67, 0.1, 0.766, 0.14),
        "opponent_guild": (0.67, 0.15, 0.85, 0.2),
        "opponent_scored": (0.715, 0.21, 0.79, 0.26),
        "date": (0.85, 0.09, 0.955, 0.135),
    }

    result = {}

    for key, (x1, y1, x2, y2) in coords.items():
        label: str = pytesseract.image_to_string(
            panel.crop((x1 * W, y1 * H, x2 * W, y2 * H)), config="--psm 6"
        ).strip()
        if key in ("points_scored", "opponent_scored"):
            data = int(label)
        elif key in ("server_number", "opponent_server"):
            data = int(label.removeprefix("Server: "))
        else:
            data = label
        result[key] = data

    return result


def get_coords(name, size):
    W, H = size
    rat = W / H
    x1, y1, x2, y2 = COORDS[name]
    left = x1 * W
    top = y1 * H
    right = x2 * W
    bottom = y2 * H
    if rat < 1.5:
        left -= W / 25
        right -= W / 30
        top += H / 22
        bottom += H / 22
    elif rat < 2:
        left -= W / 12
        right -= W / 30
        bottom *= 1.1
    return left, top, right, bottom


def get_label(image: Image.Image, name) -> str:
    crop = image.crop(get_coords(name, image.size))
    crop.show()
    return pytesseract.image_to_string(crop, config="--psm 6").strip("\n]*-\|[()-_ ")


def extract_league(img_bytes):
    image = Image.open(io.BytesIO(img_bytes))
    image.save("test.png")

    result = {}
    rank = get_label(image, "rank")
    chars = 5 if "Marquis" in rank and "4" not in rank else 4
    if not rank or not any(
        [w in rank for w in ("Duke", "Duca", "Marquis", "Earl", "Viscount")]
    ):
        chars = 5
        rank = get_label(image, "rank2")
    result["rank"] = rank.replace("\n", " ")
    total = get_label(image, "total")
    result["total_points"] = int(
        re.search(r"\d+ ?\d*", total).group().replace(" ", "")[:chars]
    )

    return result


@bot.tree.command(description="Submit screenshots to register results")
@app_commands.describe(
    war="Screenshot of Guild War Log", league="Screenshot of Championsip League"
)
async def submit(
    i: discord.Interaction, war: discord.Attachment, league: discord.Attachment
):
    await i.response.defer()

    try:
        war_data = extract_war_info(await war.read())
        league_data = extract_league(await league.read())
        await add_submission(**war_data, **league_data, submitted_by=i.user.name)
    except Exception as error:
        war.save("war_error.png")
        league.save("league_error.png")
        with open("error.log", "a", encoding="utf-8") as f:
            traceback.print_exception(type(error), error, error.__traceback__, file=f)

    await i.followup.send("Screenshots recorded! ✅")


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
