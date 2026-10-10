"""Draw the app icon and write it as an .icns.

The icon is drawn with Pillow, which the app already depends on, rather than
kept as a binary in the repository: the source of the artwork is then the code
below, and nothing has to be redrawn by hand to change it.

`iconutil` ships with macOS and turns the iconset into the .icns the bundle
wants. It is the only part of this file that is macOS only.
"""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

# The sizes an .icns is expected to carry, each at 1x and 2x.
ICONSET_SIZES = (16, 32, 128, 256, 512)

BACKGROUND = ((44, 110, 235), (88, 62, 214))  # top and bottom of the gradient
PAGE = (255, 255, 255)
PAGE_EDGE = (214, 222, 242)
FOLD = (198, 210, 240)
MARK = (44, 110, 235)

SIZE = 1024  # everything is drawn here and scaled down


def draw(size: int = SIZE) -> Image.Image:
    """Draw the icon: a rounded square, a page with a folded corner, an arrow."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)

    _rounded_gradient(image, radius=int(size * 0.225))

    # A page, slightly left of centre, with the top right corner folded over.
    left, top, right, bottom = size * 0.28, size * 0.2, size * 0.72, size * 0.8
    fold = size * 0.14
    canvas.polygon(
        [
            (left, top), (right - fold, top), (right, top + fold),
            (right, bottom), (left, bottom),
        ],
        fill=PAGE,
        outline=PAGE_EDGE,
        width=max(1, int(size * 0.006)),
    )
    canvas.polygon(
        [(right - fold, top), (right, top + fold), (right - fold, top + fold)],
        fill=FOLD,
    )

    # A downward arrow across the page: the file becomes another file.
    middle = (left + right) / 2
    stem = size * 0.035
    head = size * 0.085
    canvas.rectangle(
        [middle - stem / 2, top + size * 0.17, middle + stem / 2, bottom - size * 0.21],
        fill=MARK,
    )
    canvas.polygon(
        [
            (middle - head, bottom - size * 0.22),
            (middle + head, bottom - size * 0.22),
            (middle, bottom - size * 0.09),
        ],
        fill=MARK,
    )
    return image


def _rounded_gradient(image: Image.Image, radius: int) -> None:
    """Paint a vertical gradient clipped to a rounded square."""
    size = image.width
    gradient = Image.new("RGBA", (1, size))
    top, bottom = BACKGROUND
    for y in range(size):
        blend = y / max(1, size - 1)
        gradient.putpixel(
            (0, y),
            tuple(round(top[c] + (bottom[c] - top[c]) * blend) for c in range(3)) + (255,),
        )
    gradient = gradient.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    # Inset by a hair so the rounded edge stays smooth once it is scaled down.
    inset = size * 0.02
    ImageDraw.Draw(mask).rounded_rectangle(
        [inset, inset, size - inset, size - inset], radius=radius, fill=255
    )
    image.paste(gradient, (0, 0), mask)


def write_iconset(directory: Path, size: int = SIZE) -> Path:
    """Write the icon at every size an .icns needs. Returns the .iconset path."""
    iconset = directory / "FileTool.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    art = draw(size)
    for edge in ICONSET_SIZES:
        for scale in (1, 2):
            pixels = edge * scale
            suffix = "" if scale == 1 else "@2x"
            art.resize((pixels, pixels), Image.LANCZOS).save(
                iconset / f"icon_{edge}x{edge}{suffix}.png"
            )
    return iconset


def build_icns(directory: Path) -> Path:
    """Draw the icon and convert it to an .icns with macOS's own iconutil."""
    iconset = write_iconset(directory)
    icns = directory / "FileTool.icns"
    subprocess.run(
        ["iconutil", "--convert", "icns", str(iconset), "--output", str(icns)],
        check=True,
        capture_output=True,
    )
    return icns
