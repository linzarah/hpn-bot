import asyncio
import contextlib
import csv
import io
import logging
import os
import traceback
from datetime import date, datetime, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta
from discord import (
    Attachment,
    ButtonStyle,
    Color,
    Embed,
    File,
    Intents,
    Interaction,
    Member,
    Message,
    Object,
    PermissionOverwrite,
    SelectOption,
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
    delete_guild_from_db,
    edit_label,
    get_date,
    get_guild_by_id,
    get_guild_from_member,
    get_guilds_from_name,
    get_inactive_members,
    get_kudos_history,
    get_latest_date,
    get_leaderboard,
    get_missing_submissions,
    get_opponent_guilds_from_name,
    get_records_data,
    give_kudo_and_get_guild_info,
    remove_inactive_members,
    rename_guild,
    reset_guild_server,
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
MAIN_GUILD = 1325720729240600627
KUDOS_CHANNEL = 1442610115860631642
REMINDER_ROLE = 1419076867930984611

intents = Intents.default()
intents.message_content = True


class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self) -> None:
        self.add_view(AmendView())

    async def on_ready(self):
        print(f"Bot started as {self.user} (ID: {self.user.id})")


bot = DiscordBot()

LABELS = {
    "points_scored",
    "league",
    "division",
    "opponent_server",
    "opponent_guild",
    "opponent_scored",
    "date",
    "total_points",
}

RESULT_MAP = {"Win": "🟩", "Loss": "🟥", "Draw": "⬜"}


def is_staff(i: Interaction):
    return (
        i.user.guild_permissions.manage_guild
        or i.user.guild_permissions.administrator
        or Object(1363113680916709376) in i.user.roles
    )


class ConfirmView(View):
    def __init__(self):
        super().__init__()
        self.value = None

    @button(label="✅ Confirm", style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, _: Button):
        self.value = True
        self.stop()
        await interaction.response.edit_message(content="Confirmed ✅", view=None)

    @button(label="❌ Cancel", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, _: Button):
        self.value = False
        self.stop()
        await interaction.response.edit_message(content="Cancelled ❌", view=None)


class LeaderboardPaginator:
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


class RecordsPaginator:
    def __init__(
        self,
        data,
        guild_name,
        display_date,
        summary,
        interaction,
        opponent=False,
        **kwargs,
    ) -> None:
        self.data: list[tuple] = data
        self.guild_name: str = guild_name
        self.display_date: str = display_date
        self.summary: str = summary
        self.i: Interaction = interaction
        self.opponent: bool = opponent
        self.ITEMS_PER_PAGE = 20
        self.view = (
            PaginatorView(self.i, self, timeout=30)
            if len(self.data) > self.ITEMS_PER_PAGE
            else None
        )

        self.page = kwargs.get("page", 1)
        calculation = len(self.data) / self.ITEMS_PER_PAGE
        self.total_pages = (
            int(calculation) if calculation.is_integer() else int(calculation) + 1
        )
        if self.total_pages == 0:
            self.total_pages = 1

    def _get_rows(self) -> list[dict]:
        return self.data[
            (self.page - 1) * self.ITEMS_PER_PAGE : self.page * self.ITEMS_PER_PAGE
        ]

    def _build_embed(self):
        embed = Embed(
            title=self.guild_name,
            description=self.summary if self.data else "No results found",
            color=Color.blue(),
        )

        for (
            other_server,
            other_name,
            me_scored,
            other_scored,
            submission_date,
            result,
        ) in self._get_rows():
            if self.opponent:
                if result == "Win":
                    result = "Loss"
                elif result == "Loss":
                    result = "Win"
            embed.add_field(
                name=f"{self.guild_name} - {other_name} (S{other_server})",
                value=f"{RESULT_MAP[result]} {submission_date} `{me_scored}` - `{other_scored}`",
                inline=False,
            )

        embed.set_footer(text=f"Page {self.page}/{self.total_pages}")
        embed.set_author(name=f"Opponent Data - {self.display_date}")
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


