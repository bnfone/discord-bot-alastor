<div align="center">
  <img src="alastor.jpg" alt="Bot Profile" width="150" style="border-radius: 50%;">
</div>

<h1 align="center">Alastor - The Radio Daemon</h1>


**[Alastor - The Radio Daemon](https://hazbinhotel.fandom.com/wiki/Alastor)** is a powerful and fun Discord bot designed to play various radio stations in voice channels. Inspired by the character Alastor from the *[Hazbin Hotel](https://www.imdb.com/de/title/tt7216636/)* series (Prime Video), this bot is perfect for anyone who enjoys listening to radio stations with friends on Discord.

[![Publish Docker Image](https://github.com/bnfone/discord-bot-alastor/actions/workflows/publish-docker.yml/badge.svg)](https://github.com/bnfone/discord-bot-alastor/actions/workflows/publish-docker.yml)

---

## Features

- **Play Radio Stations**: Use the bot to stream radio stations directly into your Discord voice channels.
- **Supports Multiple Servers**: The bot can play different radio stations simultaneously on multiple servers.
- **Playlist Support**: Automatically resolves `.m3u`, `.m3u8`, and `.pls` playlists to ensure compatibility with most radio streams.
- **Slash Commands**: Easy-to-use Discord commands for managing radio playback.
- **English Language**: All responses and embeds are in English.
- **Modern Design**: Interactive dropdown menus for station selection and clean embed messages.

---

## Bot Setup & Discord Permissions

### Creating a Discord Bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application and bot
3. Copy the bot token for later use

### Required Bot Permissions
When adding the bot to your Discord server, ensure these permissions are selected:

**General Permissions:**
- View Channels
- Send Messages
- Embed Links

**Voice Permissions (CRITICAL for radio functionality):**
- Connect (to join voice channels)
- Speak (to play audio)
- Use Voice Activity (for audio streaming)

**Bot Invite URL:**
Use this URL template and replace `YOUR_BOT_CLIENT_ID` with your bot's Client ID:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_CLIENT_ID&permissions=3145728&scope=bot%20applications.commands
```

**Permission Value:** `3145728` includes all required permissions above.

**⚠️ Important:** Without proper voice permissions, the bot will fail to connect with error code 4006.

---

## How to Use the Bot

### Prerequisites
- Docker installed on your system.
- Basic knowledge of Docker and `docker-compose`.
- A Discord bot token (see Bot Setup section below).

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/bnfone/discord-bot-alastor.git
   cd discord-bot-alastor
   ```

2. Create a `docker-compose.yml` file with the following content:
   ```yaml
   services:
     bot:
       image: ghcr.io/bnfone/discord-bot-alastor:latest
       container_name: discord-alastor
       environment:
         - DISCORD_TOKEN=your-bot-token
         - CONFIG_PATH=/app/config.yaml
        volumes:
            - ./config.yaml:/app/config.yaml:ro
   ```

3. Create a `config.yaml` file in the root directory:
     ```yaml
     radios:
       BBC Radio 1:
         url: "http://example.com/bbc-radio-1"
       Example Station:
         url: "http://example.com/example-station"
     ```

4. Start the bot:
   ```bash
   docker-compose up -d
   ```

5. Check the bot logs to ensure it is running properly:
   ```bash
   docker-compose logs -f
   ```

### Bot Commands
- `/info` - Shows info about the bot.
- `/donate` - Shows a donation link.
- `/radio list` - Provides a dropdown of all available radio stations.
- `/radio play [NAME]` - Plays the mentioned radio station (if configured in config.yml).
- `/radio stop` - Stops the bot and leaves the voice channel.
- `/radio play [NAME]` - Plays the mentioned radio station (if configured in config.yml).
- `/radio info` - Shows the current playing radio station.

---

## Legal Disclaimer
This bot is for private use only. Using it for public purposes might require compliance with local copyright laws, including potential GEMA fees for music or similar content.

Please ensure you understand and comply with all applicable laws in your region.


---

### TO DO:
- better structure
- better error handling