import os
import aiosqlite
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from database import init_db, add_guild, DB_NAME


class GuildIDTransformer(app_commands.Transformer):
    async def transform(self, i: discord.Interaction, value: str) -> int:
        return int(value)


load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    print(f"✅ {bot.user} has connected to Discord!")
    print("🗂️ Initializing database...")
    await init_db()
    print("✅ Database initialized.")


@bot.command(name="sync")
@commands.is_owner()
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
async def register_guild(interaction: discord.Interaction, guild_name: str, server_number: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ You must have 'Manage Server' permission to register a guild.",
            ephemeral=True
        )
        return

    await add_guild(guild_name, server_number, interaction.user.id, interaction.user.display_name, datetime.now().strftime(format="%d/%m/%Y, %H:%M:%S"))

    await interaction.response.send_message(
        f"✅ Guild **{guild_name}** (Server {server_number}) registered successfully!"
    )


async def guild_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = []
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, guild_name, server_number FROM guilds WHERE guild_name LIKE ? LIMIT 25",
            (f"%{current}%",)
        )
        rows = await cursor.fetchall()
        for guild_id, guild_name, server_number in rows:
            print(guild_id, type(guild_id))
            choices.append(app_commands.Choice(name=f"{guild_name} (S{server_number})", value=int(guild_id)))
    return choices


@bot.tree.command(description="Register a member to a guild")
@app_commands.describe(guild="Select the guild")
@app_commands.autocomplete(guild=guild_name_autocomplete)
async def register_member(interaction: discord.Interaction, guild: int, member: discord.Member):
    print(guild, type(guild))
    await interaction.response.defer()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, guild_name, server_number FROM guilds WHERE id = ?",
            (guild)
        )
        row = await cursor.fetchone()

    if not row:
        guild_id, guild_name, server_number = row
        return await interaction.response.send_message(
            f"❌ Guild **{guild_name}** (Server {server_number}) not found. Please register your guild first.",
            ephemeral=True
        )

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO members (member_id, username, guild_id) VALUES (?, ?, ?)",
            (member.id, member.display_name, guild_id)
        )
        await db.commit()

    await interaction.followup.send(
        f"✅ {member.mention}, you have been registered to guild **{guild_name}** (Server {server_number}).",
    )


bot.run(TOKEN)
