import re

# sᴍᴀʟʟᴄᴀᴘS rendering for English inline-button labels.
_SMALL_CAPS = str.maketrans({
    "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ", "G": "ɢ",
    "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ", "M": "ᴍ", "N": "ɴ",
    "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ", "S": "s", "T": "ᴛ", "U": "ᴜ",
    "V": "ᴠ", "W": "ᴡ", "X": "x", "Y": "ʏ", "Z": "ᴢ",
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ",
    "w": "ᴡ", "y": "ʏ", "z": "ᴢ",
})


def to_small_caps(text: str) -> str:
    return (text or "").translate(_SMALL_CAPS)


def strip_html(text: str) -> str:
    """Plain-text fallback for messages whose HTML markup was rejected."""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    text = re.sub(r"</?p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def split_chunks(text: str, size: int = 3900) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text or ""), size)] or [""]


# Insults toward the bot, its creators or Vibegram trigger an automatic warning.
_TARGET_RE = re.compile(
    r"پویا|pouya|pooya|thepouya|شایان|حیدری|shayan|heydari|"
    r"وایبگرام|vibegram|وایب‌چت|وایبچت|vibechat|وایب|vibe|سازنده|ربات",
    re.I,
)
_INSULT_RE = re.compile(
    r"احمق|خنگ|بی\s*شعور|بیشعور|الاغ|\bخر\b|\bکص\b|کصکش|کس\s*کش|\bکوس\b|"
    r"جنده|هرزه|عوضی|دیوث|ابله|مادر\s*(?:قحبه|جنده|سنگ)|"
    r"\bidiot\b|\bstupid\b|\bdumb(?:ass)?\b|\bmoron\b|\bfool(?:ish)?\b|"
    r"\bfuck\w*\b|\bshit\w*\b|\bbastard\b|\basshole\b|\bbitch\b|"
    r"\bloser\b|\bgarbage\b|\bclown\b|\btrash\b|\bpathetic\b|\buseless\b",
    re.I,
)
# "خر نیست" / "stupid, isn't it" style negations must not produce warnings.
_NEGATION_RE = re.compile(
    r"^\s*(?:نیست\S*|نباش\S*|نبود|نیستم|نمیش\S*|نه\b|isn'?t|aren'?t|not\b|nope\b)",
    re.I,
)


def insult_hit(text: str) -> bool:
    low = (text or "").lower()
    if not low:
        return False
    for target in _TARGET_RE.finditer(low):
        window = low[max(0, target.start() - 80): target.end() + 80]
        for insult in _INSULT_RE.finditer(window):
            if _NEGATION_RE.match(window[insult.end(): insult.end() + 22]):
                continue
            return True
    return False


_RE_THANKS = ["ممنون", "مرسی", "تشکر", "سپاس", "دمت", "مچکر", "thanks", "thank you", "tnx"]
_RE_LOVE = ["دوستت دارم", "دوست دارم", "عشق", "عاشقتم", "عاشق", "love you", "❤️", "😍"]
_RE_FUN = ["خنده", "خندیدم", "ههه", "خخ", "😂", "🤣", "lol", "lmao", "haha", "جوک", "joke"]
_RE_SAD = ["ناراحت", "غمگین", "دلتنگ", "متاسف", "متأسف", "حس بد", "اشک", "گریه", "sad", "crying"]
_RE_DOUBT = ["مطمئنی", "واقعا", "جدی", "چی میگی", "really", "sure", "wtf"]
_RE_GREET = ["سلام", "درود", "صبح بخیر", "عصر بخیر", "شب بخیر", "وقت بخیر", "hi", "hello", "hey"]
_RE_PRAISE = ["عالی", "فوق العاده", "فوق‌العاده", "ایول", "بهترین", "great", "awesome", "perfect", "amazing"]


def pick_reaction(text: str) -> str:
    """Choose a reaction emoji by analysing the user's message."""
    low = (text or "").lower()

    def has(words: list[str]) -> bool:
        return any(word in low for word in words)

    if has(_RE_THANKS) or has(_RE_LOVE):
        return "❤️"
    if has(_RE_FUN):
        return "🤣"
    if has(_RE_SAD):
        return "😢"
    if has(_RE_DOUBT):
        return "🤨"
    if has(_RE_GREET):
        return "🥰"
    if "؟" in (text or "") or "?" in low:
        return "🧐"
    if has(_RE_PRAISE):
        return "🔥"
    return "👍"
