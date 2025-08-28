use std::collections::HashMap;

use figment::{providers::{Env, Format, Yaml}, Figment};
use serde::{Deserialize, Serialize};
use url::Url;

use crate::error::{AlastorError, Result};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub discord_token: String,
    pub bot: BotConfig,
    pub radios: HashMap<String, RadioStation>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BotConfig {
    #[serde(default = "default_prefix")]
    pub prefix: String,
    #[serde(default = "default_description")]
    pub description: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RadioStation {
    pub url: String,
    #[serde(default)]
    pub aliases: Vec<String>,
    #[serde(default)]
    pub bitrate: Option<u32>,
    #[serde(default)]
    pub format: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
}

impl Config {
    pub fn load() -> Result<Self> {
        let config: Config = Figment::new()
            .merge(Yaml::file("config.yaml"))
            .merge(Env::prefixed("ALASTOR_"))
            .merge(Env::raw().only(&["DISCORD_TOKEN"]))
            .extract()
            .map_err(AlastorError::Config)?;

        // Validate Discord token
        if config.discord_token.is_empty() {
            return Err(AlastorError::Config(
                figment::Error::from("DISCORD_TOKEN is required")
            ));
        }

        // Validate radio station URLs
        for (name, station) in &config.radios {
            if let Err(_) = Url::parse(&station.url) {
                tracing::warn!("Invalid URL for station '{}': {}", name, station.url);
            }
        }

        Ok(config)
    }

    pub fn find_station(&self, query: &str) -> Option<(&String, &RadioStation)> {
        // First try exact match (case insensitive)
        if let Some(station) = self.radios.iter()
            .find(|(name, _)| name.to_lowercase() == query.to_lowercase()) {
            return Some(station);
        }

        // Then try alias match
        if let Some(station) = self.radios.iter()
            .find(|(_, station)| station.aliases.iter()
                .any(|alias| alias.to_lowercase() == query.to_lowercase())) {
            return Some(station);
        }

        // Finally try fuzzy match using Levenshtein distance
        let query_lower = query.to_lowercase();
        let mut best_match = None;
        let mut best_score = 0.7; // Minimum similarity threshold

        for (name, station) in &self.radios {
            let name_lower = name.to_lowercase();
            let similarity = 1.0 - (strsim::levenshtein(&query_lower, &name_lower) as f64 
                / name_lower.len().max(query_lower.len()) as f64);
            
            if similarity > best_score {
                best_score = similarity;
                best_match = Some((name, station));
            }

            // Also check aliases
            for alias in &station.aliases {
                let alias_lower = alias.to_lowercase();
                let alias_similarity = 1.0 - (strsim::levenshtein(&query_lower, &alias_lower) as f64 
                    / alias_lower.len().max(query_lower.len()) as f64);
                
                if alias_similarity > best_score {
                    best_score = alias_similarity;
                    best_match = Some((name, station));
                }
            }
        }

        best_match
    }

    pub fn get_station_names(&self) -> Vec<String> {
        self.radios.keys().cloned().collect()
    }

    pub fn search_stations(&self, query: &str) -> Vec<(&String, &RadioStation)> {
        if query.is_empty() {
            return self.radios.iter().take(25).collect();
        }

        let query_lower = query.to_lowercase();
        let mut matches: Vec<_> = self.radios.iter()
            .filter_map(|(name, station)| {
                let name_lower = name.to_lowercase();
                
                // Exact match gets highest priority
                if name_lower == query_lower {
                    return Some((name, station, 1.0));
                }
                
                // Prefix match gets high priority
                if name_lower.starts_with(&query_lower) {
                    return Some((name, station, 0.9));
                }
                
                // Contains match
                if name_lower.contains(&query_lower) {
                    return Some((name, station, 0.8));
                }
                
                // Alias matches
                for alias in &station.aliases {
                    let alias_lower = alias.to_lowercase();
                    if alias_lower == query_lower {
                        return Some((name, station, 0.95));
                    }
                    if alias_lower.starts_with(&query_lower) {
                        return Some((name, station, 0.85));
                    }
                    if alias_lower.contains(&query_lower) {
                        return Some((name, station, 0.75));
                    }
                }
                
                // Fuzzy match
                let similarity = 1.0 - (strsim::levenshtein(&query_lower, &name_lower) as f64 
                    / name_lower.len().max(query_lower.len()) as f64);
                
                if similarity > 0.6 {
                    Some((name, station, similarity * 0.7))
                } else {
                    None
                }
            })
            .collect();

        // Sort by score (descending)
        matches.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap());
        
        // Return top 25 matches
        matches.into_iter()
            .take(25)
            .map(|(name, station, _)| (name, station))
            .collect()
    }
}

fn default_prefix() -> String {
    "!".to_string()
}

fn default_description() -> String {
    "Alastor - The Radio Daemon: High-performance Discord radio bot inspired by Hazbin Hotel".to_string()
}