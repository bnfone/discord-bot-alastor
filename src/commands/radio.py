import os
import asyncio
import logging
import aiohttp
import json
import time
from typing import Dict, Optional, List
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, ui, SelectOption
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import load_config

# Load configuration (via CONFIG_PATH, default: config.yaml)
config = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
RADIOS = config.get("radios", {})

# Enhanced state management
current_radios: Dict[int, Dict] = {}  # guild_id -> {name, voice_client, url, start_time}
stream_cache: Dict[str, Dict] = {}  # url -> {resolved_url, timestamp}
server_stations: Dict[int, Dict[str, Dict]] = {}  # guild_id -> {station_name -> {url, description, added_by}}
STATE_FILE = "bot_state.json"
CACHE_DURATION = 3600  # 1 hour cache

# Persistent state management
def save_state():
    """Save current state to file"""
    try:
        state = {
            "current_radios": {
                str(guild_id): {
                    "name": data["name"],
                    "url": data.get("url", ""),
                    "start_time": data.get("start_time", time.time())
                }
                for guild_id, data in current_radios.items()
            },
            "radios": RADIOS,
            "server_stations": {
                str(guild_id): stations
                for guild_id, stations in server_stations.items()
            }
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save state: {e}")

def load_state():
    """Load state from file"""
    global RADIOS, server_stations
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        RADIOS.update(state.get("radios", {}))
        # Load server-specific stations
        loaded_server_stations = state.get("server_stations", {})
        for guild_id_str, stations in loaded_server_stations.items():
            server_stations[int(guild_id_str)] = stations
        logging.info(f"Loaded state: {len(RADIOS)} global stations, {sum(len(s) for s in server_stations.values())} server stations")
    except FileNotFoundError:
        logging.info("No state file found, starting fresh")
    except Exception as e:
        logging.error(f"Failed to load state: {e}")

# Configure logging
logger = logging.getLogger(__name__)

# Load state on import
load_state()
logger.info(f"🎵 Radio module initialized with {len(RADIOS)} stations")

async def resolve_stream_url(url: str) -> Optional[str]:
    """
    Asynchronously resolve playlist URLs with caching.
    Returns the resolved URL or None if retrieval fails.
    """
    # Check cache first
    if url in stream_cache:
        cache_entry = stream_cache[url]
        if time.time() - cache_entry["timestamp"] < CACHE_DURATION:
            return cache_entry["resolved_url"]
        else:
            del stream_cache[url]  # Remove expired cache
    
    lower_url = url.lower()
    if lower_url.endswith((".m3u", ".m3u8", ".pls")):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    text = await response.text()
                    
                    # Handle .pls format
                    if lower_url.endswith(".pls"):
                        for line in text.splitlines():
                            line = line.strip()
                            if line.startswith("File") and "=" in line:
                                stream_url = line.split("=", 1)[1]
                                if stream_url.startswith(("http", "https")):
                                    # Cache the result
                                    stream_cache[url] = {
                                        "resolved_url": stream_url,
                                        "timestamp": time.time()
                                    }
                                    return stream_url
                    else:
                        # Handle .m3u/.m3u8 format
                        for line in text.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and line.startswith(("http", "https")):
                                # Cache the result
                                stream_cache[url] = {
                                    "resolved_url": line,
                                    "timestamp": time.time()
                                }
                                return line
        except Exception as e:
            logging.error(f"Error resolving playlist URL {url}: {e}")
            return None
    return url

async def safe_send_message(interaction: Interaction, embed: Embed = None, content: str = None, ephemeral: bool = False, view: ui.View = None):
    """Sends a response, even if one was already sent."""
    kwargs = {"ephemeral": ephemeral}
    if embed:
        kwargs["embed"] = embed
    if content:
        kwargs["content"] = content
    if view:
        kwargs["view"] = view
        
    if not interaction.response.is_done():
        await interaction.response.send_message(**kwargs)
    else:
        await interaction.followup.send(**kwargs)

def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate if URL is safe for streaming"""
    import re
    
    # Must be HTTP/HTTPS
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    
    # Block suspicious patterns
    suspicious_patterns = [
        r'localhost', r'127\.0\.0\.1', r'0\.0\.0\.0', r'\[::1\]',  # Localhost
        r'192\.168\.', r'10\.', r'172\.(1[6-9]|2[0-9]|3[01])\.', # Private IPs
        r'file://', r'ftp://', r'sftp://', # Non-HTTP protocols
        r'\.(exe|bat|cmd|scr|pif|com)($|\?)', # Executable files
        r'javascript:', r'data:', r'vbscript:', # Script protocols
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, url.lower()):
            return False, "URL appears to be unsafe or blocked"
    
    # Check for valid streaming extensions/formats
    streaming_patterns = [
        r'\.(mp3|aac|ogg|wav|flac|m4a)($|\?)',  # Audio files
        r'\.(m3u|m3u8|pls)($|\?)',  # Playlists
        r'(icecast|shoutcast|stream)',  # Streaming servers
        r'/(live|radio|stream)/',  # Common streaming paths
    ]
    
    # If it doesn't match streaming patterns, be more cautious
    if not any(re.search(pattern, url.lower()) for pattern in streaming_patterns):
        # Allow well-known radio domains
        trusted_domains = [
            'bbc.co.uk', 'ndr.de', 'wdr.de', 'swr.de', 'br.de',
            'ard.de', 'deutschlandfunk.de', 'ffn.de', 
            'absolutradio.de', 'ilovemusic.de', 'pride1.de',
            'radio.de', 'tune.in', 'stream.live', 'icecast'
        ]
        
        if not any(domain in url.lower() for domain in trusted_domains):
            return False, "URL doesn't appear to be from a recognized streaming service"
    
    return True, "URL appears safe"

def get_available_stations(guild_id: int) -> Dict[str, Dict]:
    """Get all available stations for a guild (global + server-specific)"""
    available = RADIOS.copy()
    if guild_id in server_stations:
        available.update(server_stations[guild_id])
    return available

async def get_station_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Get autocomplete choices for station names"""
    guild_stations = get_available_stations(interaction.guild_id)
    
    if not current:
        # Return first 25 stations if no input
        return [app_commands.Choice(name=name, value=name) for name in list(guild_stations.keys())[:25]]
    
    # Fuzzy search for matching stations
    matches = []
    current_lower = current.lower()
    
    for station_name in guild_stations.keys():
        if current_lower in station_name.lower():
            matches.append(app_commands.Choice(name=station_name, value=station_name))
        if len(matches) >= 25:  # Discord limit
            break
            
    return matches

class RadioSelectMenu(ui.Select):
    def __init__(self, guild_id: int, page: int = 0):
        self.page = page
        self.guild_id = guild_id
        available_stations = get_available_stations(guild_id)
        stations = list(available_stations.keys())
        start_idx = page * 25
        end_idx = start_idx + 25
        page_stations = stations[start_idx:end_idx]
        
        options = []
        for station in page_stations:
            # Show if it's a server-specific station
            desc_suffix = " (Server)" if guild_id in server_stations and station in server_stations[guild_id] else " (Global)"
            description = f"Play {station}{desc_suffix}"[:100]
            options.append(SelectOption(label=station[:100], description=description, value=station))
        
        if not options:
            options = [SelectOption(label="No stations available", description="Add stations with /station add", value="none")]
            
        super().__init__(placeholder="Choose a radio station...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if self.values[0] == "none":
            await safe_send_message(interaction, content="No stations available. Use `/admin add` to add stations.", ephemeral=True)
            return
        station = self.values[0]
        await RadioCog.play_radio_static(interaction, station)

class StationControlView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        
    @ui.button(label="⏹️ Stop", style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: Interaction, button: ui.Button):
        await RadioCog.stop_radio_static(interaction)
        
    @ui.button(label="ℹ️ Info", style=discord.ButtonStyle.secondary)
    async def info_button(self, interaction: Interaction, button: ui.Button):
        await RadioCog.show_info_static(interaction)
        
class RadioListView(ui.View):
    def __init__(self, guild_id: int, page: int = 0):
        super().__init__(timeout=120)
        self.page = page
        self.guild_id = guild_id
        self.add_item(RadioSelectMenu(guild_id, page))
        
        available_stations = get_available_stations(guild_id)
        total_stations = len(available_stations)
        total_pages = (total_stations + 24) // 25  # Ceiling division
        
        if total_pages > 1:
            if page > 0:
                self.add_item(PreviousPageButton(guild_id, page))
            if page < total_pages - 1:
                self.add_item(NextPageButton(guild_id, page))
                
class PreviousPageButton(ui.Button):
    def __init__(self, guild_id: int, current_page: int):
        super().__init__(label="◀️ Previous", style=discord.ButtonStyle.secondary)
        self.current_page = current_page
        self.guild_id = guild_id
        
    async def callback(self, interaction: Interaction):
        new_view = RadioListView(self.guild_id, self.current_page - 1)
        available_stations = get_available_stations(self.guild_id)
        global_count = len(RADIOS)
        server_count = len(server_stations.get(self.guild_id, {}))
        embed = Embed(
            title="📻 Available Radio Stations",
            description=f"Choose from **{len(available_stations)}** stations ({global_count} global, {server_count} server):\n\nPage {self.current_page}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.edit_message(embed=embed, view=new_view)
        
class NextPageButton(ui.Button):
    def __init__(self, guild_id: int, current_page: int):
        super().__init__(label="Next ▶️", style=discord.ButtonStyle.secondary)
        self.current_page = current_page
        self.guild_id = guild_id
        
    async def callback(self, interaction: Interaction):
        new_view = RadioListView(self.guild_id, self.current_page + 1)
        available_stations = get_available_stations(self.guild_id)
        global_count = len(RADIOS)
        server_count = len(server_stations.get(self.guild_id, {}))
        embed = Embed(
            title="📻 Available Radio Stations",
            description=f"Choose from **{len(available_stations)}** stations ({global_count} global, {server_count} server):\n\nPage {self.current_page + 2}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.response.edit_message(embed=embed, view=new_view)

class RadioCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Define an app_commands.Group; all methods decorated with @radio.command will be registered as /radio <subcommand>
    radio = app_commands.Group(name="radio", description="Manage radio stations")

    @staticmethod
    async def play_radio_static(interaction: Interaction, station_name: str, show_loading: bool = True):
        """Enhanced radio playback with better feedback and multi-server support"""
        # Get guild_id first
        guild_id = interaction.guild_id
        
        # Log the play request
        guild_name = interaction.guild.name if interaction.guild else "Unknown"
        user_name = f"{interaction.user.display_name} ({interaction.user.name})"
        logger.info(f"🎵 Play request: '{station_name}' by {user_name} in '{guild_name}'")
        
        # Show loading indicator
        if show_loading:
            loading_embed = Embed(
                title="🔄 Loading...",
                description=f"Connecting to **{station_name}**...",
                color=discord.Color.orange()
            )
            loading_embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=loading_embed, ephemeral=False)
        available_stations = get_available_stations(guild_id)
        if station_name not in available_stations:
            embed = Embed(
                title="❌ Station Not Found",
                description=f"Station **{station_name}** does not exist.\n\nUse `/radio list` to see available stations or `/station add` to add new ones.",
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

        # Always clean up any existing voice clients first
        logger.info(f"🔊 Connecting to voice channel: {voice_channel.name}")
        logger.info(f"🌍 Server: {interaction.guild.name} (ID: {interaction.guild_id})")
        logger.info(f"🔊 Channel: {voice_channel.name} (ID: {voice_channel.id})")
        logger.info(f"🌐 Voice region: {getattr(interaction.guild, 'region', 'Unknown')}")
        logger.info(f"👤 Bot permissions: {voice_channel.permissions_for(interaction.guild.me)}")
        
        try:
            # Force cleanup of any existing voice connections for this guild
            existing_vcs = [vc for vc in interaction.client.voice_clients if vc.guild.id == interaction.guild_id]
            for vc in existing_vcs:
                try:
                    if vc.is_connected():
                        vc.stop()
                        await vc.disconnect(force=True)
                        logger.info("🔄 Cleaned up existing voice connection")
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ Error during cleanup: {cleanup_error}")
            
            # Wait for cleanup to complete
            await asyncio.sleep(1.5)
            
            # Connect with retry logic
            voice_client = None
            for attempt in range(3):
                try:
                    logger.info(f"🔄 Connection attempt {attempt + 1}/3")
                    voice_client = await asyncio.wait_for(voice_channel.connect(reconnect=False, timeout=60.0), timeout=20.0)
                    logger.info(f"✅ Successfully connected to {voice_channel.name} (attempt {attempt + 1})")
                    break
                except discord.errors.ConnectionClosed as e:
                    logger.warning(f"🔄 Connection closed (attempt {attempt + 1}): {e}")
                    # Log the voice endpoint for debugging
                    logger.warning(f"🌐 Failed endpoint: {getattr(e, 'endpoint', 'Unknown')}")
                    if attempt < 2:  # Not the last attempt
                        await asyncio.sleep(5)  # Wait even longer before retry
                        continue
                    else:
                        raise
                except discord.errors.ClientException as e:
                    if "Already connected" in str(e):
                        logger.warning(f"🔄 Bot thinks it's connected, forcing cleanup (attempt {attempt + 1})")
                        # Force more aggressive cleanup
                        for vc in interaction.client.voice_clients:
                            if vc.guild.id == interaction.guild_id:
                                try:
                                    await vc.disconnect(force=True)
                                except:
                                    pass
                        await asyncio.sleep(2)
                        if attempt < 2:
                            continue
                        else:
                            raise
                    else:
                        raise
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Connection timeout (attempt {attempt + 1})")
                    if attempt < 2:  # Not the last attempt
                        await asyncio.sleep(3)  # Wait before retry
                        continue
                    else:
                        raise
            
            if not voice_client:
                raise Exception("Failed to establish voice connection after 3 attempts")
                        
        except asyncio.TimeoutError:
            logger.error(f"⏰ Connection timeout to {voice_channel.name}")
            embed = Embed(
                title="❌ Connection Timeout",
                description="Failed to connect to the voice channel. This might be due to:\n• Discord server issues\n• Network connectivity problems\n• Bot token permissions\n\nPlease try again in a moment.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        except discord.errors.ConnectionClosed as e:
            logger.error(f"❌ Voice connection closed: {e}")
            embed = Embed(
                title="❌ Connection Failed",
                description="Discord voice connection was closed. This usually indicates:\n• Bot permissions issue\n• Invalid bot token\n• Discord API problems\n\nCheck bot permissions and try again.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        except discord.errors.ClientException as e:
            if "Already connected" in str(e):
                logger.error(f"❌ Persistent connection conflict: {e}")
                embed = Embed(
                    title="❌ Connection Conflict",
                    description="The bot is stuck in a connection state. This usually resolves itself in a few moments.\n\nPlease wait 30 seconds and try again, or restart the bot.",
                    color=discord.Color.red()
                )
            else:
                logger.error(f"❌ Voice client error: {e}")
                embed = Embed(
                    title="❌ Voice Client Error",
                    description=f"Discord client error: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}",
                    color=discord.Color.red()
                )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        except Exception as e:
            logger.error(f"❌ Voice connection error: {e}")
            embed = Embed(
                title="❌ Connection Error",
                description=f"Error joining voice channel: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        
        # If we reach here, we have a successful connection
        # Check if we need to move to a different channel
        if voice_client and voice_client.is_connected() and voice_client.channel.id != voice_channel.id:
            logger.info(f"🔄 Moving from {voice_client.channel.name} to {voice_channel.name}")
            try:
                await voice_client.move_to(voice_channel)
                logger.info(f"✅ Successfully moved to {voice_channel.name}")
            except Exception as e:
                logger.error(f"❌ Voice move error: {e}")
                embed = Embed(
                    title="❌ Move Error",
                    description=f"Error moving to voice channel: {e}",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Alastor - The Radio Daemon")
                await safe_send_message(interaction, embed=embed, ephemeral=True)
                return

        original_url = available_stations[station_name]["url"]
        logger.info(f"🔗 Resolving stream URL for '{station_name}': {original_url[:60]}...")
        resolved_url = await resolve_stream_url(original_url)
        if resolved_url is None:
            logger.error(f"❌ Failed to resolve stream URL for '{station_name}'")
            embed = Embed(
                title="❌ Stream Error",
                description=f"Failed to retrieve stream URL for **{station_name}**.\n\nThe station may be offline or the URL is invalid.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            if show_loading:
                await interaction.edit_original_response(embed=embed)
            else:
                await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        
        logger.info(f"✅ Stream URL resolved successfully for '{station_name}'")

        # Start playing the stream with improved FFmpeg options
        logger.info(f"🎵 Starting playback of '{station_name}'")
        logger.info(f"🔗 Final stream URL: {resolved_url}")
        
        # Test the URL first with a simple HTTP request
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.head(resolved_url) as response:
                    logger.info(f"📡 Stream test response: {response.status} - {response.headers.get('content-type', 'unknown')}")
                    if response.status >= 400:
                        raise Exception(f"Stream returned HTTP {response.status}")
        except Exception as e:
            logger.error(f"❌ Stream connectivity test failed for '{station_name}': {e}")
            embed = Embed(
                title="❌ Stream Unavailable",
                description=f"**{station_name}** is currently offline or unreachable.\n\nError: {str(e)}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            if show_loading:
                await interaction.edit_original_response(embed=embed)
            else:
                await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        
        # Try different FFmpeg configurations and sources
        ffmpeg_path = "/opt/homebrew/bin/ffmpeg"  # Explicit path for macOS Homebrew
        
        # Try different approaches
        approaches = [
            {
                "name": "FFmpegOpusAudio (recommended for Discord)",
                "source_type": "opus",
                "before_options": "-reconnect 1 -reconnect_streamed 1 -user_agent 'Mozilla/5.0'",
                "options": "-vn"
            },
            {
                "name": "FFmpegPCMAudio with explicit path",
                "source_type": "pcm",
                "executable": ffmpeg_path,
                "before_options": "-reconnect 1 -user_agent 'Mozilla/5.0'", 
                "options": "-vn -f s16le -ar 48000 -ac 2"
            },
            {
                "name": "FFmpegPCMAudio basic",
                "source_type": "pcm",
                "options": "-vn"
            }
        ]
        
        for config in approaches:
            try:
                logger.info(f"🔧 Trying {config['name']} for '{station_name}'")
                
                # Prepare kwargs
                kwargs = {k: v for k, v in config.items() if k not in ['name', 'source_type']}
                
                # Create appropriate source
                if config['source_type'] == 'opus':
                    source = discord.FFmpegOpusAudio(resolved_url, **kwargs)
                else:
                    source = discord.FFmpegPCMAudio(resolved_url, **kwargs)
                
                # Start playing
                voice_client.play(source, after=lambda e: logger.error(f"❌ Player error for '{station_name}': {e}") if e else logger.info(f"⏹️ Playback ended for '{station_name}'"))
                logger.info(f"✅ Successfully started playing '{station_name}' with {config['name']}")
                break
                
            except Exception as e:
                logger.error(f"❌ {config['name']} failed for '{station_name}': {str(e) or 'Unknown error'}")
                
                # If this was the last attempt, show error
                if config == approaches[-1]:
                    embed = Embed(
                        title="❌ Playback Error",
                        description=f"Could not play **{station_name}**.\n\nThis might be due to:\n• FFmpeg compatibility issues on macOS\n• Stream format not supported\n• Network connectivity problems\n\nError: {str(e)[:150]}{'...' if len(str(e)) > 150 else ''}",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Alastor - The Radio Daemon")
                    if show_loading:
                        await interaction.edit_original_response(embed=embed)
                    else:
                        await safe_send_message(interaction, embed=embed, ephemeral=True)
                    return

        # Enhanced state tracking
        current_radios[guild_id] = {
            "name": station_name, 
            "voice_client": voice_client,
            "url": resolved_url,
            "start_time": time.time()
        }
        save_state()  # Persist state
        
        # Multi-server status (show total servers instead of specific station)
        active_servers = len(current_radios)
        await interaction.client.change_presence(
            activity=discord.Game(name=f"Radio on {active_servers} server{'s' if active_servers != 1 else ''}")
        )
        
        logger.info(f"🎵 Now playing '{station_name}' in '{guild_name}' ({active_servers} total active servers)")
        
        embed = Embed(
            title="📻 Radio Started",
            description=f"**{station_name}** is now playing in {voice_channel.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="🔊 Channel", value=voice_channel.name, inline=True)
        embed.add_field(name="🎵 Quality", value="Auto", inline=True)
        embed.set_footer(text="Alastor - The Radio Daemon")
        
        view = StationControlView(guild_id)
        if show_loading:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await safe_send_message(interaction, embed=embed, view=view)

    @radio.command(name="play", description="Play a radio station by name.")
    @app_commands.describe(name="Station name")
    @app_commands.autocomplete(name=get_station_autocomplete)
    async def play(self, interaction: Interaction, name: str):
        await self.play_radio_static(interaction, name)

    @radio.command(name="stop", description="Stop the currently playing radio and leave the voice channel.")
    async def stop(self, interaction: Interaction):
        await self.stop_radio_static(interaction)
        
    @staticmethod
    async def stop_radio_static(interaction: Interaction):
        guild_id = interaction.guild_id
        if guild_id not in current_radios:
            embed = Embed(
                title="📻 No Radio Playing",
                description="No radio is currently playing on this server.\n\nUse `/radio play` or `/radio list` to start playing.",
                color=discord.Color.yellow()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed)
            return

        station_name = current_radios[guild_id]["name"]
        voice_client = current_radios[guild_id]["voice_client"]
        guild_name = interaction.guild.name if interaction.guild else "Unknown"
        
        logger.info(f"📋 Stop request for '{station_name}' in '{guild_name}' by {interaction.user.display_name}")
        
        # Graceful shutdown
        try:
            voice_client.stop()
            await asyncio.wait_for(voice_client.disconnect(force=True), timeout=5.0)
            logger.info(f"✅ Successfully stopped and disconnected from '{guild_name}'")
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Voice client disconnect timed out for '{guild_name}'")
        except Exception as e:
            logger.error(f"❌ Error disconnecting from '{guild_name}': {e}")

        del current_radios[guild_id]
        save_state()
        
        # Update presence
        active_servers = len(current_radios)
        if active_servers > 0:
            await interaction.client.change_presence(
                activity=discord.Game(name=f"Radio on {active_servers} server{'s' if active_servers != 1 else ''}")
            )
        else:
            await interaction.client.change_presence(activity=discord.Game(name="Radio"))
            
        embed = Embed(
            title="⏹️ Radio Stopped",
            description=f"**{station_name}** has been stopped and I've left the voice channel.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await safe_send_message(interaction, embed=embed)

    @radio.command(name="info", description="Show detailed information about the currently playing radio station.")
    async def info(self, interaction: Interaction):
        await self.show_info_static(interaction)
        
    @staticmethod
    async def show_info_static(interaction: Interaction):
        guild_id = interaction.guild_id
        if guild_id in current_radios:
            radio_data = current_radios[guild_id]
            station_name = radio_data["name"]
            start_time = radio_data.get("start_time", time.time())
            uptime_seconds = int(time.time() - start_time)
            
            # Format uptime
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            embed = Embed(
                title="📻 Current Radio Station",
                description=f"**{station_name}** is currently playing.",
                color=discord.Color.blue()
            )
            embed.add_field(name="🕰️ Uptime", value=uptime_str, inline=True)
            embed.add_field(name="🏛️ Server", value=interaction.guild.name, inline=True)
            embed.add_field(name="🔗 Status", value="✅ Connected", inline=True)
            
            voice_client = radio_data["voice_client"]
            if voice_client and voice_client.channel:
                embed.add_field(name="🔊 Channel", value=voice_client.channel.name, inline=True)
                embed.add_field(name="👥 Listeners", value=str(len(voice_client.channel.members) - 1), inline=True)
                
            view = StationControlView(guild_id)
        else:
            embed = Embed(
                title="📻 Radio Status",
                description="No radio is currently playing on this server.\n\nUse `/radio play` or `/radio list` to start playing.",
                color=discord.Color.yellow()
            )
            view = None
            
        embed.set_footer(text="Alastor - The Radio Daemon")
        await safe_send_message(interaction, embed=embed, view=view)

    @radio.command(name="list", description="Browse all available radio stations with pagination.")
    async def list(self, interaction: Interaction):
        guild_id = interaction.guild_id
        available_stations = get_available_stations(guild_id)
        
        if not available_stations:
            embed = Embed(
                title="📻 No Stations Available",
                description="No radio stations configured yet.\n\nServer admins can use `/station add` to add new stations.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Alastor - The Radio Daemon")
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return

        global_count = len(RADIOS)
        server_count = len(server_stations.get(guild_id, {}))
        total_stations = len(available_stations)
        
        view = RadioListView(guild_id, page=0)
        embed = Embed(
            title="📻 Available Radio Stations",
            description=f"Choose from **{total_stations}** stations ({global_count} global, {server_count} server):\n\nSelect a station from the dropdown menu below:",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Alastor - The Radio Daemon • Page 1 of {(total_stations + 24) // 25}")
        await safe_send_message(interaction, embed=embed, view=view)
        

    # Station management commands (public but secure)
    station = app_commands.Group(name="station", description="Add and manage radio stations")
    
    @station.command(name="add", description="Add a radio station to this server (Admin only)")
    @app_commands.describe(
        name="Station name",
        url="Stream URL (supports .m3u, .m3u8, .pls playlists)",
        description="Optional description"
    )
    async def station_add(self, interaction: Interaction, name: str, url: str, description: str = ""):
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            embed = Embed(
                title="❌ Permission Denied",
                description="Only server administrators can add stations.\n\nAsk a server admin to add stations for you.",
                color=discord.Color.red()
            )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        
        # Validate the URL for security
        is_safe, safety_message = is_safe_url(url)
        if not is_safe:
            embed = Embed(
                title="❌ Unsafe URL",
                description=f"{safety_message}\n\nFor security, only safe streaming URLs are allowed.",
                color=discord.Color.red()
            )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
            
        # Check if station already exists (global or server-specific)
        guild_id = interaction.guild_id
        available_stations = get_available_stations(guild_id)
        if name in available_stations:
            embed = Embed(
                title="⚠️ Station Exists",
                description=f"Station **{name}** already exists on this server.\n\nChoose a different name.",
                color=discord.Color.yellow()
            )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
            
        # Test the URL
        loading_embed = Embed(
            title="🔄 Testing Station...",
            description=f"Validating **{name}** stream...",
            color=discord.Color.orange()
        )
        await safe_send_message(interaction, embed=loading_embed)
        
        test_url = await resolve_stream_url(url)
        if test_url is None:
            embed = Embed(
                title="❌ Invalid Stream",
                description=f"Could not resolve stream URL. Please check the URL and try again.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed)
            return
            
        # Add station to server-specific stations
        if guild_id not in server_stations:
            server_stations[guild_id] = {}
        
        server_stations[guild_id][name] = {
            "url": url,
            "added_by": interaction.user.id,
            "added_at": time.time()
        }
        if description:
            server_stations[guild_id][name]["description"] = description
        save_state()
        
        logger.info(f"➕ Admin {interaction.user.display_name} added server station '{name}' in {interaction.guild.name}: {url[:50]}...")
        
        embed = Embed(
            title="✅ Station Added",
            description=f"**{name}** has been added to this server!\n\n🎧 Only available on **{interaction.guild.name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="URL", value=url[:100] + ("..." if len(url) > 100 else ""), inline=False)
        if description:
            embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Added by", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Alastor - The Radio Daemon")
        await interaction.edit_original_response(embed=embed)
        
    @station.command(name="remove", description="Remove a server radio station (Admin only)")
    @app_commands.describe(name="Station name to remove")
    @app_commands.autocomplete(name=get_station_autocomplete)
    async def station_remove(self, interaction: Interaction, name: str):
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            embed = Embed(
                title="❌ Permission Denied",
                description="Only server administrators can remove stations.",
                color=discord.Color.red()
            )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
        
        guild_id = interaction.guild_id
            
        # Check if it's a server station (can't remove global stations)
        if guild_id not in server_stations or name not in server_stations[guild_id]:
            if name in RADIOS:
                embed = Embed(
                    title="❌ Cannot Remove Global Station",
                    description=f"**{name}** is a global station and cannot be removed.\n\nOnly server-specific stations can be removed.",
                    color=discord.Color.red()
                )
            else:
                embed = Embed(
                    title="❌ Station Not Found",
                    description=f"Station **{name}** does not exist on this server.",
                    color=discord.Color.red()
                )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
            
        # Check if station is currently playing on this server
        if guild_id in current_radios and current_radios[guild_id]["name"] == name:
            embed = Embed(
                title="⚠️ Station In Use",
                description=f"**{name}** is currently playing on this server.\n\nStop the station before removing it.",
                color=discord.Color.yellow()
            )
            await safe_send_message(interaction, embed=embed, ephemeral=True)
            return
            
        # Remove server station
        del server_stations[guild_id][name]
        if not server_stations[guild_id]:  # Remove empty dict
            del server_stations[guild_id]
        save_state()
        
        logger.info(f"➖ Admin {interaction.user.display_name} removed server station '{name}' from {interaction.guild.name}")
        
        embed = Embed(
            title="✅ Station Removed",
            description=f"**{name}** has been removed from this server.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Alastor - The Radio Daemon")
        await safe_send_message(interaction, embed=embed)
        

# Auto-leave functionality
auto_leave_tasks = {}

class ThankYouView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        
        # Get donation and GitHub URLs from config
        donations = config.get("donations", [])
        github_url = config.get("bot", {}).get("github_url", "https://github.com/bnfone/discord-bot-alastor")
        
        # Add first donation button if available
        if donations:
            button = ui.Button(
                label=donations[0]['name'],
                emoji=donations[0].get('emoji', '💝'),
                url=donations[0]['url'],
                style=discord.ButtonStyle.link
            )
            self.add_item(button)
        
        # Add GitHub star button
        github_button = ui.Button(
            label="⭐ GitHub Star",
            emoji="⭐",
            url=github_url,
            style=discord.ButtonStyle.link
        )
        self.add_item(github_button)

async def check_voice_channel_empty(bot, guild_id: int):
    """Check if voice channel is empty and leave after 30 seconds"""
    await asyncio.sleep(30)  # Wait 30 seconds
    
    # Check if still playing and channel is empty
    if guild_id not in current_radios:
        return  # Already stopped
    
    voice_client = current_radios[guild_id]["voice_client"]
    if not voice_client or not voice_client.is_connected():
        return  # Already disconnected
    
    # Check if anyone else is in the channel (excluding the bot)
    members_in_channel = [m for m in voice_client.channel.members if not m.bot]
    
    if not members_in_channel:  # Channel is empty
        station_name = current_radios[guild_id]["name"]
        channel = voice_client.channel
        
        # Stop and disconnect
        voice_client.stop()
        await voice_client.disconnect()
        del current_radios[guild_id]
        save_state()
        
        # Update presence
        active_servers = len(current_radios)
        if active_servers > 0:
            await bot.change_presence(
                activity=discord.Game(name=f"Radio on {active_servers} server{'s' if active_servers != 1 else ''}")
            )
        else:
            await bot.change_presence(activity=discord.Game(name="Radio"))
        
        # Send thank you message to a text channel
        guild = bot.get_guild(guild_id)
        if guild:
            # Try to find a general channel to send the message
            text_channel = None
            for ch in guild.text_channels:
                if ch.name.lower() in ['general', 'chat', 'main', 'lobby'] or 'general' in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        text_channel = ch
                        break
            
            if not text_channel:  # Fallback to first available text channel
                text_channel = next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
            
            if text_channel:
                embed = Embed(
                    title="👋 Thanks for listening!",
                    description=f"I left **{channel.name}** since no one was listening to **{station_name}**.\n\nThanks for using Alastor - The Radio Daemon!",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Alastor - The Radio Daemon • Support us below!")
                
                view = ThankYouView()
                try:
                    await text_channel.send(embed=embed, view=view)
                    logger.info(f"💌 Sent thank you message in {guild.name}")
                except discord.Forbidden:
                    logger.warning(f"❌ Cannot send thank you message in {guild.name}")
        
        logger.info(f"🚪 Auto-left empty voice channel in {guild.name if guild else 'Unknown Guild'}")
    
    # Clean up the task
    if guild_id in auto_leave_tasks:
        del auto_leave_tasks[guild_id]

# Add voice state monitoring to RadioCog
class RadioCogEnhanced(RadioCog):
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Monitor voice channel activity for auto-leave"""
        if member.bot:  # Ignore bot activities
            return
        
        # Check if someone left a channel where the bot is playing
        if before.channel and self.bot.user in [m for m in before.channel.members]:
            guild_id = before.channel.guild.id
            if guild_id in current_radios:
                voice_client = current_radios[guild_id]["voice_client"]
                if voice_client and voice_client.channel == before.channel:
                    # Check if channel is now empty (excluding bots)
                    members_in_channel = [m for m in before.channel.members if not m.bot]
                    
                    if not members_in_channel and guild_id not in auto_leave_tasks:
                        # Start auto-leave timer
                        auto_leave_tasks[guild_id] = asyncio.create_task(check_voice_channel_empty(self.bot, guild_id))
                        logger.info(f"⏰ Started 30s auto-leave timer for {before.channel.guild.name}")
                    elif members_in_channel and guild_id in auto_leave_tasks:
                        # Cancel auto-leave timer if someone joined back
                        auto_leave_tasks[guild_id].cancel()
                        del auto_leave_tasks[guild_id]
                        logger.info(f"⏰ Cancelled auto-leave timer for {before.channel.guild.name}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RadioCogEnhanced(bot))