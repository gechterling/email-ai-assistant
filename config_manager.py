import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
STYLE_FILE = BASE_DIR / "style_profile.json"
HISTORY_FILE = BASE_DIR / "history.json"
PROCESSED_FILE = BASE_DIR / "processed.json"

DEFAULT_CONFIG = {
    "imap": {
        "host": "",
        "port": 993,
        "username": "",
        "password": "",
        "ssl": True,
        "inbox_folder": "INBOX",
        "drafts_folder": "Drafts",
        "sent_folder": "Sent"
    },
    "ai": {
        "provider": "ollama",
        "ollama_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
        "cloud_provider": "anthropic",
        "cloud_api_key": "",
        "cloud_model": "claude-sonnet-4-6"
    },
    "keywords": [],
    "days_back": 7,
    "max_emails_per_run": 20,
    "skip_processed": True
}

DEFAULT_STYLE = {
    "style_description": "",
    "system_prompt": "",
    "examples": [],
    "last_analyzed": None,
    "emails_analyzed": 0
}


class ConfigManager:
    def get_config(self) -> dict:
        if not CONFIG_FILE.exists():
            return DEFAULT_CONFIG.copy()
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for key, value in saved.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    def save_config(self, config: dict):
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

    def get_style_profile(self) -> dict:
        if not STYLE_FILE.exists():
            return DEFAULT_STYLE.copy()
        with open(STYLE_FILE) as f:
            return json.load(f)

    def save_style_profile(self, profile: dict):
        with open(STYLE_FILE, "w") as f:
            json.dump(profile, f, indent=2)

    def get_history(self) -> list:
        if not HISTORY_FILE.exists():
            return []
        with open(HISTORY_FILE) as f:
            return json.load(f)

    def add_history_entry(self, entry: dict):
        history = self.get_history()
        entry["timestamp"] = datetime.now().isoformat()
        history.insert(0, entry)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history[:200], f, indent=2)

    def get_processed_ids(self) -> set:
        if not PROCESSED_FILE.exists():
            return set()
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))

    def mark_processed(self, message_id: str):
        ids = self.get_processed_ids()
        ids.add(message_id)
        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(ids)[-2000:], f)
