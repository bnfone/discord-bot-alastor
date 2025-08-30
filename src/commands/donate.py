import os
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, ui
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import load_config

# Load configuration
config = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
DONATIONS = config.get("donations", [])
GITHUB_URL = config.get("bot", {}).get("github_url", "https://github.com/bnfone/discord-bot-alastor")

class DonationView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        
        # Add donation buttons dynamically
        for donation in DONATIONS:
            button = ui.Button(
                label=donation['name'], 
                emoji=donation.get('emoji', '💝'),
                url=donation['url'],
                style=discord.ButtonStyle.link
            )
            self.add_item(button)
        
        # Add GitHub star button
        github_button = ui.Button(
            label="GitHub Star",
            emoji="⭐",
            url=GITHUB_URL,
            style=discord.ButtonStyle.link
        )
        self.add_item(github_button)

class DonateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="donate", description="Support the bot development with donations.")
    async def donate(self, interaction: Interaction):
        if not DONATIONS:
            embed = Embed(
                title="💝 Support the Bot",
                description=f"Thank you for wanting to support the development!\n\n[⭐ Give us a GitHub star]({GITHUB_URL})",
                color=discord.Color.gold()
            )
            view = None
        else:
            donation_list = "\n".join([f"**{donation['name']}**" for donation in DONATIONS])
            embed = Embed(
                title="💝 Support the Bot",
                description=f"Thank you for supporting Alastor development!\n\nChoose your preferred method:\n\n{donation_list}\n\n⭐ **Or give us a GitHub star!**",
                color=discord.Color.gold()
            )
            view = DonationView()
        
        embed.set_footer(text="Alastor - The Radio Daemon • Every contribution helps!")
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(DonateCog(bot))