"""Load config.json and overlay secrets from a local .env file."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

CONFIG_PATH = Path("config.json")

# (env var name, nested config path)
ENV_OVERRIDES = (
    ("EMAIL_SENDER", ("notifications", "email", "sender_email")),
    ("EMAIL_PASSWORD", ("notifications", "email", "sender_password")),
    ("EMAIL_RECIPIENT", ("notifications", "email", "recipient_email")),
    ("PUSHOVER_USER_KEY", ("notifications", "pushover", "user_key")),
    ("PUSHOVER_API_TOKEN", ("notifications", "pushover", "api_token")),
    ("NTFY_TOPIC", ("notifications", "ntfy", "topic")),
    ("FACEBOOK_EMAIL", ("facebook_email",)),
    ("FACEBOOK_PASSWORD", ("facebook_password",)),
)


def _set_nested(config: dict, path: tuple[str, ...], value: str) -> None:
    node = config
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def load_config(config_path: str | Path = CONFIG_PATH) -> dict:
    load_dotenv()

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    for env_key, config_path_keys in ENV_OVERRIDES:
        value = os.getenv(env_key)
        if value:
            _set_nested(config, config_path_keys, value.strip())

    if os.getenv("NTFY_TOPIC"):
        config.setdefault("notifications", {}).setdefault("ntfy", {})["enabled"] = True

    if os.getenv("PUSHOVER_USER_KEY") and os.getenv("PUSHOVER_API_TOKEN"):
        config.setdefault("notifications", {}).setdefault("pushover", {})["enabled"] = True

    return config
