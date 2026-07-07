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
import sys
from PIL import Image, ImageOps

CANVAS = 900          # output is CANVAS x CANVAS
FACE_ZOOM = 2.4       # crop side = face height * FACE_ZOOM

try:
    import cv2
    import numpy as np
    _CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except (ImportError, AttributeError):   # AttributeError: opencv>=5 dropped Haar
    cv2 = None


def _find_face(img: Image.Image):
    """Return (cx, cy, face_h) of the largest face, or None."""
    if cv2 is None:
        return None
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                      minSize=(gray.shape[1] // 10,) * 2)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return x + w / 2, y + h / 2, h


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
        top = int(cy - side * 0.46)   # face slightly above crop center
    else:
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
