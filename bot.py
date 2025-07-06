import discord
import os
import aiosqlite
from dotenv import load_dotenv
from discord.ext import commands
from database import init_db

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up intents
intents = discord.Intents.default()
intents.message_content = True

# Create the bot client
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} has connected to Discord!")
    print("🗂️ Initializing database...")
    await init_db()
    print("✅ Database initialized.")
    try:
        print("🔄 Attempting to sync slash commands globally...")
        synced = await bot.tree.sync()  # No guild specified here => global commands
        print(f"✅ Synced {len(synced)} commands globally:")
        for cmd in synced:
            print(f" - {cmd.name}")
    except Exception as e:
        print(f"⚠️ Error syncing commands: {e}")

# Prefix command
@bot.command(name="hello")
async def hello(ctx):
    await ctx.send("👋 Hello! This is a prefix command.")

# Slash command: hello
@bot.tree.command(name="hello", description="Say hello to the bot")
async def slash_hello(interaction: discord.Interaction):
    await interaction.response.send_message("👋 Hello! This is a slash command.")

# Slash command: register_guild
@bot.tree.command(name="register_guild", description="Register your guild and server")
async def register_guild(interaction: discord.Interaction, guild_name: str, server_number: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ You must have 'Manage Server' permission to register a guild.",
            ephemeral=True
        )
        return

    async with aiosqlite.connect("hpn_bot.db") as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO guilds (guild_id, guild_name, server_number, registered_by)
            VALUES (?, ?, ?, ?)
            """,
            (interaction.guild.id, guild_name, server_number, str(interaction.user))
        )
        await db.commit()

    await interaction.response.send_message(
        f"✅ Guild **{guild_name}** (Server {server_number}) registered successfully!"
    )

# Slash command: register_member
@bot.tree.command(name="register_member", description="Register yourself to a guild")
async def register_member(interaction: discord.Interaction, guild_name: str, server_number: str):
    # Verify guild exists
    async with aiosqlite.connect("hpn_bot.db") as db:
        cursor = await db.execute(
            "SELECT guild_id FROM guilds WHERE guild_name = ? AND server_number = ?",
            (guild_name, server_number)
        )
        row = await cursor.fetchone()

    if not row:
        await interaction.response.send_message(
            f"❌ Guild **{guild_name}** (Server {server_number}) not found. Please register your guild first.",
            ephemeral=True
        )
        return

    guild_id = row[0]

    # Register member
    async with aiosqlite.connect("hpn_bot.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO members (member_id, username, guild_id) VALUES (?, ?, ?)",
            (str(interaction.user.id), str(interaction.user), guild_id)
        )
        await db.commit()

    await interaction.response.send_message(
        f"✅ {interaction.user.display_name}, you have been registered to guild **{guild_name}** (Server {server_number}).",
        ephemeral=True
    )

# Run the bot (last line)
bot.run(TOKEN)
