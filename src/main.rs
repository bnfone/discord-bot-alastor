mod commands;
mod config;
mod radio;
mod error;

use std::sync::Arc;

use anyhow::Context;
use serenity::{
    all::{
        GatewayIntents, Ready, Interaction, CommandInteraction, 
        AutocompleteInteraction, ComponentInteraction, ComponentInteractionDataKind,
    },
    async_trait,
    prelude::*,
};
use songbird::SerenityInit;
use tracing::{error, info, warn};
use std::time::Duration;
use governor::{Quota, RateLimiter, state::{direct::NotKeyed, InMemoryState}, clock::DefaultClock};

use crate::{
    commands::{register_commands, handle_command, radio},
    config::Config,
    radio::RadioManager,
};

struct Handler {
    radio_manager: Arc<RadioManager>,
    rate_limiter: RateLimiter<NotKeyed, InMemoryState, DefaultClock>,
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("🎭 {} is connected and ready!", ready.user.name);
        
        if let Err(why) = register_commands(&ctx).await {
            error!("Failed to register slash commands: {}", why);
        } else {
            info!("✅ Slash commands registered successfully");
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        // Rate limiting check
        if self.rate_limiter.check().is_err() {
            warn!("Rate limit exceeded for interaction");
            return;
        }

        match interaction {
            Interaction::Command(command) => {
                if let Err(why) = handle_command(&ctx, &command).await {
                    error!("Error handling command '{}': {}", command.data.name, why);
                }
            }
            Interaction::Autocomplete(autocomplete) => {
                if autocomplete.data.name == "radio" {
                    if let Err(why) = radio::handle_autocomplete(&ctx, &autocomplete).await {
                        error!("Error handling autocomplete: {}", why);
                    }
                }
            }
            Interaction::Component(component) => {
                if let Err(why) = handle_component_interaction(&ctx, &component).await {
                    error!("Error handling component interaction: {}", why);
                }
            }
            _ => {}
        }
    }
}

async fn handle_component_interaction(
    ctx: &Context, 
    component: &ComponentInteraction
) -> anyhow::Result<()> {
    // Handle button clicks and select menus
    match &component.data.kind {
        ComponentInteractionDataKind::Button => {
            match component.data.custom_id.as_str() {
                id if id.starts_with("retry_") => {
                    let station_name = id.strip_prefix("retry_").unwrap();
                    info!("Retrying station: {}", station_name);
                }
                "show_alternatives" => {
                    info!("Showing alternative stations");
                }
                "setup_wizard" => {
                    info!("Starting setup wizard from button");
                }
                "player_stop" => {
                    let guild_id = component.guild_id.ok_or(crate::error::AlastorError::BotNotConnected)?;
                    let data = ctx.data.read().await;
                    let radio_manager = data.get::<RadioManager>()
                        .ok_or(crate::error::AlastorError::BotNotConnected)?;
                    if let Some(name) = radio_manager.stop_station(guild_id).await? {
                        component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                            serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content(format!("Stopped {}", name))
                        )).await.ok();
                    }
                }
                "player_next" => {
                    let guild_id = component.guild_id.ok_or(crate::error::AlastorError::BotNotConnected)?;
                    let data = ctx.data.read().await;
                    let radio_manager = data.get::<RadioManager>()
                        .ok_or(crate::error::AlastorError::BotNotConnected)?;
                    let config = radio_manager.get_config().clone();
                    let current = radio_manager.get_current_station(guild_id)
                        .map(|s| s.station_name)
                        .unwrap_or_else(|| config.get_station_names().first().cloned().unwrap_or_default());
                    let names = config.get_station_names();
                    if names.is_empty() {
                        component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                            serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content("No stations configured")
                        )).await.ok();
                    } else {
                        let idx = names.iter().position(|n| n.eq_ignore_ascii_case(&current)).unwrap_or(0);
                        let next = &names[(idx + 1) % names.len()];
                        // Try to join user's current voice channel
                        if let Some(vc) = component.member.as_ref().and_then(|m| m.user.voice_state.as_ref()).and_then(|v| v.channel_id) {
                            let manager = songbird::get_voice_manager(ctx).await;
                            let call_lock = manager.join(guild_id, vc).await?;
                            radio_manager.play_station(guild_id, vc, component.user.id, next, call_lock).await?;
                            // Update player message
                            upsert_player_message_ctx(ctx, component.channel_id, guild_id, next).await.ok();
                            component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                                serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content(format!("Switched to {}", next))
                            )).await.ok();
                        } else {
                            component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                                serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content("Join a voice channel first")
                            )).await.ok();
                        }
                    }
                }
                _ => {
                    warn!("Unknown component interaction: {}", component.data.custom_id);
                }
            }
        }
        ComponentInteractionDataKind::StringSelect { values } => {
            if component.data.custom_id == "player_choose" {
                let guild_id = component.guild_id.ok_or(crate::error::AlastorError::BotNotConnected)?;
                if let Some(station) = values.first() {
                    if let Some(vc) = component.member.as_ref().and_then(|m| m.user.voice_state.as_ref()).and_then(|v| v.channel_id) {
                        let data = ctx.data.read().await;
                        let radio_manager = data.get::<RadioManager>()
                            .ok_or(crate::error::AlastorError::BotNotConnected)?;
                        let manager = songbird::get_voice_manager(ctx).await;
                        let call_lock = manager.join(guild_id, vc).await?;
                        radio_manager.play_station(guild_id, vc, component.user.id, station, call_lock).await?;
                        upsert_player_message_ctx(ctx, component.channel_id, guild_id, station).await.ok();
                        component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                            serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content(format!("Playing {}", station))
                        )).await.ok();
                    } else {
                        component.create_response(&ctx.http, serenity::all::CreateInteractionResponse::Message(
                            serenity::all::CreateInteractionResponseMessage::new().ephemeral(true).content("Join a voice channel first")
                        )).await.ok();
                    }
                }
            }
        }
        _ => {}
    }
    Ok(())
}

