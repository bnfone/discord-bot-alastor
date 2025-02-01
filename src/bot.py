import os
import asyncio
import logging
import discord
from discord.ext import commands
from src.config import load_config
from src.commands.radio import RadioCog
from src.commands.info import InfoCog
from src.commands.donate import DonateCog

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load configuration (via ENV variable CONFIG_PATH, default: config.yaml)
config_path = os.getenv("CONFIG_PATH", "config.yaml")
config = load_config(config_path)

BOT_PREFIX = config["bot"]["prefix"]
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    logging.error("DISCORD_TOKEN is not set!")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    description=config["bot"]["description"]
)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logging.info(f"{len(synced)} slash commands synced.")
    except Exception as e:
        logging.error(f"Error syncing slash commands: {e}")
    await bot.change_presence(activity=discord.Game(name="Radio"))

async def setup():
    await bot.add_cog(RadioCog(bot))
    await bot.add_cog(InfoCog(bot))
    await bot.add_cog(DonateCog(bot))

async def main():
    async with bot:
        await setup()
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())