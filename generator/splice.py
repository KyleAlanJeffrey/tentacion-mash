"""splice.py — make the half-and-half edit.

Left half:  XXXTentacion (fixed base image, generator/assets/xxx.jpg)
Right half: the newly deceased person

Both portraits are ALIGNED before splicing: a similarity transform (rotate +
scale + translate) places the eye line of each face at the same height, with
the same inter-eye distance, and the midpoint between the eyes exactly on the
seam. Eyes, nose line and chin therefore match across the two halves.

Eye positions come from the YuNet face detector. If detection is wrong or
fails (heavy tattoos, odd lighting), mark the eyes yourself:

    python generator/splice.py --mark generator/assets/xxx.jpg

writes xxx.jpg.marked.jpg showing the detected eyes, and prints a sidecar
template. Save corrected pixel coords as generator/assets/xxx.jpg.json:

    {"eyes": [[x1, y1], [x2, y2]]}

A sidecar always beats detection.

Usage:
    python splice.py <right_portrait> <output.jpg>
    python splice.py --mark <image>
Or import: make_splice(left_path, right_path, out_path)
"""
import json
import math
import os
import sys
import urllib.request
from PIL import Image, ImageOps

CANVAS = 900          # output is CANVAS x CANVAS

# Alignment targets, tunable via env, e.g.  SPLICE_EYELINE=0.42 ./run.sh regen
EYE_LINE = float(os.environ.get("SPLICE_EYELINE", 0.40))  # eye line, fraction of canvas height
EYE_DIST = float(os.environ.get("SPLICE_EYEDIST", 0.17))  # inter-eye dist, fraction of canvas width

# Fallback geometric crop (only when no eyes are found anywhere)
FACE_ZOOM = float(os.environ.get("SPLICE_ZOOM", 2.4))
FACE_VOFFSET = float(os.environ.get("SPLICE_VOFFSET", 0.46))

# Canonical 5-point face template (ArcFace proportions, 112x112 space).
# Order matches YuNet: subject-right eye, subject-left eye, nose tip,
# right mouth corner, left mouth corner. Aligning every face to these fixed
# proportions is what makes the eyes, nose, mouth, chin AND head size line up
# across the seam — not just the eyes.
_ARCFACE = [
    (38.2946, 51.6963),
    (73.5318, 51.5014),
    (56.0252, 71.7366),
    (41.5493, 92.3655),
    (70.7299, 92.2041),
]

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


_TEMPLATE = None  # cached canonical 5-point template in canvas coords


def _similarity(src, dst):
    """Least-squares similarity transform (uniform scale + rotation +
    translation, no shear/reflection) mapping src points onto dst points.
    Umeyama 1991 — the standard for landmark-based face alignment. Works with
    2 points (exact) or 5 (over-determined -> best fit). Returns a 2x3 matrix."""
    src = np.asarray(src, np.float64)
    dst = np.asarray(dst, np.float64)
    n = src.shape[0]
    src_mean, dst_mean = src.mean(0), dst.mean(0)
    sc, dc = src - src_mean, dst - dst_mean
    cov = (dc.T @ sc) / n
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[1, 1] = -1                       # forbid reflections
    R = U @ D @ Vt
    var = (sc ** 2).sum() / n
    scale = float((S * np.diag(D)).sum() / var) if var else 1.0
    M = np.zeros((2, 3))
    M[:2, :2] = scale * R
    M[:2, 2] = dst_mean - scale * R @ src_mean
    return M


def _template():
    """The 5-point template placed into the output canvas: eye midpoint on
    EYE_LINE, inter-eye = EYE_DIST, nose/mouth/chin following ArcFace ratios."""
    global _TEMPLATE
    if _TEMPLATE is None:
        eye_targets = [
            (CANVAS / 2 - EYE_DIST * CANVAS / 2, EYE_LINE * CANVAS),
            (CANVAS / 2 + EYE_DIST * CANVAS / 2, EYE_LINE * CANVAS),
        ]
        # scale/place the whole ArcFace template by its two eye points
        M = _similarity(_ARCFACE[:2], eye_targets)
        arc = np.array(_ARCFACE, np.float64)
        _TEMPLATE = arc @ M[:, :2].T + M[:, 2]
    return _TEMPLATE


