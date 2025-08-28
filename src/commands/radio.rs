use std::sync::Arc;

use serenity::{
    all::{
        CommandInteraction, CommandOptionType, CreateCommand, CreateCommandOption,
        CreateInteractionResponse, CreateInteractionResponseMessage, CreateEmbed,
        CreateAutocompleteResponse, CreateButton, CreateActionRow, ButtonStyle,
        Colour, InteractionResponseType, CommandDataOptionValue, AutocompleteInteraction,
    },
    prelude::Context,
};
use songbird::{get_voice_manager, Call};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::{
    error::{AlastorError, Result},
    radio::RadioManager,
};

pub fn create_radio_command() -> CreateCommand {
    CreateCommand::new("radio")
        .description("Control radio playback")
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "play",
                "Play a radio station"
            )
            .add_sub_option(
                CreateCommandOption::new(
                    CommandOptionType::String,
                    "station",
                    "Station name"
                )
                .required(true)
                .set_autocomplete(true)
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "choose",
                "Pick a station from a list"
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "stop",
                "Stop current radio playback"
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "info",
                "Show current playing station"
            )
        )
        .add_option(
            CreateCommandOption::new(
                CommandOptionType::SubCommand,
                "list",
                "List available stations"
            )
            .add_sub_option(
                CreateCommandOption::new(
                    CommandOptionType::String,
                    "search",
                    "Search stations"
                )
                .required(false)
            )
        )
}

pub async fn handle_radio_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let subcommand = command.data.options.first()
        .ok_or_else(|| AlastorError::Config("No subcommand provided".into()))?;

    match subcommand.name.as_str() {
        "play" => handle_play_command(ctx, command).await,
        "choose" => handle_choose_command(ctx, command).await,
        "stop" => handle_stop_command(ctx, command).await,
        "info" => handle_info_command(ctx, command).await,
        "list" => handle_list_command(ctx, command).await,
        _ => Ok(()),
    }
}

async fn handle_play_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let guild_id = command.guild_id.ok_or(AlastorError::BotNotConnected)?;
    
    // Get the station parameter
    let station_name = if let Some(option) = command.data.options.first()
        .and_then(|opt| opt.options.first()) {
        if let CommandDataOptionValue::String(name) = &option.value {
            name
        } else {
            return send_error_response(ctx, command, "Invalid station parameter").await;
        }
    } else {
        return send_error_response(ctx, command, "Station name is required").await;
    };

    // Check if user is in a voice channel
    let voice_channel_id = command.member.as_ref()
        .and_then(|member| member.user.voice_state.as_ref())
        .and_then(|vs| vs.channel_id)
        .ok_or(AlastorError::UserNotInVoice)?;

    // Defer response for potentially long operation
    command.create_response(
        &ctx.http,
        CreateInteractionResponse::Defer(
            CreateInteractionResponseMessage::new()
        )
    ).await?;

    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    // Check if station exists and get health info
    let (station_key, station) = radio_manager.get_config().find_station(station_name)
        .ok_or_else(|| AlastorError::StationNotFound { 
            name: station_name.to_string() 
        })?;

    // Perform preflight health check
    let is_healthy = radio_manager.check_stream_health(&station.url).await
        .unwrap_or(false);

    if !is_healthy {
        return send_health_check_failed_response(ctx, command, station_key, station).await;
    }

    // Get voice manager and join channel
    let manager = get_voice_manager(ctx).await;
    let call_result = manager.join(guild_id, voice_channel_id).await;

    let call_lock = match call_result {
        Ok(call_lock) => call_lock,
        Err(e) => {
            return send_error_response(ctx, command, &format!("Failed to join voice channel: {}", e)).await;
        }
    };

    // Play the station
    match radio_manager.play_station(
        guild_id,
        voice_channel_id,
        command.user.id,
        station_key,
        call_lock,
    ).await {
        Ok(_) => {
            // Update or create persistent player message
            upsert_player_message(ctx, command, station_key).await.ok();
            send_play_success_response(ctx, command, station_key, station).await
        }
        Err(e) => {
            error!("Failed to play station: {}", e);
            send_error_response(ctx, command, &format!("Failed to play station: {}", e)).await
        }
    }
}

async fn handle_choose_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    let station_names: Vec<String> = radio_manager.get_config().get_station_names();

    if station_names.is_empty() {
        return send_error_response(ctx, command, "No stations configured").await;
    }

    let mut menu = serenity::all::CreateSelectMenu::new(
        "player_choose",
        serenity::all::CreateSelectMenuKind::String { options: vec![] },
    )
    .placeholder("Select a station");

    for name in station_names.into_iter().take(25) {
        menu = menu.add_option(serenity::all::CreateSelectMenuOption::new(name.clone(), name));
    }

    let action_row = CreateActionRow::SelectMenu(menu);

    command.create_response(
        &ctx.http,
        CreateInteractionResponse::Message(
            CreateInteractionResponseMessage::new()
                .content("Pick a station to play:")
                .components(vec![action_row])
                .ephemeral(true)
        )
    ).await?;

    Ok(())
}

