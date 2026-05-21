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
    "max_emails_per_run": 20,
    "skip_processed": True
}

DEFAULT_RULES = """- Never suggest, invent, or commit to any specific date or timeframe unless the customer explicitly mentioned one first.
- If the customer mentions a specific date, acknowledge it and say you will try your best to accommodate it, but make clear you cannot guarantee it. Example: "I will do my best to have it done by [their date] but I can't make any promises."
- If the customer mentions a general timeframe (e.g. "first week of November"), acknowledge it and express intent without committing. Example: "I will take note of that and try my best to fit you in during that first week of November."
- Do not repeat, reference, or borrow any language from quoted or forwarded text in the email you are replying to. Respond only to what the customer actually wrote.
- Do not invent or assume any details not stated in the customer's message."""

DEFAULT_STYLE = {
    "style_description": "",
    "system_prompt": "",
    "custom_rules": DEFAULT_RULES,
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
            return json.loads(json.dumps(DEFAULT_STYLE))
        with open(STYLE_FILE) as f:
            saved = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_STYLE))
        merged.update(saved)
        return merged

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
