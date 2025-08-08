import asyncio
import logging
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import (
    add_guild,
    add_member,
    add_submission,
    connect_db,
    get_date,
    get_guild_by_id,
    get_guilds_from_name,
    get_leaderboard,
)
from screenshots import extract_league, extract_war

logging.basicConfig(
    handlers=(
        logging.StreamHandler(),
        logging.FileHandler("error.log"),
    ),
    level=logging.ERROR,
)

load_dotenv()

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


class ReportView(discord.ui.View):
    def __init__(self, author, war, league):
        self.author: discord.User = author
        self.war: discord.Attachment = war
        self.league: discord.Attachment = league
        self.message: discord.Message
        super().__init__(timeout=180)

    @discord.ui.button(label="Report", style=discord.ButtonStyle.red, emoji="🗣️")
    async def report_button(self, i: discord.Interaction, button: discord.Button):
        await i.response.send_message("The screenshots will be reviewed ✅")
        button.disabled = True
        await self.message.edit(view=self)
        await self.save_fails()

    async def interaction_check(self, i: discord.Interaction):
        if i.user.id != self.author.id:
            await i.response.send_message(
                "Only the person who used the command can report an error",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def save_fails(self):
        n = len(os.listdir("fails"))
        await self.war.save(f"fails/war_error{n}.png")
        await self.league.save(f"fails/league_error{n}.png")


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


@bot.tree.command(description="Submit screenshots to register results")
@app_commands.describe(
    war="Screenshot of Guild War Log", league="Screenshot of Championsip League"
)
async def submit(
    i: discord.Interaction, war: discord.Attachment, league: discord.Attachment
):
    await i.response.defer()

    try:
        war_data = extract_war(await war.read())
        league_data = extract_league(await league.read())
        await add_submission(**war_data, **league_data, submitted_by=i.user.name)
    except Exception as e:
        logging.error(e)
        n = len(os.listdir("fails"))
        await war.save(f"fails/war_error{n}.png")
        await league.save(f"fails/league_error{n}.png")
        return await i.followup.send(
            "Failed to read screenshots... Make sure you added them in the right order ❌"
        )

    embed = discord.Embed(
        color=discord.Color.green(),
        title="Screenshots recorded ✅",
        description="Use the report button only if there is an error in the information detected. The screenshot will be manually reviewed and the algorythm will be corrected.",
    )
    for data in (war_data, league_data):
        for key, value in data.items():
            embed.add_field(name=key, value=value)

    view = ReportView(i.user, war, league)
    view.message = await i.followup.send(embed=embed, view=view)


async def date_autocomplete(
    _: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await get_date(current)

    unique_dates = list(dict.fromkeys(res[0] for res in results))

    return [app_commands.Choice(name=date, value=date) for date in unique_dates]


@bot.tree.command(description="View guilds leaderboard")
@app_commands.autocomplete(date=date_autocomplete)
async def leaderboard(i: discord.Interaction, date: str):
    await i.response.defer()

    desc = "\n".join(
        [
            f"`#{num}` {guild_name} (S{server_number}): **{total_points}** _{league} league Division: {division}_"
            for server_number, guild_name, total_points, league, division, num in await get_leaderboard(
                date
            )
        ]
    )
    embed = discord.Embed(
        title="Leaderboard 🏆", description=desc, color=discord.Color.gold()
    )
    embed.set_footer(text=date)
    await i.followup.send(embed=embed)


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
