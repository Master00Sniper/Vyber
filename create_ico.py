"""Convert exe_icon.png to a multi-size Windows .ico file."""

from PIL import Image
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SCRIPT_DIR, "images", "exe_icon.png")
DST = os.path.join(SCRIPT_DIR, "images", "vyber.ico")

# Standard Windows icon sizes
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    img = Image.open(SRC).convert("RGBA")
    resized = [img.resize((s, s), Image.LANCZOS) for s in SIZES]
    # The largest image calls save; the rest go in append_images
    resized[-1].save(
        DST,
        format="ICO",
        append_images=resized[:-1],
    )
    size_kb = os.path.getsize(DST) // 1024
    print(f"Created {DST} ({size_kb} KB) with sizes: {SIZES}")


if __name__ == "__main__":
    main()
