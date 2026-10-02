import re
import unicodedata
from typing import Dict, Any, List, Tuple

# Word-to-digit translation map for spelled-out phone numbers
WORD_DIGITS = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'
}

# Regex for standard and obfuscated phone numbers (Indian and global)
# Matches 10-digit numbers starting with 6-9, or +91 followed by 10 digits, with optional separators
RE_PHONE_STANDARD = re.compile(
    r'(?:\+?91[\s\-]?)?(?:\(?\b[6-9]\d{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{4}\b)|'
    r'(?:\b(?:\+?91[\s\-.]?)?[6-9](?:[\s\-._]?[0-9]){9}\b)'
)
RE_EMAIL_STANDARD = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
RE_EMAIL_OBFUSCATED = re.compile(r'\b[A-Za-z0-9._%+-]+\s+(?:at|@)\s+[A-Za-z0-9.-]+\s+(?:dot|\.)\s+[A-Za-z]{2,}\b', re.IGNORECASE)
RE_URL_STANDARD = re.compile(r'(?:https?://|www\.)[^\s/$.?#].[^\s]*', re.IGNORECASE)
RE_URL_DOMAIN = re.compile(r'\b[a-zA-Z0-9-]{2,}\.(?:com|org|net|in|io|co|xyz|me|app|link|top|site|club|live)\b', re.IGNORECASE)
RE_URL_OBFUSCATED = re.compile(
    r'(?:h[tx]{2}ps?://[^\s]+)|'
    r'\b[a-zA-Z0-9-]{2,}\s*(?:\[\.\]|\(\.\)|\s+dot\s+|\.\s*)(?:com|org|net|in|io|co|xyz|app|link)\b',
    re.IGNORECASE
)
RE_IP_ADDRESS = re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
RE_SOCIAL_HANDLES = re.compile(
    r'(?:\b(?:insta(?:gram)?|snap(?:chat)?|tele(?:gram)?|discord|whatsapp|roblox)\s*(?:id|handle|username|name)?\s*(?:is|:|@|\s)\s*([A-Za-z0-9._]{3,30}))|'
    r'(?:\bwa\b\s*(?:id|handle|username|name)?\s*(?:is|:|@|\s)\s*([A-Za-z0-9._]{3,30}))|'
    r'(?:@([A-Za-z0-9._]{3,30}))|'
    r'(?:\b(?:what\'?s\s*app|whatsapp)\s+me\b)|'
    r'(?:\b(?:add|dm|text|call|ping|follow|msg|message)\s+me\s+(?:on\s+)?(?:insta|snap|telegram|discord|whatsapp|roblox|phone))\b',
    re.IGNORECASE
)
RE_ADDRESS_SHARING = re.compile(
    r'\b(?:my\s+(?:house|home|street|flat|apartment|school)?\s*address\s+is|'
    r'i\s+live\s+(?:at|in|near)\b[^\n,.]+(?:street|road|layout|nagar|colony|apartments|cross|main|lane|block|sector)|'
    r'meet\s+me\s+(?:at|outside|near|after\s+school\b)|'
    r'give\s+me\s+your\s+address|'
    r'where\s+(?:is\s+your\s+school|do\s+you\s+(?:live|go\s+to\s+school)))\b',
    re.IGNORECASE
)
RE_CONTACT_NUDGE = re.compile(
    r'\b(?:'
    r'(?:give|send|share|tell)\s+me\s+your\s+(?:number|phone|insta|snap|email|whatsapp|address|location)|'
    r'send\s+(?:me\s+a\s+|your\s+)(?:selfie|picture|photo|number)|'
    r'(?:call|text)\s+me(?:\s+at)?|'
    r'share\s+your\s+(?:number|location)'
    r')\b',
    re.IGNORECASE
)
RE_SECRECY_CUES = re.compile(
    r'\b(?:don\'?t\s+tell\s+(?:your\s+)?(?:parents|anyone|mom|dad)|'
    r'(?:let\'?s\s+)?keep\s+(?:this|it)\s+(?:a\s+)?secret)\b',
    re.IGNORECASE
)

# Common date patterns (ISO, standard dates) to preserve without false positives
RE_DATE_PATTERN = re.compile(
    r'\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b'
)


def _normalize_text(text: str) -> str:
    """
    Unicode normalization (NFKC) + Arabic-Indic and Eastern Arabic-Indic digit translation.
    Converts full-width numbers (０-９) and Arabic digits (٠-٩, ۰-۹) to standard ASCII 0-9.
    NOTE: Optical Character Recognition (OCR) on embedded images is a planned future enhancement.
    """
    norm = unicodedata.normalize('NFKC', text)
    res = []
    for ch in norm:
        val = ord(ch)
        if 0x0660 <= val <= 0x0669:
            res.append(chr(ord('0') + (val - 0x0660)))
        elif 0x06F0 <= val <= 0x06F9:
            res.append(chr(ord('0') + (val - 0x06F0)))
        else:
            res.append(ch)
    return "".join(res)


def _check_spelled_out_numbers(text: str) -> Tuple[bool, str]:
    """Detect word-spelled/mixed phone numbers such as '984 five zero ...'."""
    low = text.lower()
    for w, d in WORD_DIGITS.items():
        low = re.sub(r'\b' + w + r'\b', d, low)
    # Look for 10 consecutive/spaced digits starting with 6-9
    m = re.search(r'\b[6-9](?:[\s\-_.]?\d){9}\b', low)
    if m:
        digits = re.sub(r'\D', '', m.group(0))
        return True, digits
    return False, ""


