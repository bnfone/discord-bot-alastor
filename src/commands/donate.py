import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed

class DonateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="donate", description="Support the bot with a donation.")
    async def donate(self, interaction: Interaction):
        embed = Embed(
            title="Donate",
            description="Support the bot – [donate now!](https://bnf.one/devdonations).",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(DonateCog(bot))