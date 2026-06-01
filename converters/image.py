"""Image to ASCII converter"""
from PIL import Image
import io
import base64
import numpy as np

# ASCII characters from light to dark
ASCII_CHARS = " .:-=+*#%@"

def image_to_ascii_base64(image_data, max_width=120, max_height=None):
    """
    Convert base64 image to ASCII art.
    image_data: base64 string (with or without data URI prefix)
    returns: base64 of ASCII art image
    """
    # Remove data URI prefix if present
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    img_bytes = base64.b64decode(image_data)
    img = Image.open(io.BytesIO(img_bytes)).convert("L")

    w, h = img.size
    aspect = h / w

    # Calculate new size
    new_w = min(max_width, w)
    new_h = int(new_w * aspect * 0.5)  # 0.5 for character height ratio

    if max_height:
        new_h = min(new_h, max_height)

    img = img.resize((new_w, new_h))
    pixels = np.array(img)

    # Map pixels to ASCII chars
    rows = []
    for row in pixels:
        line = "".join(ASCII_CHARS[min(int(p / 25.5), len(ASCII_CHARS) - 1)] for p in row)
        rows.append(line)

    ascii_str = "\n".join(rows)

    # Convert ASCII string to image
    char_w, char_h = 8, 16
    out_w = new_w * char_w
    out_h = new_h * char_h

    out_img = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    from PIL import ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    except:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(out_img)
    draw.text((0, 0), ascii_str, fill=(0, 255, 65), font=font)

    buf = io.BytesIO()
    out_img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def image_to_ascii_text(image_data, max_width=80):
    """
    Convert base64 image to ASCII text (plain characters).
    Returns the ASCII string directly.
    """
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    img_bytes = base64.b64decode(image_data)
    img = Image.open(io.BytesIO(img_bytes)).convert("L")

    w, h = img.size
    aspect = h / w
    new_w = min(max_width, w)
    new_h = int(new_w * aspect * 0.5)

    img = img.resize((new_w, new_h))
    pixels = np.array(img)

    rows = []
    for row in pixels:
        line = "".join(ASCII_CHARS[min(int(p / 25.5), len(ASCII_CHARS) - 1)] for p in row)
        rows.append(line)

    return "\n".join(rows)