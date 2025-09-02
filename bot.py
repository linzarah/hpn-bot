import asyncio
import contextlib
import logging
import os
from datetime import date, datetime

from discord import (
    Attachment,
    ButtonStyle,
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
from discord.errors import NotFound
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, View, button
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
    get_latest_date,
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


class Paginator:
    def __init__(self, **kwargs) -> None:
        self.rows: list[str] = kwargs.get("leaderboard")
        self.i: Interaction = kwargs.get("interaction")
        self.display_filters: str = kwargs.get("display_filters")
        self.ITEMS_PER_PAGE = 20
        self.view = (
            PaginatorView(self.i, self, timeout=30)
            if len(self.rows) > self.ITEMS_PER_PAGE
            else None
        )

        self.page = kwargs.get("page", 1)
        calculation = len(self.rows) / self.ITEMS_PER_PAGE
        self.total_pages = (
            int(calculation) if calculation.is_integer() else int(calculation) + 1
        )
        if self.total_pages == 0:
            self.total_pages = 1

    def _get_rows(self) -> list[dict]:
        return self.rows[
            (self.page - 1) * self.ITEMS_PER_PAGE : self.page * self.ITEMS_PER_PAGE
        ]

    def _build_embed(self):
        embed = Embed(
            description="" if self.rows else "No results found", color=Color.gold()
        )

        for (
            server_number,
            guild_name,
            total_points,
            league,
            division,
            num,
        ) in self._get_rows():
            embed.add_field(
                name=f"#{num} {guild_name} (S{server_number})",
                value=f"`{total_points}` {league} League {division}",
                inline=False,
            )

        embed.set_footer(text=f"Page {self.page}/{self.total_pages}")
        embed.set_author(
            name=f"🏆 Leaderboard - {self.display_filters}",
        )
        return embed

    @property
    def embed(self) -> Embed:
        return self._build_embed()

    async def send_message(self, i: Interaction):
        if not i.command:
            self.view.update_buttons()
            await i.followup.edit_message(
                message_id=i.message.id, embed=self.embed, view=self.view
            )
        elif self.view:
            await i.followup.send(embed=self.embed, view=self.view)
        else:
            await i.followup.send(embed=self.embed)


class PaginatorView(View):
    def __init__(self, i, paginator, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.i: Interaction = i
        self.paginator: Paginator = paginator

    async def on_timeout(self):
        if self.paginator.i:
            with contextlib.suppress(NotFound):
                m = await self.paginator.i.original_response()
                await m.edit(view=None)

    async def interaction_check(self, i: Interaction) -> bool:
        await i.response.defer()
        if i.user != self.i.user:
            await i.followup.send(
                "This is not your leaderboard.",
            )
            return False
        return True

    async def callback(self, interaction: Interaction, button: Button):
        if button.custom_id == "stop":
            await interaction.message.delete()
            return self.stop()
        if button.custom_id == "last":
            self.paginator.page -= 1
            return await self.paginator.send_message(interaction)
        if button.custom_id == "next":
            self.paginator.page += 1
            return await self.paginator.send_message(interaction)
        if button.custom_id == "fastlast":
            self.paginator.page = 1
            return await self.paginator.send_message(interaction)
        if button.custom_id == "fastnext":
            self.paginator.page = self.paginator.total_pages
            return await self.paginator.send_message(interaction)

    def update_buttons(self):
        last_disable = self.paginator.page <= 1
        next_disable = self.paginator.page >= self.paginator.total_pages
        self.children[0].disabled = last_disable
        self.children[1].disabled = last_disable
        self.children[-2].disabled = next_disable
        self.children[-1].disabled = next_disable

    @button(
        emoji="⏪",
        custom_id="fastlast",
        style=ButtonStyle.secondary,
        disabled=True,
    )
    async def fastlast_callback(self, interaction: Interaction, button: Button):
        return await self.callback(interaction, button)

    @button(emoji="◀", custom_id="last", style=ButtonStyle.secondary, disabled=True)
    async def last_callback(self, interaction: Interaction, button: Button):
        return await self.callback(interaction, button)

    @button(emoji="❌", custom_id="stop", style=ButtonStyle.secondary)
    async def stop_callback(self, interaction: Interaction, button: Button):
        return await self.callback(interaction, button)

    @button(
        emoji="▶️",
        custom_id="next",
        style=ButtonStyle.secondary,
        disabled=False,
    )
    async def next_callback(self, interaction: Interaction, button: Button):
        return await self.callback(interaction, button)

    @button(
        emoji="⏩",
        custom_id="fastnext",
        style=ButtonStyle.secondary,
        disabled=False,
    )
    async def fastnext_callback(self, interaction: Interaction, button: Button):
        return await self.callback(interaction, button)


class AmendModal(Modal):
    def __init__(self, id_, label, value, view):
        self.id_ = id_
        self.label = label
        self.value = value
        self.view: "AmendView" = view
        if label == "date":
            label = "date [YYY-mm-dd]"
        self.amend = TextInput(label=label, default=str(value))
        super().__init__(title="Enter the corrected data")
        self.add_item(self.amend)

    async def on_submit(self, i: Interaction):
        if self.amend.value == str(self.value):
            return await i.response.send_message("The data wasn't modified...")

        if self.label in (
            "server_number",
            "points_scored",
            "opponent_server",
            "opponent_scored",
            "total_points",
            "division",
        ):
            if not self.amend.value.isdigit():
                return await i.response.send_message(f"{self.label} must be a number")
            value = int(self.amend.value)
        elif self.label == "date":
            year, month, day = self.amend.value.split("-")
            try:
                value = date(int(year), int(month), int(day))
            except Exception:
                return await i.response.send_message(
                    "Wrong date format, must be YYYY-mm-dd"
                )
        else:
            value = self.amend.value

        await self.view.save_fails()
        try:
            await edit_label(self.id_, self.label, value)
        except Exception as e:
            logging.error(e)
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
        super().__init__(timeout=60 * 15)
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
    return [app_commands.Choice(name=str(date), value=str(date)) for date in results]


@bot.tree.command(description="View guilds leaderboard")
@app_commands.autocomplete(date=date_autocomplete)
async def leaderboard(i: Interaction, date: str = None):
    await i.response.defer()
    if date is None:
        date = await get_latest_date()
        date = str(date)
        print(date)

    paginator = Paginator(
        leaderboard=await get_leaderboard(date),
        interaction=i,
        display_filters=date,
    )
    await paginator.send_message(i)


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
