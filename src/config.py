import os
import yaml

def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Überschreibe den Bot-Prefix, falls in der ENV gesetzt:
    bot_config = config.get("bot", {})
    bot_config["prefix"] = os.getenv("BOT_PREFIX", bot_config.get("prefix", "!"))
    bot_config["description"] = os.getenv("BOT_DESCRIPTION", bot_config.get("description",
                         "This bot can play various radio stations. It's inspired by Alastor from the 'Hazbin Hotel' series (Prime Video). Learn more: https://hazbinhotel.fandom.com/wiki/Alastor"))
    config["bot"] = bot_config

    return config