class MissingSubmissionPaginator:
    def __init__(self, data, period, interaction, **kwargs) -> None:
        self.data: dict[int, dict] = data
        self.period: str = period
        self.i: Interaction = interaction
        self.ITEMS_PER_PAGE = 25
        self.view = (
            PaginatorView(self.i, self, missing_submissions=data, timeout=300)
            if len(self.data) > self.ITEMS_PER_PAGE
            else None
        )

        self.page = kwargs.get("page", 1)
        calculation = len(self.data) / self.ITEMS_PER_PAGE
        self.total_pages = (
            int(calculation) if calculation.is_integer() else int(calculation) + 1
        )
        if self.total_pages == 0:
            self.total_pages = 1

    def _get_rows(self):
        return self.data[
            (self.page - 1) * self.ITEMS_PER_PAGE : self.page * self.ITEMS_PER_PAGE
        ]

    def _build_embed(self):
        embed = Embed(
            title=f"Missing submissions - {self.period}",
            description="" if self.data else "No results found",
            color=Color.dark_gold(),
        )

        for guild_d in self._get_rows():
            members = [f"<@{member_id}>" for member_id in guild_d["members"]]
            embed.add_field(
                name=f"{guild_d['guild_name']} (S{guild_d['server_number']})",
                value=", ".join(members),
            )

        embed.set_footer(text=f"Page {self.page}/{self.total_pages}")
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


class RemindButton(Button):
    def __init__(self, missing_submissions):
        super().__init__(
            style=ButtonStyle.blurple,
            label="Remind all",
            emoji="🔔",
            row=2,
        )
        self.members = [m for g in missing_submissions for m in g["members"]]

    async def callback(self, i: Interaction):
        start = await i.followup.send("Started sending notification DM's...", wait=True)
        embed = Embed(
            title="Screenshot submission reminder",
            description="Hello 👋,\n\nI'm the HPN bot! My goal is to provide an accurate daily leaderboard by gathering information submitted by guilds, but your guild has no recent war submissions.\n\nGuilds are requested to do daily screenshots of GC, but membership requires at least one submission every week. Please submit information soon, as your guild may receive a strike per our <#1325808876293193790>\n\nThank you for being a part of our community!",
            color=Color.orange(),
        )
        for member_id in self.members:
            try:
                member = await i.guild.fetch_member(member_id)
            except NotFound:
                continue
            await member.send(embed=embed)
            await asyncio.sleep(10)
        await start.edit(content="Submission reminders sent successfully ✅")


class ExtractCSVButton(Button):
    def __init__(self, missing_submissions):
        super().__init__(
            style=ButtonStyle.secondary,
            label="Extract data to CSV",
            emoji="🖨️",
            row=2,
        )
        self.missing_submissions: list[dict] = missing_submissions

    async def callback(self, i: Interaction):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["guild_name", "server_number", "members"])

        for g in self.missing_submissions:
            members_str = ", ".join(map(str, g["members"]))
            writer.writerow([g["guild_name"], g["server_number"], members_str])
        output.seek(0)
        file = File(
            io.BytesIO(output.getvalue().encode()), filename="missing_guilds.csv"
        )
        await i.followup.send("Guilds missing submissions exported", file=file)


