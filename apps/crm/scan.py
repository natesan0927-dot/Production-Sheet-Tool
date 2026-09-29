"""Turning a handful of photographed pages into one PDF.

Measurement sheets are written on paper at site. Phones photograph them
readily and attach them badly: five separate JPEGs, sideways, named
IMG_20260926_114233.jpg. This takes the photos, straightens what the camera
recorded, and returns a single named PDF so the job's folder holds one
document per sheet rather than a pile of pictures.

The conversion runs on the server rather than in the browser: the phones this
is used on are whatever staff already own, and Pillow is already a dependency.

Memory is the constraint here, not speed. A free host has 512 MB for the whole
site, and a 12-megapixel photo is 36 MB once decoded. Holding thirty of them at
once took over 500 MB and would have killed the server mid-scan, taking every
signed-in person's session with it. So each page is decoded, shrunk, squeezed
back into a small JPEG and let go of before the next one is opened; the PDF is
then assembled from those small JPEGs without decoding them again.
"""

import os
import tempfile
import unicodedata
from io import BytesIO

from PIL import Image, ImageOps
from reportlab.pdfgen import canvas

# Comfortably past what a sheet of paper needs, and small enough that a job's
# folder does not fill with 12 MP originals.
MAX_EDGE = 2200
JPEG_QUALITY = 78
MAX_PAGES = 30
# Printed size of a page's long edge, in PDF points (A4's long edge is 842).
PAGE_LONG_EDGE = 842


class ScanError(Exception):
    """Something about the pictures, said in words the office can act on."""


def _compressed_page(uploaded):
    """One photograph as (small JPEG bytes, width, height). Nothing else is kept."""
    with Image.open(uploaded) as image:
        if image.format == "JPEG":
            # Let the decoder produce a smaller picture directly when the photo
            # is far bigger than needed, instead of decoding all of it first.
            longest = max(image.size)
            if longest > MAX_EDGE * 2:
                ratio = MAX_EDGE / longest
                image.draft("RGB", (int(image.width * ratio) + 1, int(image.height * ratio) + 1))

        if image.mode in ("RGBA", "LA", "P"):
            # A PNG with transparency flattens to black without a white page under it.
            converted = image.convert("RGBA")
            image = Image.new("RGB", converted.size, (255, 255, 255))
            image.paste(converted, mask=converted.split()[-1])
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Shrink first, then straighten. Straightening makes a whole new copy of
        # the picture, and a 12-megapixel photo is 36 MB — the small one is 11.
        if max(image.size) > MAX_EDGE:
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

        # Phones record orientation in EXIF rather than in the pixels, so a page
        # shot in portrait arrives on its side unless this is applied.
        upright = ImageOps.exif_transpose(image)

        buffer = BytesIO()
        upright.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue(), upright.width, upright.height


def pages_to_pdf(uploads):
    """Merge the uploaded images, in the order given, into one PDF's bytes."""
    if not uploads:
        raise ScanError("Add at least one page before making the PDF.")
    if len(uploads) > MAX_PAGES:
        raise ScanError(f"That is {len(uploads)} pages. Scan up to {MAX_PAGES} at a time.")

    output = BytesIO()
    pdf = canvas.Canvas(output, pageCompression=1)

    # reportlab copies a JPEG into the PDF untouched only when it is handed a
    # file path. Handed the same picture from memory it decodes it and stores raw
    # pixels instead — many times the size, and back to holding every page's
    # pixels at once. So each small JPEG goes to a scratch folder for the
    # moment it takes to build the PDF.
    with tempfile.TemporaryDirectory() as scratch:
        for index, uploaded in enumerate(uploads, start=1):
            try:
                data, width, height = _compressed_page(uploaded)
            except Exception:
                name = getattr(uploaded, "name", f"page {index}")
                raise ScanError(f"{name} could not be read as a picture. Scan that page again.")

            path = os.path.join(scratch, f"page{index:03d}.jpg")
            with open(path, "wb") as handle:
                handle.write(data)

            # Each page takes the shape of its photograph, long edge at A4 length.
            scale = PAGE_LONG_EDGE / max(width, height)
            page_width, page_height = width * scale, height * scale
            pdf.setPageSize((page_width, page_height))
            pdf.drawImage(path, 0, 0, page_width, page_height)
            pdf.showPage()

        pdf.save()
    return output.getvalue()


def name_character(character):
    """A letter, a digit, or one of the vowel marks Indian scripts join to their letters."""
    return unicodedata.category(character)[0] in "LNM"


def pdf_filename(name, fallback="Scan"):
    """The name typed in the box, made safe to store and still readable."""
    cleaned = "".join(character if (name_character(character) or character in " -_") else " " for character in (name or ""))
    cleaned = " ".join(cleaned.split())[:80]
    return f"{cleaned or fallback}.pdf"
