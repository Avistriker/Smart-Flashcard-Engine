"""
PDF text and image extraction using PyMuPDF (fitz).
Extracts text per page and saves embedded images to static/images/cards/.
"""

import os
import uuid
import fitz  # PyMuPDF


def extract_from_pdf(pdf_path, image_output_dir='static/images/cards'):
    """
    Extract text and images from a PDF file.

    Returns:
        dict: {
            "text": str (full text),
            "images": [{"page": int, "path": str (relative to static)}]
        }
    """
    os.makedirs(image_output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    full_text = ""
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Extract text
        page_text = page.get_text()
        if page_text.strip():
            full_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

        # Extract images
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # Save image with unique name
                image_filename = f"{uuid.uuid4().hex}.{image_ext}"
                image_path = os.path.join(image_output_dir, image_filename)
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)

                # Store relative path for web serving
                relative_path = f"/static/images/cards/{image_filename}"
                images.append({
                    "page": page_num + 1,
                    "path": relative_path,
                    "filename": image_filename
                })
            except Exception as e:
                print(f"Warning: Could not extract image {img_index} from page {page_num + 1}: {e}")
                continue

    doc.close()

    return {
        "text": full_text.strip(),
        "images": images
    }
