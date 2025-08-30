import os
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import load_config

# Load configuration
config = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
BOT_DESCRIPTION = config.get("bot", {}).get("description", "A powerful and fun Discord radio bot inspired by Alastor.")

class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Show information about the bot.")
    async def show_info(self, interaction: Interaction):
        embed = Embed(
            title="Alastor - The Radio Daemon",
            description=BOT_DESCRIPTION,
            color=discord.Color.purple()
        )
        version = config.get("bot", {}).get("version", "Unknown")
        github_url = config.get("bot", {}).get("github_url", "https://github.com/bnfone/discord-bot-alastor")
        embed.add_field(name="Version", value=version, inline=False)
        embed.add_field(name="Developer", value="[Blake](https://github.com/bnfone)", inline=False)
        embed.add_field(name="Source Code", value=f"[GitHub]({github_url})", inline=False)
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))