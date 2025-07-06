from discord import app_commands
from discord.ext import commands
import discord

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# Autocomplete function: returns filtered sample list of guilds
async def guild_name_autocomplete(interaction: discord.Interaction, current: str):
    sample_guilds = ["Semi-Croustillants", "Brave", "Dragon"]
    return [
        app_commands.Choice(name=guild, value=guild)
        for guild in sample_guilds if current.lower() in guild.lower()
    ][:25]

# Slash command using autocomplete
@bot.tree.command(name="register_member", description="Register yourself to a guild")
@app_commands.describe(guild_name="Select your guild")
@app_commands.autocomplete(guild_name=guild_name_autocomplete)
async def register_member(interaction: discord.Interaction, guild_name: str):
    await interaction.response.send_message(f"You selected {guild_name}!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    await bot.tree.sync()

bot.run(MTM5MTQ2MjU4NDE5NjE0MTExNg.GUlrj6.CUCEnyt3OahzGEejx6zH-fOoz_KJF3eUA4_YQU)