async fn upsert_player_message_ctx(ctx: &Context, channel_id: serenity::all::ChannelId, guild_id: serenity::all::GuildId, station_name: &str) -> anyhow::Result<()> {
    use serenity::all::{CreateEmbed, Colour, CreateButton, ButtonStyle, CreateActionRow};
    let embed = CreateEmbed::new()
        .title("📻 Alastor Player")
        .description(format!("Now playing: **{}**", station_name))
        .color(Colour::PURPLE);

    let next_button = CreateButton::new("player_next").label("Next").style(ButtonStyle::Primary);
    let stop_button = CreateButton::new("player_stop").label("Stop").style(ButtonStyle::Danger);
    let row = CreateActionRow::Buttons(vec![next_button, stop_button]);

    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>().ok_or(crate::error::AlastorError::BotNotConnected)?;

    if let Some(msg_id) = radio_manager.get_player_message(guild_id) {
        channel_id.edit_message(&ctx.http, msg_id, |m| m.embed(|_| embed.clone()).components(|c| c.add_action_row(row.clone()))).await?;
    } else {
        let msg = channel_id.send_message(&ctx.http, |m| m.embed(|_| embed.clone()).components(|c| c.add_action_row(row.clone()))).await?;
        radio_manager.set_player_message(guild_id, msg.id);
    }
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "alastor_bot=info".into()),
        )
        .init();

    info!("🎭 Starting Alastor - The Radio Daemon v2.0");

    // Load configuration
    let config = Config::load().context("Failed to load configuration")?;
    let token = config.discord_token.clone();

    // Create radio manager
    let radio_manager = Arc::new(RadioManager::new(config.clone()));

    // Create rate limiter (10 requests per minute per bot)
    let rate_limiter = RateLimiter::direct(Quota::per_minute(std::num::NonZeroU32::new(60).unwrap()));

    // Configure the client with the framework
    let intents = GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::GUILD_VOICE_STATES
        | GatewayIntents::MESSAGE_CONTENT;

    let mut client = Client::builder(&token, intents)
        .event_handler(Handler { 
            radio_manager: radio_manager.clone(),
            rate_limiter,
        })
        .register_songbird()
        .type_map_insert::<RadioManager>(radio_manager)
        .await
        .context("Error creating client")?;

    // Start listening for events
    if let Err(why) = client.start().await {
        error!("Client error: {:?}", why);
    }

    Ok(())
}