async fn upsert_player_message(ctx: &Context, command: &CommandInteraction, station_name: &str) -> Result<()> {
    let guild_id = command.guild_id.ok_or(AlastorError::BotNotConnected)?;
    let channel_id = command.channel_id;

    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    let embed = CreateEmbed::new()
        .title("📻 Alastor Player")
        .description(format!("Now playing: **{}**", station_name))
        .color(Colour::PURPLE);

    let next_button = CreateButton::new("player_next")
        .label("Next")
        .style(ButtonStyle::Primary);
    let stop_button = CreateButton::new("player_stop")
        .label("Stop")
        .style(ButtonStyle::Danger);
    let row = CreateActionRow::Buttons(vec![next_button, stop_button]);

    if let Some(msg_id) = radio_manager.get_player_message(guild_id) {
        channel_id
            .edit_message(&ctx.http, msg_id, |m| m.embed(|_| embed.clone()).components(|c| c.add_action_row(row.clone())))
            .await?;
    } else {
        let msg = channel_id
            .send_message(&ctx.http, |m| m.embed(|_| embed.clone()).components(|c| c.add_action_row(row.clone())))
            .await?;
        radio_manager.set_player_message(guild_id, msg.id);
    }

    Ok(())
}

async fn handle_stop_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let guild_id = command.guild_id.ok_or(AlastorError::BotNotConnected)?;

    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    match radio_manager.stop_station(guild_id).await? {
        Some(station_name) => {
            let embed = CreateEmbed::new()
                .title("⏹️ Radio Stopped")
                .description(&format!("Stopped **{}** and left the voice channel.", station_name))
                .color(Colour::ORANGE)
                .footer(|f| f.text("Alastor - The Radio Daemon"));

            command.create_response(
                &ctx.http,
                CreateInteractionResponse::Message(
                    CreateInteractionResponseMessage::new()
                        .embed(embed)
                        .ephemeral(true)
                )
            ).await?;

            // Leave voice channel
            let manager = get_voice_manager(ctx).await;
            manager.remove(guild_id).await?;
        }
        None => {
            let embed = CreateEmbed::new()
                .title("ℹ️ No Active Stream")
                .description("No radio is currently playing on this server.")
                .color(Colour::BLUE)
                .footer(|f| f.text("Alastor - The Radio Daemon"));

            command.create_response(
                &ctx.http,
                CreateInteractionResponse::Message(
                    CreateInteractionResponseMessage::new()
                        .embed(embed)
                        .ephemeral(true)
                )
            ).await?;
        }
    }

    Ok(())
}

async fn handle_info_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let guild_id = command.guild_id.ok_or(AlastorError::BotNotConnected)?;

    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    if let Some(active_stream) = radio_manager.get_current_station(guild_id) {
        let duration = chrono::Utc::now() - active_stream.started_at;
        let duration_str = format_duration(duration);

        let mut embed = CreateEmbed::new()
            .title("🎵 Currently Playing")
            .description(&format!("**{}**", active_stream.station_name))
            .color(Colour::GREEN)
            .field("Duration", duration_str, true)
            .field("Started by", format!("<@{}>", active_stream.started_by), true);

        if let Some(bitrate) = active_stream.station.bitrate {
            embed = embed.field("Bitrate", format!("{}kbps", bitrate), true);
        }

        if let Some(format) = &active_stream.station.format {
            embed = embed.field("Format", format, true);
        }

        embed = embed.footer(|f| f.text("Alastor - The Radio Daemon"));

        command.create_response(
            &ctx.http,
            CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .embed(embed)
                    .ephemeral(true)
            )
        ).await?;
    } else {
        let embed = CreateEmbed::new()
            .title("ℹ️ No Active Stream")
            .description("No radio is currently playing on this server.")
            .color(Colour::BLUE)
            .footer(|f| f.text("Alastor - The Radio Daemon"));

        command.create_response(
            &ctx.http,
            CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .embed(embed)
                    .ephemeral(true)
            )
        ).await?;
    }

    Ok(())
}