def scan_pii(text: str) -> Dict[str, Any]:
    """Local child-safety PII/contact screening.

    LittleNet's deterministic rules are always authoritative and available.
    Microsoft Presidio is then run locally as a richer recognizer layer when the
    dependency/model is installed. Presidio failure never disables the existing
    rules and never sends child text to a third party.
    """
    if not text or not isinstance(text, str):
        return {
            "detected": False, "categories": [], "severity": "LOW",
            "policy_action": "ALLOW", "redacted_text": "", "reason_codes": [],
            "presidio_available": False,
        }

    raw = _normalize_text(text.strip())
    categories: List[str] = []
    reason_codes: List[str] = []
    redacted = raw

    # Phone detection with tight boundary checks (avoids false-positive on dates/scattered numbers)
    phone_matches = RE_PHONE_STANDARD.findall(raw)
    valid_phones = []
    for p in phone_matches:
        d = re.sub(r'\D', '', p)
        if len(d) == 10 and d[0] in '6789':
            valid_phones.append(p)
        elif len(d) == 12 and d.startswith('91') and d[2] in '6789':
            valid_phones.append(p)

    spelled_phone, _ = _check_spelled_out_numbers(raw)
    if valid_phones or spelled_phone or RE_CONTACT_NUDGE.search(raw):
        categories.append("PHONE_NUMBER")
        reason_codes.append("DETECTED_PHONE_OR_CONTACT_REQUEST")
        redacted = RE_PHONE_STANDARD.sub("[PHONE]", redacted)
        if spelled_phone:
            redacted = "[PHONE]"

    if RE_EMAIL_STANDARD.search(raw) or RE_EMAIL_OBFUSCATED.search(raw):
        categories.append("EMAIL_ADDRESS")
        reason_codes.append("DETECTED_EMAIL")
        redacted = RE_EMAIL_STANDARD.sub("[EMAIL]", redacted)
        redacted = RE_EMAIL_OBFUSCATED.sub("[EMAIL]", redacted)

    if RE_URL_STANDARD.search(raw) or RE_URL_DOMAIN.search(raw):
        categories.extend(x for x in ("URL", "EXTERNAL_URL") if x not in categories)
        reason_codes.append("DETECTED_EXTERNAL_LINK")
        redacted = RE_URL_STANDARD.sub("[URL]", redacted)
        redacted = RE_URL_DOMAIN.sub("[URL]", redacted)
    if RE_URL_OBFUSCATED.search(raw):
        if "OBFUSCATED_URL" not in categories: categories.append("OBFUSCATED_URL")
        if "URL" not in categories: categories.append("URL")
        reason_codes.append("DETECTED_OBFUSCATED_LINK")
        redacted = RE_URL_OBFUSCATED.sub("[URL]", redacted)
    if RE_IP_ADDRESS.search(raw):
        categories.append("IP_ADDRESS")
        reason_codes.append("DETECTED_IP_ADDRESS")
        redacted = RE_IP_ADDRESS.sub("[IP_REDACTED]", redacted)

    if RE_SOCIAL_HANDLES.search(raw):
        categories.append("SOCIAL_HANDLE")
        reason_codes.append("DETECTED_SOCIAL_TRANSFER")
        redacted = RE_SOCIAL_HANDLES.sub("[SOCIAL_HANDLE_REDACTED]", redacted)
    if RE_ADDRESS_SHARING.search(raw):
        categories.append("PHYSICAL_LOCATION")
        reason_codes.append("DETECTED_ADDRESS_SHARING")
        redacted = RE_ADDRESS_SHARING.sub("[ADDRESS_REDACTED]", redacted)
    if RE_SECRECY_CUES.search(raw):
        categories.append("GROOMING_SECRECY")
        reason_codes.append("DETECTED_SECRECY_CUE")
        redacted = RE_SECRECY_CUES.sub("[SECRECY_CUE]", redacted)

    # Mature OSS enrichment. Run on the already-redacted text so deterministic
    # detections remain hidden while Presidio finds additional concrete entities.
    presidio = {"available": False, "categories": [], "redacted_text": redacted}
    try:
        from .presidio_adapter import analyze_pii
        presidio = analyze_pii(redacted)
        for category in presidio.get("categories", []):
            if category not in categories:
                categories.append(category)
                reason_codes.append("DETECTED_PRESIDIO_" + category)
        if presidio.get("matches"):
            redacted = presidio.get("redacted_text", redacted)
    except Exception:
        # Deterministic scanner above remains authoritative and must never fail
        # because an optional enrichment package/model is unavailable.
        presidio = {"available": False, "categories": [], "redacted_text": redacted}

    detected = bool(categories)
    critical = {"PHONE_NUMBER", "PHYSICAL_LOCATION", "GROOMING_SECRECY", "FINANCIAL_IDENTIFIER"}
    severity = "CRITICAL" if critical.intersection(categories) else ("HIGH" if detected else "LOW")
    policy_action = "BLOCK" if detected else "ALLOW"
    return {
        "detected": detected,
        "categories": categories,
        "severity": severity,
        "policy_action": policy_action,
        "redacted_text": redacted,
        "reason_codes": reason_codes,
        "presidio_available": bool(presidio.get("available")),
        "presidio_matches": presidio.get("matches", []),
    }
