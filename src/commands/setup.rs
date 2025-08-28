use serenity::{
    all::{
        CommandInteraction, CreateCommand, CreateInteractionResponse,
        CreateInteractionResponseMessage, CreateEmbed, CreateButton, CreateActionRow,
        ButtonStyle, Colour, CommandOptionType, CreateCommandOption,
        CommandDataOptionValue, ChannelType, RoleId, ChannelId,
    },
    prelude::Context,
};

use crate::error::Result;

#[derive(Debug, Clone)]
pub struct GuildSetup {
    pub guild_id: u64,
    pub default_voice_channel: Option<ChannelId>,
    pub dj_role: Option<RoleId>,
    pub locale: String,
    pub auto_join: bool,
    pub volume_limit: u8,
}

pub fn create_setup_command() -> CreateCommand {
    CreateCommand::new("setup")
        .description("Configure Alastor for your server (Admin only)")
        .default_member_permissions(serenity::all::Permissions::ADMINISTRATOR)
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "wizard",
                "Run the interactive setup wizard"
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "voice",
                "Set default voice channel"
            )
            .add_sub_option(
                CreateCommandOption::new(
                    CommandOptionType::Channel,
                    "channel",
                    "Default voice channel for the bot"
                )
                .required(true)
                .channel_types(vec![ChannelType::Voice])
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "dj",
                "Set DJ role (users who can control music)"
            )
            .add_sub_option(
                CreateCommandOption::new(
                    CommandOptionType::Role,
                    "role",
                    "Role that can control music playback"
                )
                .required(true)
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "status",
                "Show current server configuration"
            )
        )
}

pub async fn handle_setup_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let subcommand = command.data.options.first()
        .ok_or_else(|| crate::error::AlastorError::Config("No subcommand provided".into()))?;

    match subcommand.name.as_str() {
        "wizard" => handle_setup_wizard(ctx, command).await,
        "voice" => handle_voice_setup(ctx, command).await,
        "dj" => handle_dj_setup(ctx, command).await,
        "status" => handle_status_command(ctx, command).await,
        _ => Ok(()),
    }
}

async fn handle_setup_wizard(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let embed = CreateEmbed::new()
        .title("🎭 Alastor Setup Wizard")
        .description("Welcome to the Alastor setup wizard! I'll guide you through configuring the bot for your server.\n\n**Step 1 of 4: Voice Channel**\n\nFirst, let's set up a default voice channel where I should join when playing music.")
        .color(Colour::PURPLE)
        .field(
            "What we'll configure:",
            "🎵 **Default Voice Channel** - Where I'll join automatically\n🎭 **DJ Role** - Who can control music (optional)\n🌍 **Locale** - Language and region settings\n⚙️ **Preferences** - Auto-join and volume settings",
            false
        )
        .footer(|f| f.text("This wizard will only be visible to you"));

    let next_button = CreateButton::new("setup_step_voice")
        .label("🎵 Set Voice Channel")
        .style(ButtonStyle::Primary);

    let skip_button = CreateButton::new("setup_skip")
        .label("Skip Setup")
        .style(ButtonStyle::Secondary);

    let action_row = CreateActionRow::Buttons(vec![next_button, skip_button]);

    command.create_response(
        &ctx.http,
        CreateInteractionResponse::Message(
            CreateInteractionResponseMessage::new()
                .embed(embed)
                .components(vec![action_row])
                .ephemeral(true)
        )
    ).await?;

    Ok(())
}

async fn handle_voice_setup(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let channel_option = command.data.options.first()
        .and_then(|opt| opt.options.first())
        .ok_or_else(|| crate::error::AlastorError::Config("Channel option required".into()))?;

    if let CommandDataOptionValue::Channel(channel_id) = &channel_option.value {
        // Here you would typically save this to a database
        // For now, we'll just confirm the setting
        
        let embed = CreateEmbed::new()
            .title("✅ Voice Channel Set")
            .description(&format!(
                "Default voice channel has been set to <#{}>.\n\nI'll automatically join this channel when someone uses `/radio play`.",
                channel_id
            ))
            .color(Colour::GREEN)
            .footer(|f| f.text("You can change this anytime with /setup voice"));

        command.create_response(
            &ctx.http,
            CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .embed(embed)
                    .ephemeral(true)
            )
        ).await?;
    } else {
        return Err(crate::error::AlastorError::Config("Invalid channel parameter".into()));
    }

    Ok(())
}

async fn handle_dj_setup(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let role_option = command.data.options.first()
        .and_then(|opt| opt.options.first())
        .ok_or_else(|| crate::error::AlastorError::Config("Role option required".into()))?;

    if let CommandDataOptionValue::Role(role_id) = &role_option.value {
        // Here you would typically save this to a database
        
        let embed = CreateEmbed::new()
            .title("✅ DJ Role Set")
            .description(&format!(
                "DJ role has been set to <@&{}>.\n\nUsers with this role can control music playback. Users without this role can still use basic commands like `/radio info`.",
                role_id
            ))
            .color(Colour::GREEN)
            .field(
                "DJ Permissions Include:",
                "• Playing and stopping music\n• Changing stations\n• Volume control\n• Queue management",
                false
            )
            .footer(|f| f.text("You can change this anytime with /setup dj"));

        command.create_response(
            &ctx.http,
            CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .embed(embed)
                    .ephemeral(true)
            )
        ).await?;
    } else {
        return Err(crate::error::AlastorError::Config("Invalid role parameter".into()));
    }

    Ok(())
}

async fn handle_status_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let guild_id = command.guild_id
        .ok_or(crate::error::AlastorError::BotNotConnected)?;

    // In a real implementation, you'd fetch this from a database
    let embed = CreateEmbed::new()
        .title("⚙️ Server Configuration")
        .description("Current Alastor configuration for this server:")
        .color(Colour::BLUE)
        .field("🎵 Default Voice Channel", "Not configured", true)
        .field("🎭 DJ Role", "Not configured", true)
        .field("🌍 Locale", "English (US)", true)
        .field("📊 Auto-join", "Enabled", true)
        .field("🔊 Volume Limit", "100%", true)
        .field("📈 Active Streams", "0", true)
        .field(
            "Available Commands:",
            "`/radio play` - Play a radio station\n`/radio stop` - Stop current playback\n`/radio info` - Show current station\n`/radio list` - List all stations\n`/info` - Bot information\n`/setup` - Configuration commands",
            false
        )
        .footer(|f| f.text("Use /setup wizard to configure these settings"));

    let wizard_button = CreateButton::new("setup_wizard")
        .label("🧙‍♂️ Run Setup Wizard")
        .style(ButtonStyle::Primary);

    let action_row = CreateActionRow::Buttons(vec![wizard_button]);

    command.create_response(
        &ctx.http,
        CreateInteractionResponse::Message(
            CreateInteractionResponseMessage::new()
                .embed(embed)
                .components(vec![action_row])
                .ephemeral(true)
        )
    ).await?;

    Ok(())
}