class PaginatorView(View):
    def __init__(self, i, paginator, missing_submissions=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.i: Interaction = i
        self.paginator: (
            LeaderboardPaginator | MissingSubmissionPaginator | RecordsPaginator
        ) = paginator
        if isinstance(paginator, MissingSubmissionPaginator):
            self.add_item(RemindButton(missing_submissions))
            self.add_item(ExtractCSVButton(missing_submissions))

    async def on_timeout(self):
        if self.paginator.i:
            with contextlib.suppress(NotFound):
                m = await self.paginator.i.original_response()
                await m.edit(view=None)

    async def interaction_check(self, i: Interaction) -> bool:
        await i.response.defer()
        if i.user != self.i.user:
            await i.followup.send("This is not your embed.")
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
        self.children[3].disabled = next_disable
        self.children[4].disabled = next_disable

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
    def __init__(self, id_, label, value, message, field_index):
        self.id_ = id_
        self.label = label
        self.value = value
        self.message: Message = message
        self.field_index: int = field_index
        if label == "date":
            label = "date [YYY-mm-dd]"
        self.amend = TextInput(
            label=label, default=str(value) if value is not None else None
        )
        super().__init__(title="Enter the corrected data")
        self.add_item(self.amend)

    async def on_submit(self, i: Interaction):
        await i.response.defer()
        if self.amend.value == str(self.value):
            return await i.followup.send("The data wasn't modified...")

        if self.label in (
            "points_scored",
            "opponent_server",
            "opponent_scored",
            "total_points",
            "division",
        ):
            if not self.amend.value.isdigit():
                return await i.followup.send(f"{self.label} must be a number")
            value = int(self.amend.value)
        elif self.label == "date":
            year, month, day = self.amend.value.split("-")
            try:
                value = date(int(year), int(month), int(day))
            except Exception:
                return await i.followup.send("Wrong date format, must be YYYY-mm-dd")
        else:
            value = self.amend.value

        try:
            await edit_label(self.id_, self.label, value)
        except Exception as e:
            logging.error("FAILED EDIT LABEL", e)
            return await i.followup.send("Failed amending data...")
        await i.followup.send(f"{self.label} was updated to {value}")
        n_embed = self.message.embeds[0]
        n_embed.set_field_at(self.field_index, name=self.label, value=value)
        await self.message.edit(embed=n_embed)


class AmendSelect(Select):
    def __init__(self):
        options = [SelectOption(label=key, value=key) for key in LABELS]
        super().__init__(
            placeholder="Amend data...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="amend-select",
        )

    async def callback(self, i: Interaction):
        label = self.values[0]
        field_data = next(
            (
                (n, field.value)
                for n, field in enumerate(i.message.embeds[0].fields)
                if field.name == label
            ),
            None,
        )
        value = field_index = None
        if field_data is not None:
            field_index, value = field_data
        id_ = i.message.embeds[0].footer.text.removeprefix("Submission ID: ")
        await i.response.send_modal(
            AmendModal(id_, label, value, i.message, field_index)
        )


class AmendView(View):
    def __init__(self):
        self.message: Message
        super().__init__(timeout=None)
        self.add_item(AmendSelect())


@bot.command()
@commands.is_owner()
async def sync(ctx):
    await bot.tree.sync()
    await bot.tree.sync(guild=Object(MAIN_GUILD))
    await ctx.send("Commands synced!")


@bot.tree.command(description="Register your guild and server")
async def register_guild(i: Interaction, guild_name: str, server_number: int):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to register a guild.",
            ephemeral=True,
        )
        return
    await i.response.defer()

    success = await add_guild(
        guild_name,
        server_number,
        i.user.id,
        i.user.name,
        datetime.now(),
    )

    if success:
        await i.followup.send(
            f"✅ Guild **{guild_name}** (Server {server_number}) registered successfully!"
        )
    else:
        await i.followup.send(
            f"Duplicate data for guild {guild_name} and server {server_number}"
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


@bot.tree.command(description="Remove members that left the server from the database")
async def purge_inactive_members(i: Interaction):
    await i.response.defer()
    if not is_staff(i):
        return await i.followup.send(
            "❌ You must have 'Manage Server' permission to purge inactive members.",
            ephemeral=True,
        )
    guild = bot.get_guild(MAIN_GUILD)
    if guild is None:
        return await i.followup.send(
            "❌ Could not find the main guild.",
            ephemeral=True,
        )
    active_user_ids = [member.id async for member in guild.fetch_members(limit=None)]
    await remove_inactive_members(active_user_ids)
    await i.followup.send("✅ Inactive members removed successfully.")


@bot.tree.command(description="Submit screenshots to register results")
@app_commands.describe(
    war="Screenshot of Guild War Log", league="Screenshot of Championsip League"
)
async def submit(i: Interaction, war: Attachment, league: Attachment):
    await i.response.defer()
    guild_id = await get_guild_from_member(i.user.id)
    if guild_id is None:
        return await i.followup.send(
            "You're not registered in any guild, use the `/register_guild` command first"
        )
    _, guild_name, server_number = await get_guild_by_id(guild_id)

    try:
        war_data = extract_war(await war.read())
        league_data = extract_league(await league.read())
        id_ = await add_submission(
            **war_data,
            **league_data,
            submitted_by=i.user.id,
        )
    except Exception as e:
        logging.error("FAILED EXTRACT OR ADD SUBMISSION", e)
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
    embed.set_footer(text=f"Submission ID: {id_}")
    embed.set_author(name=f"{guild_name} (S{server_number})")
    labels = {}
    for data in (
        war_data,
        league_data,
    ):
        for key, value in data.items():
            labels[key] = value
            embed.add_field(name=key, value=value if value is not None else "???")

    view = AmendView()
    view.message = await i.followup.send(embed=embed, view=view)


async def date_autocomplete(
    _: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await get_date(current)
    return [app_commands.Choice(name=str(row[0]), value=str(row[0])) for row in results]


async def season_autocomplete(
    _: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    months = []
    today = datetime.today()

    for i in range(20):
        dt = today - relativedelta(months=i)
        months.append(dt.strftime("%Y-%m"))

    return [
        app_commands.Choice(name=f"{month} season", value=month) for month in months
    ]


@bot.tree.command(description="View guilds leaderboard")
@app_commands.autocomplete(date=date_autocomplete)
@app_commands.describe(date="Date in YYYY-mm-dd format")
async def leaderboard(i: Interaction, date: str = None):
    await i.response.defer()
    if date is None:
        date = await get_latest_date()
        date = str(date)

    paginator = LeaderboardPaginator(
        leaderboard=await get_leaderboard(date),
        interaction=i,
        display_filters=date,
    )
    await paginator.send_message(i)


def get_display_date(season) -> str:
    if season is None:
        return "All time"
    return f"{season} season"


def get_formatted_results(results: dict) -> str:
    result_types = []
    for res, amount in results.items():
        emoji = RESULT_MAP[res]
        if amount != 1:
            if res == "Loss":
                res = "Losses"
            else:
                res += "s"
        result_types.append(f"`{amount}` {res} {emoji}")
    return " - ".join(result_types)


def get_records_summary(data, opponent=False):
    points = 0
    seasons = []

    results = {"Win": 0, "Loss": 0, "Draw": 0}
    last_5 = []
    for n, row in enumerate(data):
        _, _, scored, _, date, result = row
        points += scored
        season = f"`{str(date)[:-3]}`"
        if season not in seasons:
            seasons.append(season)
        if opponent:
            if result == "Win":
                result = "Loss"
            elif result == "Loss":
                result = "Win"
        results[result] += 1
        if n <= 5:
            last_5.append(RESULT_MAP[result])

    average = f"**Average**: `{points // len(data)}`"
    f_seasons = f"**Seasons covered**: {', '.join(seasons)}"
    f_last_5 = f"**Last 5**: {' '.join(last_5)}"

    return "\n".join([get_formatted_results(results), f_last_5, average, f_seasons])


async def opponent_guild_autocomplete(
    _: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    guild_data = await get_opponent_guilds_from_name(current)
    for guild_name, server_number in guild_data:
        guild_server = f"{guild_name} (S{server_number})"
        choices.append(
            app_commands.Choice(
                name=guild_server, value=f"{guild_name}///{server_number}"
            )
        )
    return choices


@bot.tree.command(description="Check opponent stats")
@app_commands.autocomplete(
    guild=opponent_guild_autocomplete, season=season_autocomplete
)
@app_commands.describe(
    guild="Select the guild",
    season="Choose the season",
)
async def check_opponent(i: Interaction, guild: str, season: str = None):
    await i.response.defer()
    try:
        guild_name, server_number = guild.split("///")
    except ValueError:
        return await i.followup.send(f"Couldn't find results for guild {guild}")

    display_date = get_display_date(season)
    data = await get_records_data([guild_name, server_number], season, True)
    summary = get_records_summary(data, True) if data else ""

    paginator = RecordsPaginator(
        data=data,
        guild_name=f"{guild_name} (S{server_number})",
        display_date=display_date,
        summary=summary,
        interaction=i,
        opponent=True,
    )
    await paginator.send_message(i)


@bot.tree.command(description="Check your guild stats")
@app_commands.autocomplete(season=season_autocomplete)
@app_commands.describe(season="Choose the season")
async def my_guild(i: Interaction, season: str = None):
    await i.response.defer()
    guild_id = await get_guild_from_member(i.user.id)
    if guild_id is None:
        return await i.followup.send(
            "You're not registered in any guild, use the `/register_guild` command first"
        )
    _, guild_name, server_number = await get_guild_by_id(guild_id)

    display_date = get_display_date(season)
    data = await get_records_data(guild_id, season)
    summary = get_records_summary(data) if data else ""

    paginator = RecordsPaginator(
        data=data,
        guild_name=f"{guild_name} (S{server_number})",
        display_date=display_date,
        summary=summary,
        interaction=i,
    )
    await paginator.send_message(i)


@bot.tree.command(description="Give kudos to a guild")
@app_commands.describe(
    guild="Select the guild", message="What would you like to give kudos for?"
)
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def give_kudos(i: Interaction, guild: str, message: str):
    await i.response.defer()
    guild_name, members = await give_kudo_and_get_guild_info(
        guild, i.user.display_name, message
    )
    if not guild_name:
        return await i.followup.send("❌ Guild not found", ephemeral=True)

    embed = Embed(
        color=Color.green(),
        title=f"{guild_name} received kudos",
        description=message,
        timestamp=datetime.now(),
    )
    embed.set_author(name=i.user.display_name, icon_url=i.user.display_avatar.url)
    channel = bot.get_channel(KUDOS_CHANNEL)
    await channel.send(", ".join(members), embed=embed)
    await i.followup.send("✅ Kudos given to this guild.", ephemeral=True)


@bot.tree.command(description="See kudos history for the chosen guild")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def guild_kudos(i: Interaction, guild: str):
    await i.response.defer()

    rows = await get_kudos_history(guild)
    if not rows:
        embed = Embed(
            color=Color.green(),
            title="Kudos History",
            description="This guild has no kudos yet!",
        )
        return await i.followup.send(embed=embed)

    description_lines = []
    for sender, message, created_at in rows:
        description_lines.append(
            f"**{sender}** — *{created_at:%Y-%m-%d %H:%M}*\n> {message}"
        )

    embed = Embed(
        color=Color.green(),
        title="Kudos History",
        description="\n\n".join(description_lines),
    )

    await i.followup.send(embed=embed)


@bot.tree.command(description="Check stats for the chosen guild")
@app_commands.autocomplete(guild=guild_name_autocomplete, season=season_autocomplete)
@app_commands.describe(guild="Select the guild", season="Choose the season")
async def check_guild(i: Interaction, guild: str, season: str = None):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to check a guild.",
            ephemeral=True,
        )
        return
    await i.response.defer()
    _, guild_name, server_number = await get_guild_by_id(guild)

    display_date = get_display_date(season)
    data = await get_records_data(guild, season)
    summary = get_records_summary(data) if data else ""

    paginator = RecordsPaginator(
        data=data,
        guild_name=f"{guild_name} (S{server_number})",
        display_date=display_date,
        summary=summary,
        interaction=i,
    )
    await paginator.send_message(i)


def get_since_from_period(period):
    today = date.today()

    ranges = {
        "Today": today,
        "Yesterday": today - timedelta(days=1),
        "Current season": today.replace(day=1),
    }

    if period.startswith("Last "):
        n_days = int(period.split()[1])
        since = today - timedelta(days=n_days)
    elif period in ranges:
        since = ranges[period]
    else:
        raise ValueError(f"Unsupported time slot: {period}")
    return since


@bot.tree.command(
    description="Check guilds that didn't submit screenshots in the chosen period of time"
)
async def missing_submissions(
    i: Interaction,
    period: Literal[
        "Today",
        "Yesterday",
        "Last 3 days",
        "Last 5 days",
        "Last 7 days",
        "Last 10 days",
        "Last 15 days",
        "Current season",
    ],
):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to check missing submissions.",
            ephemeral=True,
        )
        return
    await i.response.defer()

    since = get_since_from_period(period)

    data = await get_missing_submissions(since)
    paginator = MissingSubmissionPaginator(data, period, i)
    await paginator.send_message(i)


@bot.tree.command(description="Rename a guild")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def guild_rename(i: Interaction, guild: str, new_name: str):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to rename a guild.",
            ephemeral=True,
        )
        return
    await i.response.defer()
    success = await rename_guild(guild, new_name)

    if not success:
        return await i.followup.send("❌ Guild not found", ephemeral=True)

    await i.followup.send(f"✅ Guild successfully renamed to {new_name}.")


@bot.tree.command(description="Update a guild's server")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def guild_set_server(i: Interaction, guild: str, new_server: int):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to reset a guild's server.",
            ephemeral=True,
        )
        return
    await i.response.defer()
    success = await reset_guild_server(guild, new_server)

    if not success:
        return await i.followup.send("❌ Guild not found", ephemeral=True)

    await i.followup.send(f"✅ Guild server successfully updated to {new_server}.")


