use std::{sync::Arc, time::Duration};

use dashmap::DashMap;
use serenity::{
    all::{ChannelId, GuildId, UserId, MessageId},
    prelude::TypeMapKey,
};
use songbird::{
    input::{Restartable, Input},
    Call, Event, EventContext, EventHandler as VoiceEventHandler, TrackEvent,
};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::{
    config::{Config, RadioStation},
    error::{AlastorError, Result},
};

pub struct RadioManager {
    config: Config,
    active_streams: DashMap<GuildId, ActiveStream>,
    stream_cache: DashMap<String, CachedStream>,
    player_messages: DashMap<GuildId, MessageId>,
}

#[derive(Debug, Clone)]
pub struct ActiveStream {
    pub station_name: String,
    pub station: RadioStation,
    pub channel_id: ChannelId,
    pub started_by: UserId,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub call_lock: Arc<Mutex<Call>>,
}

#[derive(Debug, Clone)]
struct CachedStream {
    pub input: Restartable,
    pub cached_at: chrono::DateTime<chrono::Utc>,
    pub health_check_passed: bool,
}

impl TypeMapKey for RadioManager {
    type Value = Arc<RadioManager>;
}

impl RadioManager {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            active_streams: DashMap::new(),
            stream_cache: DashMap::new(),
            player_messages: DashMap::new(),
        }
    }

    pub async fn play_station(
        &self,
        guild_id: GuildId,
        channel_id: ChannelId,
        user_id: UserId,
        station_name: &str,
        call_lock: Arc<Mutex<Call>>,
    ) -> Result<()> {
        let (station_key, station) = self.config.find_station(station_name)
            .ok_or_else(|| AlastorError::StationNotFound { 
                name: station_name.to_string() 
            })?;

        info!("🎵 Playing station '{}' in guild {}", station_key, guild_id);

        // Get or create stream input
        let input = self.get_stream_input(&station.url).await?;

        // Play the stream
        {
            let mut call = call_lock.lock().await;
            
            // Stop any current playback
            call.stop();
            
            let track_handle = call.play(input.into());
            
            // Add event handler for track end
            track_handle.add_event(
                Event::Track(TrackEvent::End),
                TrackEndHandler::new(guild_id, station_key.clone()),
            )?;
        }

        // Update active streams
        let active_stream = ActiveStream {
            station_name: station_key.clone(),
            station: station.clone(),
            channel_id,
            started_by: user_id,
            started_at: chrono::Utc::now(),
            call_lock,
        };

        self.active_streams.insert(guild_id, active_stream);

        Ok(())
    }

    pub async fn stop_station(&self, guild_id: GuildId) -> Result<Option<String>> {
        if let Some((_, active_stream)) = self.active_streams.remove(&guild_id) {
            let mut call = active_stream.call_lock.lock().await;
            call.stop();
            
            info!("⏹️ Stopped station '{}' in guild {}", active_stream.station_name, guild_id);
            Ok(Some(active_stream.station_name))
        } else {
            Ok(None)
        }
    }

    pub fn get_current_station(&self, guild_id: GuildId) -> Option<ActiveStream> {
        self.active_streams.get(&guild_id).map(|entry| entry.value().clone())
    }

    pub async fn check_stream_health(&self, url: &str) -> Result<bool> {
        info!("🔍 Performing health check for stream: {}", url);

        // First check if it's a playlist URL that needs resolution
        let resolved_url = if url.ends_with(".m3u") || url.ends_with(".m3u8") || url.ends_with(".pls") {
            self.resolve_playlist_url(url).await?
        } else {
            url.to_string()
        };

        // Perform HTTP head request to check if stream is accessible
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(10))
            .build()?;

        match client.head(&resolved_url).send().await {
            Ok(response) => {
                let is_healthy = response.status().is_success();
                if is_healthy {
                    info!("✅ Stream health check passed for: {}", url);
                } else {
                    warn!("❌ Stream health check failed with status {}: {}", 
                          response.status(), url);
                }
                Ok(is_healthy)
            }
            Err(e) => {
                warn!("❌ Stream health check failed with error: {} for {}", e, url);
                Ok(false)
            }
        }
    }

    async fn get_stream_input(&self, url: &str) -> Result<Restartable> {
        // Check cache first
        if let Some(cached) = self.stream_cache.get(url) {
            let cache_age = chrono::Utc::now() - cached.cached_at;
            if cache_age < chrono::Duration::minutes(5) && cached.health_check_passed {
                info!("📦 Using cached stream input for: {}", url);
                return Ok(cached.input.clone());
            }
        }

        info!("🔄 Creating new stream input for: {}", url);

        // Resolve the URL if it's a playlist
        let resolved_url = if url.ends_with(".m3u") || url.ends_with(".m3u8") || url.ends_with(".pls") {
            self.resolve_playlist_url(url).await?
        } else {
            url.to_string()
        };

        // Create the input
        let input = Restartable::ffmpeg(resolved_url, true)
            .await
            .map_err(|e| AlastorError::StreamUnavailable { 
                url: url.to_string() 
            })?;

        // Perform health check
        let health_check_passed = self.check_stream_health(url).await.unwrap_or(false);

        // Cache the input
        let cached_stream = CachedStream {
            input: input.clone(),
            cached_at: chrono::Utc::now(),
            health_check_passed,
        };
        self.stream_cache.insert(url.to_string(), cached_stream);

        Ok(input)
    }

    async fn resolve_playlist_url(&self, playlist_url: &str) -> Result<String> {
        info!("🔍 Resolving playlist URL: {}", playlist_url);

        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()?;

        let response = client.get(playlist_url).send().await?;
        let content = response.text().await?;

        // Parse the playlist content
        for line in content.lines() {
            let line = line.trim();
            if !line.is_empty() && !line.starts_with('#') {
                if line.starts_with("http") {
                    info!("✅ Resolved playlist to: {}", line);
                    return Ok(line.to_string());
                }
            }
        }

        Err(AlastorError::StreamUnavailable { 
            url: playlist_url.to_string() 
        })
    }

    pub fn get_config(&self) -> &Config {
        &self.config
    }

    pub fn get_active_streams_count(&self) -> usize {
        self.active_streams.len()
    }

    pub fn set_player_message(&self, guild_id: GuildId, message_id: MessageId) {
        self.player_messages.insert(guild_id, message_id);
    }

    pub fn get_player_message(&self, guild_id: GuildId) -> Option<MessageId> {
        self.player_messages.get(&guild_id).map(|m| *m.value())
    }

    pub fn clear_player_message(&self, guild_id: GuildId) {
        self.player_messages.remove(&guild_id);
    }

    pub fn cleanup_inactive_streams(&self) {
        let cutoff = chrono::Utc::now() - chrono::Duration::hours(1);
        
        self.active_streams.retain(|guild_id, stream| {
            if stream.started_at < cutoff {
                info!("🧹 Cleaning up inactive stream for guild {}", guild_id);
                false
            } else {
                true
            }
        });

        // Also cleanup old cached streams
        self.stream_cache.retain(|url, cached| {
            if cached.cached_at < cutoff {
                info!("🧹 Cleaning up cached stream: {}", url);
                false
            } else {
                true
            }
        });
    }
}

struct TrackEndHandler {
    guild_id: GuildId,
    station_name: String,
}

impl TrackEndHandler {
    fn new(guild_id: GuildId, station_name: String) -> Self {
        Self {
            guild_id,
            station_name,
        }
    }
}

#[serenity::async_trait]
impl VoiceEventHandler for TrackEndHandler {
    async fn act(&self, _ctx: &EventContext<'_>) -> Option<Event> {
        warn!("🔄 Track ended for station '{}' in guild {}", 
              self.station_name, self.guild_id);
        None
    }
}