async fn handle_list_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    let search_query = command.data.options.first()
        .and_then(|opt| opt.options.first())
        .and_then(|opt| {
            if let CommandDataOptionValue::String(query) = &opt.value {
                Some(query.as_str())
            } else {
                None
            }
        })
        .unwrap_or("");

    let stations = radio_manager.get_config().search_stations(search_query);
    let total_count = radio_manager.get_config().radios.len();

    let mut description = if search_query.is_empty() {
        format!("**Available Stations** ({})", total_count)
    } else {
        format!("**Search Results for \"{}\"** ({} of {})", search_query, stations.len(), total_count)
    };

    for (name, station) in stations.iter().take(10) {
        let mut line = format!("• **{}**", name);
        
        if let Some(bitrate) = station.bitrate {
            line.push_str(&format!(" `{}kbps`", bitrate));
        }
        
        if let Some(format) = &station.format {
            line.push_str(&format!(" `{}`", format));
        }
        
        if let Some(desc) = &station.description {
            line.push_str(&format!(" - {}", desc));
        }
        
        description.push_str(&format!("\n{}", line));
    }

    if stations.len() > 10 {
        description.push_str(&format!("\n*... and {} more*", stations.len() - 10));
    }

    let embed = CreateEmbed::new()
        .title("📻 Radio Stations")
        .description(description)
        .color(Colour::PURPLE)
        .footer(|f| f.text("Use /radio play <station> to start playing"));

    command.create_response(
        &ctx.http,
        CreateInteractionResponse::Message(
            CreateInteractionResponseMessage::new()
                .embed(embed)
                .ephemeral(true)
        )
    ).await?;

    Ok(())
}

pub async fn handle_autocomplete(ctx: &Context, autocomplete: &AutocompleteInteraction) -> Result<()> {
    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>()
        .ok_or(AlastorError::BotNotConnected)?;

    let current_input = autocomplete.data.options.first()
        .and_then(|opt| opt.options.first())
        .and_then(|opt| opt.value.as_str())
        .unwrap_or("");

    let stations = radio_manager.get_config().search_stations(current_input);
    
    let choices: Vec<_> = stations.into_iter()
        .take(25)
        .map(|(name, _)| (name.clone(), name.clone()))
        .collect();

    autocomplete.create_response(
        &ctx.http,
        CreateAutocompleteResponse::new().set_choices(choices)
    ).await?;

    Ok(())
}

async fn send_error_response(
    ctx: &Context, 
    command: &CommandInteraction, 
    message: &str
) -> Result<()> {
    let embed = CreateEmbed::new()
        .title("❌ Error")
        .description(message)
        .color(Colour::RED)
        .footer(|f| f.text("Alastor - The Radio Daemon"));

    command.edit_response(
        &ctx.http,
        serenity::all::EditInteractionResponse::new().embed(embed)
    ).await?;

    Ok(())
}

async fn send_health_check_failed_response(
    ctx: &Context,
    command: &CommandInteraction,
    station_name: &str,
    station: &crate::config::RadioStation,
) -> Result<()> {
    let embed = CreateEmbed::new()
        .title("⚠️ Stream Unavailable")
        .description(&format!(
            "**{}** appears to be offline or unreachable.\n\nThis could be temporary - radio streams sometimes go offline briefly.",
            station_name
        ))
        .color(Colour::ORANGE)
        .footer(|f| f.text("Try again in a moment, or choose a different station"));

    let retry_button = CreateButton::new(format!("retry_{}", station_name))
        .label("🔄 Try Again")
        .style(ButtonStyle::Secondary);

    let list_button = CreateButton::new("show_alternatives")
        .label("📻 Show Alternatives")
        .style(ButtonStyle::Primary);

    let action_row = CreateActionRow::Buttons(vec![retry_button, list_button]);

    command.edit_response(
        &ctx.http,
        serenity::all::EditInteractionResponse::new()
            .embed(embed)
            .components(vec![action_row])
    ).await?;

    Ok(())
}

async fn send_play_success_response(
    ctx: &Context,
    command: &CommandInteraction,
    station_name: &str,
    station: &crate::config::RadioStation,
) -> Result<()> {
    let mut embed = CreateEmbed::new()
        .title("🎵 Radio Started")
        .description(&format!("Now playing **{}**", station_name))
        .color(Colour::GREEN);

    if let Some(bitrate) = station.bitrate {
        embed = embed.field("Bitrate", format!("{}kbps", bitrate), true);
    }

    if let Some(format) = &station.format {
        embed = embed.field("Format", format, true);
    }

    embed = embed.footer(|f| f.text("Alastor - The Radio Daemon"));

    command.edit_response(
        &ctx.http,
        serenity::all::EditInteractionResponse::new().embed(embed)
    ).await?;

    Ok(())
}

fn format_duration(duration: chrono::Duration) -> String {
    let total_seconds = duration.num_seconds();
    let hours = total_seconds / 3600;
    let minutes = (total_seconds % 3600) / 60;
    let seconds = total_seconds % 60;

    if hours > 0 {
        format!("{}h {}m {}s", hours, minutes, seconds)
    } else if minutes > 0 {
        format!("{}m {}s", minutes, seconds)
    } else {
        format!("{}s", seconds)
    }
}
