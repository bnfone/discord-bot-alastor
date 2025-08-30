import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands and how to use the bot.")
    async def help_command(self, interaction: Interaction):
        embed = Embed(
            title="🎵 Alastor - The Radio Daemon",
            description="I can play radio stations in your Discord voice channels! Here are my commands:",
            color=discord.Color.purple()
        )
        
        # Radio Commands
        embed.add_field(
            name="📻 Radio Commands",
            value=(
                "`/radio play <station>` - Play a specific radio station\n"
                "`/radio list` - Browse all available stations\n"
                "`/radio info` - Show current playing station details\n"
                "`/radio stop` - Stop radio and leave voice channel"
            ),
            inline=False
        )
        
        # General Commands
        embed.add_field(
            name="ℹ️ General Commands", 
            value=(
                "`/info` - Show bot information and version\n"
                "`/donate` - Support the bot development\n"
                "`/help` - Show this help message"
            ),
            inline=False
        )
        
        # Station Management Commands
        embed.add_field(
            name="🎵 Station Management (Admin Only)",
            value=(
                "`/station add <name> <url>` - Add server radio station\n"
                "`/station remove <name>` - Remove server radio station"
            ),
            inline=False
        )
        
        # Usage Tips
        embed.add_field(
            name="💡 Quick Tips",
            value=(
                "• Join a voice channel before playing radio\n"
                "• Use autocomplete when typing station names\n"
                "• I can play on multiple servers simultaneously\n"
                "• Server admins can add stations with `/station add`\n"
                "• Use the control buttons for quick actions\n"
                "• Only secure streaming URLs are allowed for safety\n"
                "• Bot auto-leaves after 30s if voice channel is empty"
            ),
            inline=False
        )
        
        embed.set_footer(text="Alastor - The Radio Daemon • /help for commands")
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))