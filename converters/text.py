"""Text to ASCII converter"""
import pyfiglet

def text_to_ascii(text, font="standard", width=80):
    """Convert text to ASCII art string"""
    try:
        result = pyfiglet.figlet_format(text, font=font, width=width)
        return result
    except Exception as e:
        # Fallback: simple block letters
        return fallback_ascii(text)

def fallback_ascii(text):
    """Simple fallback when figlet fails"""
    lines = []
    for char in text.upper():
        if char.isalpha():
            lines.append(char * 3)
        elif char.isdigit():
            lines.append(char * 3)
        else:
            lines.append(char)
    return "\n".join(lines)

FONTS = [
    "standard", "banner", "banner3", "banner3-D", "banner4",
    "big", "block", "bubble", "digital", "dot", "lean", "mini",
    "script", "shadow", "slant", "smshadow", "smslant", "standard",
    "term", "龟"  # ← wrong but kept for compatibility
]

def list_fonts():
    """Return available figlet fonts"""
    valid = [f for f in FONTS if f not in ("龟")]
    return valid