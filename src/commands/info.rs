use serenity::{
    all::{
        CommandInteraction, CreateCommand, CreateInteractionResponse, 
        CreateInteractionResponseMessage, CreateEmbed, Colour,
    },
    prelude::Context,
};

use crate::{error::Result, radio::RadioManager};

pub fn create_info_command() -> CreateCommand {
    CreateCommand::new("info")
        .description("Show information about Alastor bot")
}

pub async fn handle_info_command(ctx: &Context, command: &CommandInteraction) -> Result<()> {
    let data = ctx.data.read().await;
    let radio_manager = data.get::<RadioManager>();
    
    let active_streams = radio_manager
        .map(|rm| rm.get_active_streams_count())
        .unwrap_or(0);

    let embed = CreateEmbed::new()
        .title("🎭 Alastor - The Radio Daemon")
        .description("High-performance Discord radio bot inspired by Hazbin Hotel")
        .color(Colour::PURPLE)
        .field("Version", "2.0.0 (Rust)", true)
        .field("Active Streams", active_streams.to_string(), true)
        .field("Language", "Rust 🦀", true)
        .field("Developer", "[Blake](https://github.com/bnfone)", false)
        .field("Source Code", "[GitHub](https://github.com/bnfone/discord-bot-alastor)", false)
        .field(
            "Features",
            "• High-performance concurrent audio streaming\n• Fuzzy search with autocomplete\n• Stream health checking\n• Ephemeral responses\n• Setup wizard",
            false
        )
        .thumbnail("https://i.imgur.com/your-alastor-image.png") // You can add the alastor.jpg here
        .footer(|f| f.text("Built with Serenity & Songbird"));

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