import asyncio
import re
from email.utils import parseaddr
from typing import List, Dict, Optional, Tuple

from config_manager import ConfigManager
from imap_client import IMAPClient
from ai_client import AIClient
from utils import strip_quoted_text, strip_pii

_OCTOBER_RE = re.compile(r'\boctober\b', re.IGNORECASE)
_FLEXIBLE_RE = re.compile(
    r'\b(anytime|no rush|whenever|flexible|no hurry|no preference|'
    r'whatever works|whenever works|whenever you.re available|doesn.t matter)\b',
    re.IGNORECASE
)


def _detect_priority(body: str) -> Tuple[Optional[str], bool]:
    if _OCTOBER_RE.search(body):
        return "[PRIORITY: October requested]", True
    if _FLEXIBLE_RE.search(body):
        return "[FLEXIBLE: No specific timeframe]", True
    return None, False


EMAIL_USER_PROMPT = """Write a reply to the following email on behalf of the user.

SENDER'S FIRST NAME: {first_name}
FROM: {sender}
SUBJECT: {subject}
DATE: {date}

CUSTOMER'S MESSAGE (quoted/forwarded content already removed):
{body}

Use {first_name} as the greeting name if you include one. Write the reply now:"""


def _extract_first_name(from_field: str) -> str:
    name, addr = parseaddr(from_field)
    if name:
        return name.strip().split()[0]
    username = addr.split("@")[0] if "@" in addr else addr
    return username.replace(".", " ").replace("_", " ").split()[0].capitalize()


class EmailProcessor:
    def __init__(self, config_manager: ConfigManager):
        self.cfg = config_manager

    async def process(self, queue) -> dict:
        config = self.cfg.get_config()

        style = self.cfg.get_style_profile()
        if not style.get("system_prompt"):
            raise RuntimeError(
                "No writing style profile found. Go to Writing Style and click 'Analyze My Sent Emails' first."
            )

        processed_ids = self.cfg.get_processed_ids() if config.get("skip_processed", True) else set()

        await queue.put({"type": "status", "message": "Fetching emails from inbox..."})
        emails = await asyncio.to_thread(
            self._fetch_inbox,
            config,
            config.get("days_back", 7),
            config.get("max_emails_per_run", 20),
        )

        await queue.put({"type": "status", "message": f"Found {len(emails)} emails."})

        if config.get("skip_processed", True):
            new_emails = [e for e in emails if e["message_id"] not in processed_ids]
        else:
            new_emails = emails

        skipped = len(emails) - len(new_emails)
        if skipped:
            await queue.put({"type": "status", "message": f"Skipping {skipped} already-processed email(s)."})

        if not new_emails:
            return {"processed": 0, "drafts_saved": 0, "skipped": skipped, "errors": 0}

        await queue.put({"type": "status", "message": f"Generating AI replies for {len(new_emails)} email(s)..."})

        ai = AIClient(config)
        custom_rules = style.get("custom_rules", "").strip()
        system_prompt = style["system_prompt"]
        if custom_rules:
            system_prompt += f"\n\nADDITIONAL RULES:\n{custom_rules}"
        drafts_saved = 0
        errors = 0

        for i, em in enumerate(new_emails, 1):
            short_subject = em["subject"][:50]
            await queue.put({
                "type": "progress",
                "current": i,
                "total": len(new_emails),
                "message": f"Processing {i}/{len(new_emails)}: {short_subject}",
            })

            try:
                first_name = _extract_first_name(em["from"])
                clean_body = strip_pii(strip_quoted_text(em["body"])[:3000])
                priority_note, flagged = _detect_priority(em["body"])
                user_msg = EMAIL_USER_PROMPT.format(
                    first_name=first_name,
                    sender=em["from"],
                    subject=em["subject"],
                    date=em["date"],
                    body=clean_body,
                )
                reply = await ai.generate(system_prompt, user_msg)

                await asyncio.to_thread(self._save_draft, config, em, reply, flagged, priority_note)
                self.cfg.mark_processed(em["message_id"])
                self.cfg.add_history_entry({
                    "subject": em["subject"],
                    "from": em["from"],
                    "date": em["date"],
                    "status": "draft_saved",
                    "reply_preview": reply[:200],
                })
                drafts_saved += 1
                await queue.put({"type": "success", "message": f"Draft saved: {short_subject}"})

            except Exception as e:
                errors += 1
                self.cfg.add_history_entry({
                    "subject": em["subject"],
                    "from": em["from"],
                    "date": em["date"],
                    "status": "error",
                    "error": str(e),
                })
                await queue.put({"type": "error", "message": f"Error on '{short_subject}': {e}"})

        return {
            "processed": len(new_emails),
            "drafts_saved": drafts_saved,
            "skipped": skipped,
            "errors": errors,
        }

    def _fetch_inbox(self, config: dict, days_back: int, max_count: int) -> List[Dict]:
        with IMAPClient(config) as client:
            return client.get_inbox_emails(days_back=days_back, max_count=max_count)

    def _save_draft(self, config: dict, original: Dict, reply_body: str, flagged: bool = False, priority_note: str = None):
        with IMAPClient(config) as client:
            client.save_draft(original, reply_body, flagged=flagged, priority_note=priority_note)

