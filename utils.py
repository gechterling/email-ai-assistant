import re

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