@bot.tree.command(description="Delete a guild from the bot")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def delete_guild(i: Interaction, guild: str):
    if not is_staff(i):
        await i.response.send_message(
            "❌ You must have 'Manage Server' permission to delete a guild.",
            ephemeral=True,
        )
        return
    await i.response.defer()

    view = ConfirmView()
    await i.followup.send("Are you sure you want to delete this guild?", view=view)
    await view.wait()

    if view.value is None:
        await i.followup.send("⏳ Timed out, no response.")
    elif view.value:
        success = await delete_guild_from_db(guild)
        if not success:
            return await i.followup.send("❌ Guild not found", ephemeral=True)
        await i.followup.send("✅ Guild deleted successfully.")
    else:
        await i.followup.send("Operation cancelled ❌")


@bot.tree.command(
    description="Remind guilds that haven't submitted screenshots in the last 15 days"
)
async def submission_reminder(i: Interaction):
    await i.response.defer()
    member_ids = await get_inactive_members()
    if not member_ids:
        return await i.followup.send("No inactive members found.")
    role = i.guild.get_role(REMINDER_ROLE)
    for member_id in member_ids:
        member = None
        with contextlib.suppress(NotFound):
            member = await i.guild.fetch_member(member_id)
        if member:
            await member.add_roles(role, reason="Submission reminder")
        await asyncio.sleep(1)
    await i.channel.edit(
        overwrites={role: PermissionOverwrite(view_channel=True)},
        reason="Submission reminder",
    )
    embed = Embed(
        title="Submission reminder",
        description="Hello 👋,\n\n"
        "You haven't submitted screenshots in the last 15 days\n\n"
        "Please submit screenshots soon, as your guild may receive a strike per our <#1325808876293193790>\n\n"
        "Thank you for being a part of our community!",
    )
    await i.followup.send(role.mention, embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("You don't have permission to use this command.")
    else:
        logging.error(f"Error in command {ctx.command}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)
        await ctx.send("An error occurred while processing the command.")


async def main():
    await connect_db()
    await bot.start(TOKEN)


asyncio.run(main())
