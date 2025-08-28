pub mod radio;
pub mod info;
pub mod setup;

use serenity::{
    all::{
        Command, CommandInteraction, CommandOptionType, CreateCommand, CreateCommandOption,
        CreateInteractionResponse, CreateInteractionResponseMessage, Ready,
    },
    prelude::Context,
};
use tracing::{error, info};

use crate::error::Result;

pub async fn register_commands(ctx: &Context) -> Result<()> {
    let commands = vec![
        radio::create_radio_command(),
        info::create_info_command(),
        setup::create_setup_command(),
    ];

    Command::set_global_commands(&ctx.http, commands).await?;
    
    Ok(())
}

pub async fn handle_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    match command.data.name.as_str() {
        "radio" => radio::handle_radio_command(ctx, command).await,
        "info" => info::handle_info_command(ctx, command).await,
        "setup" => setup::handle_setup_command(ctx, command).await,
        _ => {
            error!("Unknown command: {}", command.data.name);
            Ok(())
        }
    }
}