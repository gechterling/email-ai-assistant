import imaplib
import email
import time
import re
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from email.header import decode_header as _decode_header
from typing import List, Dict, Optional


class IMAPClient:
    def __init__(self, config: dict):
        self.config = config["imap"]
        self.conn: Optional[imaplib.IMAP4] = None

    def connect(self):
        if self.config.get("ssl", True):
            self.conn = imaplib.IMAP4_SSL(self.config["host"], self.config.get("port", 993))
        else:
            self.conn = imaplib.IMAP4(self.config["host"], self.config.get("port", 143))
        self.conn.login(self.config["username"], self.config["password"])

    def disconnect(self):
        if self.conn:
            try:
                self.conn.logout()
            except Exception:
                pass
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def list_folders(self) -> List[str]:
        _, folders = self.conn.list()
        result = []
        for f in folders:
            if isinstance(f, bytes):
                parts = f.decode().split('"')
                name = parts[-1].strip().strip('"')
                if name:
                    result.append(name)
        return result

    def _decode_str(self, value: str) -> str:
        if not value:
            return ""
        parts = _decode_header(value)
        out = []
        for part, enc in parts:
            if isinstance(part, bytes):
                out.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return "".join(out)

    def _get_body(self, msg: email.message.Message) -> str:
        plain = None
        html = None
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and plain is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        plain = payload.decode(charset, errors="replace")
                elif ct == "text/html" and html is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                plain = payload.decode(charset, errors="replace")

        if plain:
            return plain
        if html:
            text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()
        return ""

    def get_inbox_emails(self, days_back: int = 7, max_count: int = 50) -> List[Dict]:
        folder = self.config.get("inbox_folder", "INBOX")
        self.conn.select(folder, readonly=True)

        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        _, ids_data = self.conn.search(None, f"SINCE {since}")
        ids = ids_data[0].split()
        if not ids:
            return []

        ids = ids[-max_count:]
        own_address = self.config["username"].lower()
        emails = []

        for msg_id in ids:
            _, msg_data = self.conn.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_addr = self._decode_str(msg.get("From", ""))
            if own_address in from_addr.lower():
                continue

            emails.append({
                "uid": msg_id.decode(),
                "message_id": msg.get("Message-ID", "").strip(),
                "subject": self._decode_str(msg.get("Subject", "(no subject)")),
                "from": from_addr,
                "date": msg.get("Date", ""),
                "body": self._get_body(msg),
            })

        return emails

    def get_sent_emails(self, max_count: int = 100, start_date: str = None, end_date: str = None, subject_filter: str = None) -> List[Dict]:
        sent_folder = self.config.get("sent_folder", "Sent")
        candidates = [sent_folder, "Sent", "Sent Items", "Sent Messages", "[Gmail]/Sent Mail"]
        selected = None
        for folder in candidates:
            try:
                status, _ = self.conn.select(folder, readonly=True)
                if status == "OK":
                    selected = folder
                    break
            except Exception:
                continue
        if not selected:
            return []

        criteria = []
        if start_date:
            criteria.append(f"SINCE {start_date}")
        if end_date:
            criteria.append(f"BEFORE {end_date}")
        if subject_filter:
            criteria.append(f'SUBJECT "{subject_filter}"')
        search_arg = " ".join(criteria) if criteria else "ALL"

        _, ids_data = self.conn.search(None, search_arg)
        ids = ids_data[0].split()
        if not ids:
            return []

        ids = ids[-max_count:]
        emails = []
        for msg_id in ids:
            _, msg_data = self.conn.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            body = self._get_body(msg)
            if body and len(body.strip()) > 30:
                emails.append({
                    "subject": self._decode_str(msg.get("Subject", "")),
                    "body": body.strip(),
                })

        return emails

    def save_draft(self, original: Dict, reply_body: str) -> bool:
        """
        Saves reply_body as an IMAP draft. Uses APPEND only — SMTP is never called.
        The message cannot send itself; only the user can send it from their mail client.
        """
        drafts_folder = self.config.get("drafts_folder", "Drafts")

        reply_to = original.get("reply_to") or original["from"]
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        msg = EmailMessage()
        msg["From"] = self.config["username"]
        msg["To"] = reply_to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if original.get("message_id"):
            msg["In-Reply-To"] = original["message_id"]
            msg["References"] = original["message_id"]

        msg.set_content(reply_body)

        date_time = imaplib.Time2Internaldate(time.time())
        self.conn.append(drafts_folder, "(\\Draft)", date_time, msg.as_bytes())
        return True
