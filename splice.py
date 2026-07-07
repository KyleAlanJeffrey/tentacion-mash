"""splice.py — make the half-and-half edit.

Left half:  XXXTentacion (fixed base image)
Right half: the newly deceased person

Cropping is face-aware when opencv-python is installed (setup.sh installs it):
the square crop is centered on the detected face, so the seam splits both
faces down the middle and they sit at matching scale. Falls back to a
top-biased geometric crop if no face is found.

Usage:
    python splice.py path/to/right_portrait.jpg output.jpg
Or import: make_splice(left_path, right_path, out_path)
"""
import os
import sys
import urllib.request
from PIL import Image, ImageOps

CANVAS = 900          # output is CANVAS x CANVAS

# Tunable via env, e.g.:  SPLICE_ZOOM=2.0 SPLICE_VOFFSET=0.5 ./run.sh regen
FACE_ZOOM = float(os.environ.get("SPLICE_ZOOM", 2.4))     # crop side = face height * this
FACE_VOFFSET = float(os.environ.get("SPLICE_VOFFSET", 0.46))  # face center at this fraction from crop top

_DIR = os.path.dirname(os.path.abspath(__file__))
_YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
              "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_YUNET_PATH = os.path.join(_DIR, "assets", "yunet.onnx")
_yunet = None  # None = not tried, False = unavailable

try:
    import cv2
    import numpy as np
    try:
        _CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except AttributeError:              # opencv>=5 dropped Haar
        _CASCADE = None
except ImportError:
    cv2 = None
    _CASCADE = None


def _get_yunet():
    """YuNet DNN face detector — handles tilted, occluded, tattooed,
    profile-ish faces that defeat the old Haar cascade. Model (~350 KB)
    is downloaded once into assets/."""
    global _yunet
    if _yunet is None:
        _yunet = False
        if cv2 is not None and hasattr(cv2, "FaceDetectorYN"):
            try:
                if not os.path.exists(_YUNET_PATH):
                    os.makedirs(os.path.dirname(_YUNET_PATH), exist_ok=True)
                    urllib.request.urlretrieve(_YUNET_URL, _YUNET_PATH)
                _yunet = cv2.FaceDetectorYN.create(_YUNET_PATH, "", (320, 320), 0.6)
            except Exception as e:
                print(f"  (yunet unavailable: {e} — using haar fallback)")
    return _yunet or None


def _detect(img: Image.Image):
    """Largest face -> (cx, cy, face_h, frontality 0..1) or None.
    Frontality uses YuNet's eye/nose landmarks: a head-on face has the nose
    centered between the eyes and level eyes; yaw/roll push the score to 0."""
    if cv2 is None:
        return None
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]

    det = _get_yunet()
    if det is not None:
        scale = min(1.0, 1200 / max(w, h))   # downscale huge images for speed
        small = cv2.resize(bgr, (round(w * scale), round(h * scale)))
        det.setInputSize((small.shape[1], small.shape[0]))
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            f = max(faces, key=lambda r: r[2] * r[3]) / scale
            x, y, fw, fh, rex, rey, lex, ley, nx, ny = f[:10]
            eye_d = ((rex - lex) ** 2 + (rey - ley) ** 2) ** 0.5 or 1.0
            yaw = abs(nx - (rex + lex) / 2) / eye_d    # nose off eye-midpoint
            roll = abs(rey - ley) / eye_d              # eyes not level
            frontality = max(0.0, 1.0 - 2.0 * yaw - roll)
            return x + fw / 2, y + fh / 2, fh, frontality

    if _CASCADE is not None:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                          minSize=(w // 10,) * 2)
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            return x + fw / 2, y + fh / 2, fh, 0.6  # haar only fires ~frontal
    return None


def _find_face(img: Image.Image):
    d = _detect(img)
    return d[:3] if d else None


def assess_portrait(path: str) -> float:
    """How suitable is this image as a splice half? 0 = unusable.
    Wants a face that is frontal (flat, head-on) and reasonably large."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    d = _detect(img)
    if d is None:
        return 0.0
    cx, cy, fh, frontality = d
    if frontality < 0.5:          # too far from head-on
        return 0.0
    rel = min(fh / img.size[1], 0.5)   # face height relative to image
    return frontality * rel


def _face_crop(img: Image.Image, size: int) -> Image.Image:
    """Square-crop centered on the face when one is found; otherwise biased
    toward the top, where the face usually sits in an encyclopedia portrait."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size

    face = _find_face(img)
    if face:
        cx, cy, fh = face
        side = min(int(fh * FACE_ZOOM), w, h)
        left = int(cx - side / 2)
        top = int(cy - side * FACE_VOFFSET)   # face slightly above crop center
    else:
        if cv2 is not None:
            print("  (no face detected — using geometric crop)")
        side = min(w, h)
        left = (w - side) // 2
        top = min(int(h * 0.08), h - side)

    left = max(0, min(left, w - side))
    top = max(0, min(top, h - side))
    img = img.crop((left, top, left + side, top + side))
    return img.resize((size, size), Image.LANCZOS)


def make_splice(left_path: str, right_path: str, out_path: str) -> str:
    left = _face_crop(Image.open(left_path), CANVAS)
    right = _face_crop(Image.open(right_path), CANVAS)
    half = CANVAS // 2

    canvas = Image.new("RGB", (CANVAS, CANVAS))
    canvas.paste(left.crop((0, 0, half, CANVAS)), (0, 0))
    canvas.paste(right.crop((half, 0, CANVAS, CANVAS)), (half, 0))

    # hairline seam like the classic edits
    for x in (half - 1, half):
        for y in range(CANVAS):
            r, g, b = canvas.getpixel((x, y))
            canvas.putpixel((x, y), (int(r * 0.85), int(g * 0.85), int(b * 0.85)))

    canvas.save(out_path, quality=90)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python splice.py <right_portrait> <output.jpg>  "
                 "(left half is assets/xxx.jpg)")
    make_splice("assets/xxx.jpg", sys.argv[1], sys.argv[2])
    print("wrote", sys.argv[2])
