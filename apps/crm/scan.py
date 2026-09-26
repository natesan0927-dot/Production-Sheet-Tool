"""Turning a handful of photographed pages into one PDF.

Measurement sheets are written on paper at site. Phones photograph them
readily and attach them badly: five separate JPEGs, sideways, named
IMG_20260926_114233.jpg. This takes the photos, straightens what the camera
recorded, and returns a single named PDF so the job's folder holds one
document per sheet rather than a pile of pictures.

The conversion runs on the server rather than in the browser: the phones this
is used on are whatever staff already own, and Pillow is already a dependency.
"""

from io import BytesIO

from PIL import Image, ImageOps

# Comfortably past what a sheet of paper needs, and small enough that a job's
# folder does not fill with 12 MP originals.
MAX_EDGE = 2200
JPEG_QUALITY = 80
MAX_PAGES = 30


class ScanError(Exception):
    """Something about the pictures, said in words the office can act on."""


def _page(uploaded):
    image = Image.open(uploaded)
    # Phones record orientation in EXIF rather than in the pixels, so a page
    # shot in portrait arrives on its side unless this is applied.
    image = ImageOps.exif_transpose(image)

    if image.mode in ("RGBA", "LA", "P"):
        # A PNG with transparency flattens to black without a white page under it.
        backdrop = Image.new("RGB", image.size, (255, 255, 255))
        converted = image.convert("RGBA")
        backdrop.paste(converted, mask=converted.split()[-1])
        image = backdrop
    elif image.mode != "RGB":
        image = image.convert("RGB")

    if max(image.size) > MAX_EDGE:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    return image


def pages_to_pdf(uploads):
    """Merge the uploaded images, in the order given, into one PDF's bytes."""
    if not uploads:
        raise ScanError("Add at least one page before making the PDF.")
    if len(uploads) > MAX_PAGES:
        raise ScanError(f"That is {len(uploads)} pages. Scan up to {MAX_PAGES} at a time.")

    pages = []
    for index, uploaded in enumerate(uploads, start=1):
        try:
            pages.append(_page(uploaded))
        except ScanError:
            raise
        except Exception:
            name = getattr(uploaded, "name", f"page {index}")
            raise ScanError(f"{name} could not be read as a picture. Scan that page again.")

    output = BytesIO()
    first, rest = pages[0], pages[1:]
    first.save(output, format="PDF", save_all=True, append_images=rest, quality=JPEG_QUALITY)
    return output.getvalue()


def pdf_filename(name, fallback="Scan"):
    """The name typed in the box, made safe to store and still readable."""
    cleaned = "".join(character if (character.isalnum() or character in " -_") else " " for character in (name or ""))
    cleaned = " ".join(cleaned.split())[:80]
    return f"{cleaned or fallback}.pdf"