def _get_yunet():
    """YuNet DNN face detector — handles tilted, occluded, tattooed faces
    that defeat the old Haar cascade. Model (~350 KB) downloaded once."""
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
    """Largest face -> dict(cx, cy, fh, front, eyes) or None.
    eyes = ((x, y), (x, y)) from YuNet landmarks; None when only Haar fired.
    front (0..1): how head-on the face is — nose centered between level eyes."""
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
            x, y, fw, fh = f[:4]
            rex, rey, lex, ley, nx, ny, rmx, rmy, lmx, lmy = f[4:14]
            eye_d = math.hypot(rex - lex, rey - ley) or 1.0
            yaw = abs(nx - (rex + lex) / 2) / eye_d
            roll = abs(rey - ley) / eye_d
            return {
                "cx": x + fw / 2, "cy": y + fh / 2, "fh": fh,
                "front": max(0.0, 1.0 - 2.0 * yaw - roll),
                "eyes": ((rex, rey), (lex, ley)),
                # full 5-point landmark set for similarity alignment
                "lmarks": ((rex, rey), (lex, ley), (nx, ny),
                           (rmx, rmy), (lmx, lmy)),
            }

    if _CASCADE is not None:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                          minSize=(w // 10,) * 2)
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            return {"cx": x + fw / 2, "cy": y + fh / 2, "fh": fh,
                    "front": 0.6, "eyes": None}  # haar only fires ~frontal
    return None


def _find_face(img: Image.Image):
    d = _detect(img)
    return (d["cx"], d["cy"], d["fh"]) if d else None


def _colorfulness(img: Image.Image) -> float:
    """Hasler-Süsstrunk colorfulness, 0..~100. B&W photos and faded paintings
    score near 0 and splice poorly against XXX's color half."""
    if cv2 is None:
        return 40.0
    a = np.asarray(img.resize((64, 64)), dtype=np.float32)
    rg = a[..., 0] - a[..., 1]
    yb = (a[..., 0] + a[..., 1]) / 2 - a[..., 2]
    return float(math.hypot(rg.std(), yb.std()) +
                 0.3 * math.hypot(abs(rg.mean()), abs(yb.mean())))


def assess_portrait(path: str) -> float:
    """How suitable is this image as a splice half? 0 = unusable.
    Wants a face that is frontal (flat, head-on), reasonably large,
    and in color."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    d = _detect(img)
    if d is None or d["front"] < 0.5:
        return 0.0
    color = 0.7 + 0.3 * min(1.0, _colorfulness(img) / 40.0)
    return d["front"] * min(d["fh"] / img.size[1], 0.5) * color


def sidecar_landmarks(path: str):
    """Manual landmarks from '<image>.json' — overrides detection. Accepts
    either the full 5-point set (best) or just the eyes:

        {"landmarks": [[rex,rey],[lex,ley],[nx,ny],[rmx,rmy],[lmx,lmy]]}
        {"eyes": [[x1,y1],[x2,y2]]}
    """
    sc = path + ".json"
    if not os.path.exists(sc):
        return None
    with open(sc) as f:
        data = json.load(f)
    pts = data.get("landmarks") or data.get("eyes")
    return tuple((p[0], p[1]) for p in pts) if pts else None


def _face_crop(img: Image.Image, size: int) -> Image.Image:
    """Fallback: square crop around the face box (or top-center of image)."""
    w, h = img.size
    face = _find_face(img)
    if face:
        cx, cy, fh = face
        side = min(int(fh * FACE_ZOOM), w, h)
        left = int(cx - side / 2)
        top = int(cy - side * FACE_VOFFSET)
    else:
        if cv2 is not None:
            print("  (no face detected — using geometric crop)")
        side = min(w, h)
        left = (w - side) // 2
        top = min(int(h * 0.08), h - side)

    left = max(0, min(left, w - side))
    top = max(0, min(top, h - side))
    return img.crop((left, top, left + side, top + side)).resize(
        (size, size), Image.LANCZOS)


def _align(img: Image.Image, manual=None) -> Image.Image:
    """Similarity-warp the face onto the canonical 5-point template so eyes,
    nose, mouth, chin and head size all land in the same place — the whole
    face is zoomed/rotated to fit, not just the eye line. Prefers the full
    5-point landmark set; falls back to eyes only, then a geometric crop."""
    img = ImageOps.exif_transpose(img).convert("RGB")

    lmarks = eyes = None
    if manual is not None:
        if len(manual) >= 5:
            lmarks = manual
        else:
            eyes = manual
    else:
        d = _detect(img)
        if d:
            lmarks, eyes = d.get("lmarks"), d["eyes"]

    if cv2 is None:
        return _face_crop(img, CANVAS)

    if lmarks is not None:
        M = _similarity(lmarks, _template())          # full-face fit
    elif eyes is not None:
        (x1, y1), (x2, y2) = sorted(eyes, key=lambda p: p[0])
        if math.hypot(x2 - x1, y2 - y1) < 8:
            return _face_crop(img, CANVAS)
        M = _similarity(((x1, y1), (x2, y2)), _template()[:2])  # eyes only
    else:
        print("  (no landmarks — geometric crop; see splice.py --mark)")
        return _face_crop(img, CANVAS)

    arr = cv2.warpAffine(np.array(img), M, (CANVAS, CANVAS),
                         flags=cv2.INTER_LANCZOS4,
                         borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(arr)


def make_splice(left_path: str, right_path: str, out_path: str) -> str:
    left = _align(Image.open(left_path), sidecar_landmarks(left_path))
    right = _align(Image.open(right_path), sidecar_landmarks(right_path))
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


def mark(path: str):
    """Debug helper: draw the detected eyes/face on a copy of the image and
    print a sidecar template for manual correction."""
    from PIL import ImageDraw
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    d = _detect(img)
    out = path + ".marked.jpg"
    dr = ImageDraw.Draw(img)
    if d is None:
        print(f"no face detected in {path}")
        print('create a sidecar by hand:  echo \'{"eyes": [[x1, y1], [x2, y2]]}\''
              f' > {path}.json')
        return
    r = max(3, int(d["fh"] * 0.04))
    lmarks = d.get("lmarks")
    if lmarks:
        # eyes red, nose green, mouth corners blue
        colors = [(255, 0, 0), (255, 0, 0), (0, 220, 0), (0, 160, 255), (0, 160, 255)]
        for (x, y), c in zip(lmarks, colors):
            dr.ellipse((x - r, y - r, x + r, y + r), outline=c, width=3)
    dr.rectangle((d["cx"] - d["fh"] / 2, d["cy"] - d["fh"] / 2,
                  d["cx"] + d["fh"] / 2, d["cy"] + d["fh"] / 2),
                 outline=(255, 200, 0), width=2)
    img.save(out, quality=92)
    print(f"marked -> {out}")
    if lmarks:
        pts = [[round(x), round(y)] for x, y in lmarks]
        print(f"detected landmarks (rEye,lEye,nose,rMouth,lMouth): {pts}")
        print(f"if wrong, correct and save as {path}.json:")
        print(json.dumps({"landmarks": pts}))
    else:
        print(f"no landmarks (haar) — mark manually and save {path}.json:")
        print('{"landmarks": [[rex,rey],[lex,ley],[nx,ny],[rmx,rmy],[lmx,lmy]]}')


if __name__ == "__main__":
    if "--mark" in sys.argv:
        mark(sys.argv[sys.argv.index("--mark") + 1])
    elif len(sys.argv) == 3:
        make_splice(os.path.join(_DIR, "assets", "xxx.jpg"),
                    sys.argv[1], sys.argv[2])
        print("wrote", sys.argv[2])
    else:
        sys.exit("usage: python splice.py <right_portrait> <output.jpg>\n"
                 "       python splice.py --mark <image>")
