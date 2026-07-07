"""splice.py — make the half-and-half edit.

Left half:  XXXTentacion (fixed base image)
Right half: the newly deceased person

Usage:
    python splice.py path/to/right_portrait.jpg output.jpg
Or import: make_splice(left_path, right_path, out_path)
"""
import sys
from PIL import Image, ImageOps

CANVAS = 900  # output is CANVAS x CANVAS


def _face_crop(img: Image.Image, size: int) -> Image.Image:
    """Square-crop biased toward the top of the image, where the face
    almost always sits in an encyclopedia portrait, then resize."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    # bias crop upward: take from 8% down rather than vertical center
    top = min(int(h * 0.08), h - side)
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
