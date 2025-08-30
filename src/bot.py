import os
import sys
import asyncio
import logging
import discord
from discord.ext import commands

# Configure enhanced logging FIRST (before any imports that might use logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add the parent directory to sys.path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Look for .env in the project root (parent of src/)
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"✅ Loaded environment variables from {env_path}")
    else:
        # Try current directory as fallback
        load_dotenv()
        logger.info("✅ Loaded environment variables from .env")
except ImportError:
    logger.warning("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
except Exception as e:
    logger.info(f"ℹ️  No .env file found or error loading: {e}")

from src.config import load_config
from src.commands.radio import RadioCog
from src.commands.info import InfoCog
from src.commands.donate import DonateCog
from src.commands.help import HelpCog

# Load configuration (via ENV variable CONFIG_PATH, default: config.yaml)
config_path = os.getenv("CONFIG_PATH", "config.yaml")
config = load_config(config_path)

BOT_PREFIX = config["bot"]["prefix"]
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

logger.info("🎵 Starting Alastor - The Radio Daemon...")
logger.info(f"📁 Config loaded from: {config_path}")
logger.info(f"🔧 Bot prefix: {BOT_PREFIX}")

if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN is not set!")
    logger.error("💡 Create a .env file with: DISCORD_TOKEN=your_bot_token_here")
    exit(1)

logger.info("🔐 Discord token loaded successfully")

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
    logger.info("=" * 50)
    logger.info(f"🤖 Logged in as: {bot.user} (ID: {bot.user.id})")
    logger.info(f"🌐 Connected to {len(bot.guilds)} servers")
    
    # List servers
    for guild in bot.guilds:
        logger.info(f"   📊 {guild.name} ({guild.member_count} members)")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"⚡ Synced {len(synced)} slash commands successfully")
    except Exception as e:
        logger.error(f"❌ Error syncing slash commands: {e}")
    
    await bot.change_presence(activity=discord.Game(name="Radio"))
    logger.info("🎵 Bot is ready and online!")
    logger.info("=" * 50)

async def setup():
    logger.info("🔧 Loading bot extensions...")
    await bot.add_cog(RadioCog(bot))
    logger.info("   ✅ RadioCog loaded")
    await bot.add_cog(InfoCog(bot))
    logger.info("   ✅ InfoCog loaded")
    await bot.add_cog(DonateCog(bot))
    logger.info("   ✅ DonateCog loaded")
    await bot.add_cog(HelpCog(bot))
    logger.info("   ✅ HelpCog loaded")

async def main():
    async with bot:
        await setup()
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())