import asyncio
import logging
import os
from datetime import datetime

from discord import (
    Attachment,
    Color,
    Embed,
    Intents,
    Interaction,
    Member,
    Message,
    SelectOption,
    User,
    app_commands,
)
from discord.ext import commands
from discord.ui import Modal, Select, TextInput, View
from dotenv import load_dotenv

from database import (
    add_guild,
    add_member,
    add_submission,
    connect_db,
    edit_label,
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

intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


class AmendModal(Modal):
    def __init__(self, id_, label, value, view):
        self.id_ = id_
        self.label = label
        self.value = value
        self.view: "AmendView" = view
        self.amend = TextInput(label=label, default=value)
        super().__init__(title="Enter the corrected data")
        self.add_item(self.amend)

    async def on_submit(self, i: Interaction):
        if self.amend.value == str(self.value):
            return await i.response.send_message("The data wasn't modified...")
        value = (
            int(self.amend.value) if self.amend.value.isdigit() else self.amend.value
        )
        await self.view.save_fails()
        try:
            await edit_label(self.id_, self.label, value)
        except Exception:
            return await i.response.send_message("Failed amending data...")
        await i.response.send_message(f"{self.label} was updated to {value}")


class AmendSelect(Select):
    def __init__(self, id_, labels):
        self.id_: int = id_
        self.labels: dict = labels
        options = [SelectOption(label=key, value=key) for key in labels]
        super().__init__(
            placeholder="Amend data...", min_values=1, max_values=1, options=options
        )

    async def callback(self, i: Interaction):
        label = self.values[0]
        await i.response.send_modal(
            AmendModal(self.id_, label, self.labels[label], self.view)
        )


class AmendView(View):
    def __init__(self, author, war, league, id_, labels):
        self.author: User = author
        self.war: Attachment = war
        self.league: Attachment = league
        self.message: Message
        super().__init__(timeout=180)
        self.add_item(AmendSelect(id_, labels))

    async def interaction_check(self, i: Interaction):
        if i.user.id != self.author.id:
            await i.response.send_message(
                "Only the person who used the command can amend the data",
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
async def register_guild(i: Interaction, guild_name: str, server_number: str):
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
    _: Interaction, current: str
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
async def register_member(i: Interaction, guild: str, member: Member):
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
async def submit(i: Interaction, war: Attachment, league: Attachment):
    await i.response.defer()

    try:
        war_data = extract_war(await war.read())
        league_data = extract_league(await league.read())
        id_ = await add_submission(**war_data, **league_data, submitted_by=i.user.name)
    except Exception as e:
        logging.error(e)
        n = len(os.listdir("fails"))
        await war.save(f"fails/war_error{n}.png")
        await league.save(f"fails/league_error{n}.png")
        return await i.followup.send(
            "Failed to read screenshots... Make sure you added them in the right order ❌"
        )

    embed = Embed(
        color=Color.green(),
        title="Screenshots recorded ✅",
    )
    labels = {}
    for data in (war_data, league_data):
        for key, value in data.items():
            labels[key] = value
            embed.add_field(name=key, value=value if value else "???")

    view = AmendView(i.user, war, league, id_, labels)
    view.message = await i.followup.send(embed=embed, view=view)


async def date_autocomplete(
    _: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await get_date(current)

    unique_dates = list(dict.fromkeys(res[0] for res in results))

    return [app_commands.Choice(name=date, value=date) for date in unique_dates]


@bot.tree.command(description="View guilds leaderboard")
@app_commands.autocomplete(date=date_autocomplete)
async def leaderboard(i: Interaction, date: str):
    await i.response.defer()

    desc = "\n".join(
        [
            f"`#{num}` {guild_name} (S{server_number}): **{total_points}** _{league} league Division: {division}_"
            for server_number, guild_name, total_points, league, division, num in await get_leaderboard(
                date
            )
        ]
    )
    embed = Embed(title="Leaderboard 🏆", description=desc, color=Color.gold())
    embed.set_footer(text=date)
    await i.followup.send(embed=embed)


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
