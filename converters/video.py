"""Video/GIF to ASCII frame extractor"""
import cv2
import io
import base64
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ASCII_CHARS = " .:-=+*#%@"

def video_to_ascii_frames(video_data_base64, frame_count=30, max_width=100):
    """
    Extract frames from video/gif and convert to ASCII.
    Returns list of ASCII strings (frames).
    """
    # Remove data URI prefix
    if "," in video_data_base64:
        video_data_base64 = video_data_base64.split(",", 1)[1]

    video_bytes = base64.b64decode(video_data_base64)
    nparr = np.frombuffer(video_bytes, np.uint8)
    cap = cv2.VideoCapture(io.BytesIO(nparr.tobytes()) if hasattr(nparr, 'tobytes') else video_bytes)

    # Try with OpenCV directly
    try:
        import tempfile
        import os
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(video_bytes)
        tmp.close()
        cap = cv2.VideoCapture(tmp.path)
        os.unlink(tmp.name)
    except:
        pass

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        return []

    step = max(1, total_frames // frame_count)
    frames = []

    for i in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        aspect = h / w
        new_w = min(max_width, w)
        new_h = int(new_w * aspect * 0.5)

        resized = cv2.resize(gray, (new_w, new_h))

        rows = []
        for row in resized:
            line = "".join(ASCII_CHARS[min(int(p / 25.5), len(ASCII_CHARS) - 1)] for p in row)
            rows.append(line)

        frames.append("\n".join(rows))

    cap.release()
    return frames[:frame_count]

def gif_to_ascii_frames(gif_data_base64, frame_count=30, max_width=100):
    """Extract and convert GIF frames to ASCII"""
    if "," in gif_data_base64:
        gif_data_base64 = gif_data_base64.split(",", 1)[1]

    gif_bytes = base64.b64decode(gif_data_base64)
    img = Image.open(io.BytesIO(gif_bytes))

    frames = []
    try:
        total = getattr(img, "n_frames", 1)
        step = max(1, total // frame_count)

        for i in range(0, total, step):
            img.seek(i)
            f = img.convert("L")
            w, h = f.size
            aspect = h / w
            new_w = min(max_width, w)
            new_h = int(new_w * aspect * 0.5)
            f = f.resize((new_w, new_h))
            pixels = np.array(f)

            rows = []
            for row in pixels:
                line = "".join(ASCII_CHARS[min(int(p / 25.5), len(ASCII_CHARS) - 1)] for p in row)
                rows.append(line)

            frames.append("\n".join(rows))
    except EOFError:
        pass

    return frames[:frame_count]