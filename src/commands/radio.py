import os
import asyncio
import logging
import requests
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, ui, SelectOption
from src.config import load_config

# Load configuration (via CONFIG_PATH, default: config.yaml)
config = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
RADIOS = config.get("radios", {})

# Dictionary to manage currently playing radios per server
current_radios = {}

def resolve_stream_url(url: str) -> str:
    """
    If the URL ends with .m3u, .m3u8, or .pls,
    try to retrieve and parse the real stream URL.
    Returns the parsed URL or None if retrieval fails.
    """
    lower_url = url.lower()
    if lower_url.endswith((".m3u", ".m3u8", ".pls")):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            for line in response.text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
        except Exception as e:
            logging.error(f"Error resolving playlist URL {url}: {e}")
            return None
    return url

async def safe_send_message(interaction: Interaction, embed: Embed, ephemeral: bool = False):
    """Sends a response, even if one was already sent."""
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    else:
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

class RadioSelectMenu(ui.Select):
    def __init__(self):
        options = [
            SelectOption(label=station, description=f"Play {station}")
            for station in RADIOS
        ]
        super().__init__(placeholder="Choose a radio station...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        station = self.values[0]
        # Call the static method defined in the cog
        await RadioCog.play_radio_static(interaction, station)

class RadioListView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RadioSelectMenu())

class RadioCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Define an app_commands.Group; all methods decorated with @radio.command will be registered as /radio <subcommand>
    radio = app_commands.Group(name="radio", description="Manage radio stations")

    @staticmethod
    async def play_radio_static(interaction: Interaction, station_name: str):
        if station_name not in RADIOS:
            embed = Embed(
                title="Error",
                description=f"Station **{station_name}** does not exist.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return

        voice_channel = getattr(interaction.user.voice, "channel", None)
        if not voice_channel:
            embed = Embed(
                title="Error",
                description="You must be in a voice channel to play radio.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return

        guild_id = interaction.guild_id
        voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)

        # Stop any currently playing stream
        if guild_id in current_radios:
            current_vc = current_radios[guild_id]["voice_client"]
            current_vc.stop()

        # Connect or move to the correct voice channel
        if not voice_client or not voice_client.is_connected():
            try:
                await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
                voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)
            except asyncio.TimeoutError:
                embed = Embed(
                    title="Error",
                    description="Failed to connect to the voice channel (timeout).",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Alastor - The Radio Daemon")
                await safe_send_message(interaction, embed=embed, ephemeral=True)
                return
            except Exception as e:
                embed = Embed(
                    title="Error",
                    description=f"Error joining voice channel: {e}",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Alastor - The Radio Daemon")
                await safe_send_message(interaction, embed=embed, ephemeral=True)
                return
        else:
            if voice_client.channel.id != voice_channel.id:
                try:
                    await voice_client.move_to(voice_channel)
                except Exception as e:
                    embed = Embed(
                        title="Error",
                        description=f"Error moving to voice channel: {e}",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Alastor - The Radio Daemon")
                    await safe_send_message(interaction, embed=embed, ephemeral=True)
                    return

        original_url = RADIOS[station_name]["url"]
        resolved_url = resolve_stream_url(original_url)
        if resolved_url is None:
            # URL resolution failed – inform the user
            embed = Embed(
                title="Error",
                description=f"Failed to retrieve stream URL for **{station_name}**. The URL may be unreachable.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return

        ffmpeg_opts = {"options": "-vn"}
        source = discord.FFmpegPCMAudio(resolved_url, **ffmpeg_opts)
        try:
            voice_client.play(source, after=lambda e: logging.error(f"Player error: {e}") if e else None)
        except Exception as e:
            embed = Embed(
                title="Error",
                description=f"Error playing stream: {e}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return

        current_radios[guild_id] = {"name": station_name, "voice_client": voice_client}
        await interaction.client.change_presence(activity=discord.Game(name=f"Radio: {station_name}"))
        embed = Embed(
            title="Radio Started",
            description=f"**{station_name}** is now playing.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await safe_send_message(interaction, embed=embed)

    @radio.command(name="play", description="Play a radio station by name.")
    @app_commands.describe(name="Station name")
    async def play(self, interaction: Interaction, name: str):
        await self.play_radio_static(interaction, name)

    @radio.command(name="stop", description="Stop the currently playing radio and leave the voice channel.")
    async def stop(self, interaction: Interaction):
        guild_id = interaction.guild_id
        if guild_id not in current_radios:
            embed = Embed(
                title="Info",
                description="No radio is currently playing on this server.",
                color=discord.Color.yellow()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await interaction.response.send_message(embed=embed)
            return

        voice_client = current_radios[guild_id]["voice_client"]
        voice_client.stop()
        try:
            await voice_client.disconnect(force=True)
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")

        del current_radios[guild_id]
        await interaction.client.change_presence(activity=discord.Game(name="Radio"))
        embed = Embed(
            title="Radio Stopped",
            description="The radio has been stopped and the bot has left the voice channel.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed)

    @radio.command(name="info", description="Show the currently playing radio station.")
    async def info(self, interaction: Interaction):
        guild_id = interaction.guild_id
        if guild_id in current_radios:
            station_name = current_radios[guild_id]["name"]
            embed = Embed(
                title="Current Radio Station",
                description=f"**{station_name}** is currently playing.",
                color=discord.Color.blue()
            )
        else:
            embed = Embed(
                title="Info",
                description="No radio is currently playing on this server.",
                color=discord.Color.yellow()
            )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed)

    @radio.command(name="list", description="List all available radio stations in a dropdown menu.")
    async def list(self, interaction: Interaction):
        if not RADIOS:
            embed = Embed(
                title="No Stations Available",
                description="Please configure your radio stations first.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view = RadioListView()
        embed = Embed(
            title="Available Radio Stations",
            description="Choose a station from the dropdown menu:",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(RadioCog(bot))