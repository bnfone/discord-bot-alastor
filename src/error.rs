use thiserror::Error;

#[derive(Error, Debug)]
pub enum AlastorError {
    #[error("Configuration error: {0}")]
    Config(#[from] figment::Error),
    
    #[error("Discord API error: {0}")]
    Discord(#[from] serenity::Error),
    
    #[error("Songbird error: {0}")]
    Songbird(#[from] songbird::error::JoinError),
    
    #[error("Songbird control error: {0}")]
    SongbirdControl(#[from] songbird::error::ControlError),
    
    #[error("HTTP request error: {0}")]
    Http(#[from] reqwest::Error),
    
    #[error("Station not found: {name}")]
    StationNotFound { name: String },
    
    #[error("Stream unavailable: {url}")]
    StreamUnavailable { url: String },
    
    #[error("User not in voice channel")]
    UserNotInVoice,
    
    #[error("Bot not connected to voice")]
    BotNotConnected,
    
    #[error("Rate limited: try again in {seconds}s")]
    RateLimit { seconds: u64 },
    
    #[error("Setup incomplete for guild {guild_id}")]
    SetupIncomplete { guild_id: u64 },
}

pub type Result<T> = std::result::Result<T, AlastorError>;