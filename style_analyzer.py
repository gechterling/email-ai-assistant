import asyncio
import random
from typing import List, Dict

from config_manager import ConfigManager
from imap_client import IMAPClient
from ai_client import AIClient


ANALYSIS_PROMPT = """You are analyzing email samples to build a detailed writing style profile.

Below are emails written by the user. Analyze them carefully and produce a detailed style guide that can be used to write future emails that sound exactly like this person.

Cover ALL of the following:
- Greeting style (how they open emails, e.g. "Hi Name," / "Hello," / no greeting)
- Sign-off style (how they close emails, e.g. "Thanks," / "Best," / just their name / nothing)
- Sentence length and structure (short/punchy? long/detailed? mix?)
- Tone (formal, casual, friendly, professional, direct?)
- Use of punctuation (exclamation points? ellipses? comma usage?)
- Paragraph length and spacing
- Level of detail and verbosity
- Any characteristic phrases, words, or habits they repeat
- How they handle requests, questions, and follow-ups

EMAIL SAMPLES:
{samples}

Write the style guide now. Be specific — quote actual patterns you observe. This profile will be used verbatim in AI prompts to replicate their writing style."""


SYSTEM_PROMPT_TEMPLATE = """You are writing email replies on behalf of the user. Your goal is to write responses that sound exactly like them — not like an AI.

THEIR WRITING STYLE:
{style_description}

RULES:
- Write only the email body. No subject line.
- Match their greeting and sign-off style exactly.
- Do not add placeholder text like [Your Name] or [Name].
- Do not mention that you are an AI or that this is a draft.
- Be natural and human. Match their level of formality and verbosity.
- If the email requires information you don't have, write a response that acknowledges the email and asks for what's needed, in their voice.
- Never invent facts you don't know.
- Keep the response proportional in length to the incoming email."""


class StyleAnalyzer:
    def __init__(self, config_manager: ConfigManager):
        self.cfg = config_manager

    async def analyze(self, queue) -> dict:
        config = self.cfg.get_config()

        await queue.put({"type": "status", "message": "Connecting to mail server..."})
        emails = await asyncio.to_thread(self._fetch_sent, config)

        if not emails:
            raise RuntimeError("No sent emails found. Check your Sent folder name in Settings.")

        await queue.put({"type": "status", "message": f"Found {len(emails)} sent emails. Selecting samples..."})

        samples = self._select_samples(emails, n=25)
        formatted = self._format_samples(samples)

        await queue.put({"type": "status", "message": f"Sending {len(samples)} emails to AI for style analysis (this may take a minute)..."})

        ai = AIClient(config)
        prompt = ANALYSIS_PROMPT.format(samples=formatted)
        style_description = await ai.generate(
            "You are an expert writing analyst. Be thorough and specific.",
            prompt,
        )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(style_description=style_description)

        example_bodies = [e["body"][:300] for e in samples[:3]]

        profile = {
            "style_description": style_description,
            "system_prompt": system_prompt,
            "examples": example_bodies,
            "emails_analyzed": len(emails),
            "last_analyzed": __import__("datetime").datetime.now().isoformat(),
        }
        self.cfg.save_style_profile(profile)

        return {"emails_analyzed": len(emails), "samples_used": len(samples)}

    def _fetch_sent(self, config: dict) -> List[Dict]:
        with IMAPClient(config) as client:
            return client.get_sent_emails(max_count=150)

    def _select_samples(self, emails: List[Dict], n: int = 25) -> List[Dict]:
        if len(emails) <= n:
            return emails
        step = len(emails) // n
        sampled = emails[::step][:n]
        return sampled

    def _format_samples(self, emails: List[Dict]) -> str:
        parts = []
        for i, e in enumerate(emails, 1):
            subject = e.get("subject", "")
            body = e["body"][:800].strip()
            parts.append(f"--- Email {i} (Subject: {subject}) ---\n{body}")
        return "\n\n".join(parts)
