import os
import yaml
import discord
import asyncio
import requests  # <-- Neu für das Herunterladen & Auflösen von Playlist-URLs
from discord.ext import commands
from discord import app_commands, ui, SelectOption, Embed, Interaction

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Important for voice features

CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yaml")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# English description for the bot
BOT_DESCRIPTION = (
    "This bot can play various radio stations. "
    "It's inspired by Alastor from the 'Hazbin Hotel' series (Prime Video). "
    "Learn more: https://hazbinhotel.fandom.com/wiki/Alastor"
)

# -----------------------------------------------------------------
# 1) Load config
# -----------------------------------------------------------------
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Radios from config
RADIOS = config.get("radios", {})

# -----------------------------------------------------------------
# 2) Bot setup
# -----------------------------------------------------------------
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, description=BOT_DESCRIPTION)

# Dictionary to manage radios per guild
current_radios = {}

@bot.event
async def on_ready():
    print(f"Bot logged in as: {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")
    await bot.change_presence(activity=discord.Game(name="Radio"))

# -----------------------------------------------------------------
# 3) Utility function: Resolve playlist URLs (.m3u/.m3u8/.pls)
# -----------------------------------------------------------------
def resolve_stream_url(url: str) -> str:
    """
    If 'url' ends with .m3u, .m3u8 or .pls, we'll try to download it and 
    parse out the real stream link. Otherwise, return 'url' directly.

    This helps FFmpeg handle playlist files that just list actual streams.
    """
    lower_url = url.lower()
    if lower_url.endswith(".m3u") or lower_url.endswith(".m3u8") or lower_url.endswith(".pls"):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            # Look through each line:
            for line in response.text.splitlines():
                line = line.strip()
                # Ignore comments (#) or empty lines
                if line and not line.startswith("#"):
                    return line
        except Exception as e:
            print(f"Error resolving playlist URL {url}: {e}")
            return url
    return url

