import re

_PHONE_RE = re.compile(
    r'\b(\+?1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})\b'
)
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
_ADDRESS_RE = re.compile(
    r'\b\d{1,5}\s+[A-Za-z0-9][A-Za-z0-9\s]{1,30}'
    r'(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|Lane|Ln|'
    r'Court|Ct|Way|Place|Pl|Circle|Cir|Highway|Hwy|Parkway|Pkwy)\b\.?',
    re.IGNORECASE
)


def strip_pii(text: str) -> str:
    """Replace phone numbers, email addresses, and street addresses with placeholders."""
    text = _EMAIL_RE.sub('[email]', text)
    text = _PHONE_RE.sub('[phone]', text)
    text = _ADDRESS_RE.sub('[address]', text)
    return text


# Patterns that indicate the start of quoted/forwarded content
_QUOTE_BREAKS = [
    re.compile(r'^>'),                                                      # > quoted lines
    re.compile(r'^On .{5,100} wrote:\s*$', re.IGNORECASE),                 # On [date], X wrote:
    re.compile(r'^-{3,}\s*(original|forwarded)\s+message', re.IGNORECASE), # --- Original Message ---
    re.compile(r'^_{5,}\s*$'),                                              # ___________ (Outlook)
    re.compile(r'^From:\s+\S+@\S+'),                                        # From: email@domain (quoted header)
    re.compile(r'^Sent:\s+\w+,'),                                           # Sent: Monday, ... (quoted header)
    re.compile(r'^\[mailto:'),                                               # [mailto:...] Outlook style
]


def strip_quoted_text(text: str) -> str:
    """Remove quoted/forwarded email content, keeping only the top reply."""
    if not text:
        return text

    lines = text.splitlines()
    clean = []

    for line in lines:
        stripped = line.strip()
        if any(p.match(stripped) for p in _QUOTE_BREAKS):
            break
        clean.append(line)

    result = "\n".join(clean).strip()
    return result if result else text  # fall back to original if everything got stripped
