# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚨 IMPORTANT: Rust Rewrite Branch

This repository now has **TWO implementations**:

1. **`main` branch**: Original Python implementation (discord.py)
2. **`claude/rust-rewrite` branch**: New high-performance Rust implementation ⭐

**The Rust version is recommended for production use with 100+ servers.**

## Project Overview

This is **Alastor - The Radio Daemon**, a Discord radio bot that streams radio stations in voice channels. The bot is inspired by the character Alastor from Hazbin Hotel.

### Rust Implementation (claude/rust-rewrite branch) - RECOMMENDED

**Architecture**: High-performance async Rust using Serenity + Songbird
**Performance**: 5-10x less memory usage, 660+ concurrent streams per thread
**UX**: Modern slash commands with autocomplete, ephemeral responses, setup wizard
**Scale**: Designed for 100+ Discord servers with minimal resource usage

## Development Commands

### Rust Implementation (claude/rust-rewrite branch)

#### Environment Setup
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install system dependencies (Ubuntu/Debian)  
sudo apt-get install -y ffmpeg pkg-config libssl-dev cmake
```

#### Running Locally
```bash
export DISCORD_TOKEN=your_token_here
export ALASTOR_CONFIG_PATH=./config.yaml
cargo run --release
```

#### Docker Development (Rust)
```bash
# Build and run Rust version
docker-compose -f docker-compose.rust.yml up -d
docker-compose -f docker-compose.rust.yml logs -f

# Stop
docker-compose -f docker-compose.rust.yml down
```

#### Testing & Quality
```bash
cargo test
cargo fmt
cargo clippy -- -D warnings
cargo build --release
```

### Python Implementation (main branch) - Legacy

#### Environment Setup
```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

#### Running Locally
```bash
export DISCORD_TOKEN=your_token_here
export CONFIG_PATH=./config.yaml
python -m src.bot
```

#### Docker Development (Python)
```bash
docker build -t alastor .
docker compose up -d
docker compose logs -f
```

## Architecture Overview

### Rust Implementation (claude/rust-rewrite branch)

#### Core Structure
- **Entry Point**: `src/main.rs` - Async main with Serenity client and event handlers
- **Configuration**: `src/config.rs` - YAML + ENV config with fuzzy search and caching
- **Radio Manager**: `src/radio.rs` - Concurrent stream management using DashMap and Songbird
- **Commands**: `src/commands/` - Modern slash commands with autocomplete:
  - `radio.rs` - Smart autocomplete, health checks, ephemeral responses 
  - `info.rs` - Bot stats and performance metrics
  - `setup.rs` - Interactive setup wizard for admins
- **Error Handling**: `src/error.rs` - Comprehensive error types with user-friendly messages

#### Key Rust Components

##### RadioManager (`src/radio.rs:25`)
- **Concurrent State**: Uses `DashMap<GuildId, ActiveStream>` for thread-safe guild management
- **Stream Caching**: TTL-based caching with health checks (`CachedStream` struct)
- **Smart Cleanup**: Automatic cleanup of inactive streams and cached data
- **Performance**: Supports 660+ concurrent streams per thread using Songbird's scheduler

##### Configuration System (`src/config.rs:44`)
- **Fuzzy Search**: Levenshtein distance-based station matching with aliases
- **Hot Reloading**: Environment variable overrides with figment
- **Enhanced Metadata**: Station bitrate, format, descriptions, and aliases
- **Search API**: `search_stations()` with scoring and ranking

### Python Implementation (main branch) - Legacy

#### Core Structure  
- **Entry Point**: `src/bot.py` - Main bot initialization, loads cogs, handles Discord events
- **Configuration**: `src/config.py` - YAML config loader with environment variable overrides
- **Commands**: `src/commands/` - Discord slash commands organized as cogs:
  - `radio.py` - Core radio streaming functionality with playlist resolution
  - `info.py` - Bot information display
  - `donate.py` - Donation link display

### Key Components

#### Bot Initialization (`src/bot.py:1`)
- Loads configuration from `config.yaml` (configurable via `CONFIG_PATH`)
- Sets up Discord intents for message content and voice states
- Registers all cogs and syncs slash commands on startup
- Sets bot presence to show current activity

#### Radio System (`src/commands/radio.py:1`)
- **Global State**: `current_radios` dict tracks active streams per guild
- **Stream Resolution**: `resolve_stream_url()` function handles `.m3u`, `.m3u8`, `.pls` playlists
- **Voice Management**: Handles voice channel connections, moves between channels, manages audio playback
- **Commands**: `/radio play`, `/radio stop`, `/radio info`, `/radio list` (with dropdown UI)

#### Configuration System (`src/config.py:1`)
- Loads radio stations from YAML config
- Environment variable overrides: `BOT_PREFIX`, `BOT_DESCRIPTION`, `DISCORD_TOKEN`, `CONFIG_PATH`
- Default bot description references Hazbin Hotel character

### Radio Configuration (`config.yaml:1`)
Radio stations are defined in YAML format:
```yaml
radios:
  Station Name:
    url: "https://stream-url-here"
```

## Dependencies & Requirements

### Core Dependencies (`requirements.txt:1`)
- `discord.py==2.3.2` - Discord API wrapper with voice support
- `PyYAML==6.0` - YAML configuration parsing  
- `PyNaCl==1.5.0` - Voice encryption for Discord
- `requests==2.28.1` - HTTP requests for playlist resolution

### System Dependencies
- **FFmpeg** - Required for audio processing (installed in Docker image)
- **Python 3.10+** - Runtime environment

## Key Patterns & Conventions

### Error Handling
- Uses `safe_send_message()` helper in radio.py:37 to handle Discord interaction responses
- Comprehensive error handling for voice connections, stream resolution, and audio playback
- Logging for debugging audio playback issues

### Discord Interactions
- All commands use Discord slash commands (`app_commands`)
- Rich embeds with consistent branding ("Alastor - The Radio Daemon" footer)
- Interactive UI components (dropdown menus for station selection)

### Voice Management
- Per-guild state tracking in `current_radios` dictionary
- Automatic voice channel switching when users move
- Proper cleanup on stop/disconnect

## Environment Variables

### Required
- `DISCORD_TOKEN` - Discord bot token (never commit this)

### Optional
- `CONFIG_PATH` - Path to YAML config file (default: `config.yaml`)
- `BOT_PREFIX` - Command prefix (default: from config, fallback: `!`)
- `BOT_DESCRIPTION` - Bot description text

## Development Notes

### Adding New Commands
1. Create new cog file in `src/commands/`
2. Import and register in `src/bot.py:44` setup function
3. Follow existing patterns for embed styling and error handling

### Radio Stream Compatibility
- Bot automatically resolves playlist formats (M3U, M3U8, PLS)
- Stream resolution handled in `resolve_stream_url()` function
- FFmpeg options configured for audio-only streams (`-vn` flag)

### Docker Deployment
- Multi-stage build not used - simple Python slim image
- FFmpeg and build tools installed in container
- Config mounted as read-only volume
- Bot runs in module mode: `python -m src.bot`