# -----------------------------------------------------------------
# 4) Helper function to play a radio station
# -----------------------------------------------------------------
async def play_radio(interaction: Interaction, station_name: str):
    """Plays a radio station on the guild of the invoking user."""
    # 1) Check if station exists
    if station_name not in RADIOS:
        embed = Embed(
            title="Error",
            description=f"Station **{station_name}** does not exist.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 2) Check if user is in a voice channel
    voice_channel = getattr(interaction.user.voice, "channel", None)
    if not voice_channel:
        embed = Embed(
            title="Error",
            description="You must be in a voice channel to play radio.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    guild_id = interaction.guild_id
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    # 3) If something is already playing, stop it
    if guild_id in current_radios:
        current_vc = current_radios[guild_id]["voice_client"]
        current_vc.stop()

    # 4) Connect or move to the correct channel
    if not voice_client or not voice_client.is_connected():
        try:
            await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
            # Refresh voice_client reference after connecting
            voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        except asyncio.TimeoutError:
            embed = Embed(
                title="Error",
                description="Could not connect to the voice channel (Timeout).",
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
        # If the bot is already on this server, but in a different channel, move it
        if voice_client.channel.id != voice_channel.id:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                embed = Embed(
                    title="Error",
                    description=f"Error moving to the voice channel: {e}",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Alastor - The Radio Daemon")
                await safe_send_message(interaction, embed=embed, ephemeral=True)
                return

    # 5) Resolve the actual stream URL (in case it's .m3u/.pls)
    original_url = RADIOS[station_name]["url"]
    radio_url = resolve_stream_url(original_url)

    ffmpeg_opts = {"options": "-vn"}
    source = discord.FFmpegPCMAudio(radio_url, **ffmpeg_opts)

    try:
        voice_client.play(source, after=lambda e: print(f"Player error: {e}") if e else None)
    except Exception as e:
        embed = Embed(
            title="Error",
            description=f"Error while playing: {e}",
            color=discord.Color.red()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await safe_send_message(interaction, embed=embed, ephemeral=True)
        return

    # 6) Store which station is playing
    current_radios[guild_id] = {
        "name": station_name,
        "voice_client": voice_client
    }

    # 7) Update bot status
    await bot.change_presence(activity=discord.Game(name=f"Radio: {station_name}"))

    # 8) Send success embed
    embed = Embed(
        title="Radio Started",
        description=f"**{station_name}** is now playing.",
        color=discord.Color.green()
    )
    embed.set_footer(text="Alastor - The Radio Daemon")
    await safe_send_message(interaction, embed=embed)

async def safe_send_message(interaction: Interaction, embed: Embed, ephemeral: bool = False):
    """Safe method to handle interactions that may already have a response."""
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    else:
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

# -----------------------------------------------------------------
# 5) RADIO COMMANDS
# -----------------------------------------------------------------
radio_group = app_commands.Group(name="radio", description="Manage radio stations.")

@radio_group.command(name="play", description="Play a radio station by name.")
@app_commands.describe(name="Station name")
async def radio_play(interaction: Interaction, name: str):
    """
    /radio play NAME
    Plays the specified radio station.
    """
    await play_radio(interaction, name)

@radio_group.command(name="stop", description="Stop the current radio and leave the voice channel.")
async def radio_stop(interaction: Interaction):
    """
    /radio stop
    Stops the current radio station on this server and disconnects from the voice channel.
    """
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
        print(f"Error disconnecting: {e}")

    del current_radios[guild_id]

    await bot.change_presence(activity=discord.Game(name="Radio"))
    embed = Embed(
        title="Radio Stopped",
        description="The radio has been stopped and the bot left the voice channel.",
        color=discord.Color.green()
    )
    embed.set_footer(text="Alastor - The Radio Daemon")
    await interaction.response.send_message(embed=embed)

@radio_group.command(name="info", description="Show the currently playing radio station.")
async def radio_info(interaction: Interaction):
    """
    /radio info
    Shows the station that is currently playing on this server.
    """
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
            description="No radio station is currently playing on this server.",
            color=discord.Color.yellow()
        )
    embed.set_footer(text="Alastor - The Radio Daemon")
    await interaction.response.send_message(embed=embed)

# -----------------------------------------------------------------
# /radio list
# -----------------------------------------------------------------
class RadioSelectMenu(ui.Select):
    def __init__(self):
        # Build a list of SelectOption objects
        options = []
        for station_name in RADIOS:
            options.append(
                SelectOption(
                    label=station_name,
                    description=f"Play {station_name}"
                )
            )

        super().__init__(
            placeholder="Pick a radio station...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: Interaction):
        station_name = self.values[0]
        await play_radio(interaction, station_name)

class RadioListView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RadioSelectMenu())

@radio_group.command(name="list", description="List all available radio stations in a dropdown menu.")
async def radio_list(interaction: Interaction):
    """
    /radio list
    Shows all available radio stations in a dropdown menu.
    """
    if not RADIOS:
        embed = Embed(
            title="No Available Stations",
            description="Please configure your radio stations first.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    view = RadioListView()
    embed = Embed(
        title="Available Radio Stations",
        description="Choose a station from the dropdown below:",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Alastor - The Radio Daemon")
    await interaction.response.send_message(embed=embed, view=view)

bot.tree.add_command(radio_group)

# -----------------------------------------------------------------
# 6) OTHER COMMANDS
# -----------------------------------------------------------------
@bot.tree.command(name="info", description="Show information about this bot.")
async def bot_info(interaction: Interaction):
    """
    /info
    Shows info about the bot.
    """
    embed = Embed(
        title="Alastor - The Radio Daemon",
        description=BOT_DESCRIPTION,
        color=discord.Color.purple()
    )
    embed.add_field(name="Version", value="1.1.1", inline=False)
    embed.add_field(name="Developer", value="[Blake](https://github.com/bnfone)", inline=False)
    embed.add_field(name="Source Code", value="[GitHub](https://github.com/bnfone/discord-bot-alastor)", inline=False)
    embed.set_footer(text="Alastor - The Radio Daemon")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="donate", description="Support the bot with a donation.")
async def donate(interaction: Interaction):
    """
    /donate
    Shows donation information.
    """
    embed = Embed(
        title="Donate",
        description="Support the bot - [donate now!](https://bnf.one/donate).",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Alastor - The Radio Daemon")
    await interaction.response.send_message(embed=embed)

# -----------------------------------------------------------------
# 7) BOT START
# -----------------------------------------------------------------
if not DISCORD_TOKEN:
    print("Error: DISCORD_TOKEN is not set.")
    exit(1)

bot.run(DISCORD_TOKEN)
