# Original code supplied by the author on 2026-10-24.
# Uses PyMuPDF (AGPL/commercial) and Gemma 3's separate model terms.
import io

import fitz  # PyMuPDF for PDFs
import ollama
from PIL import Image


def convert_pdf_to_images(pdf_path):
    images = []
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        images.append(img_buffer.getvalue())
    return images


prompt = "Extract all readable text from these images and format it as structured Markdown."


def query_llm_with_images(image_bytes_list, model="gemma3:12b", prompt=prompt):
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt, "images": image_bytes_list}],
    )
    return response["message"]["content"]


if __name__ == "__main__":
    images = convert_pdf_to_images("mypdf.pdf")
    if images:
        print(f"Converted {len(images)} pages to images.")
        extracted_text = query_llm_with_images(images)
        with open("output.md", "w", encoding="utf-8") as md_file:
            md_file.write(extracted_text)
        print("\nMarkdown Conversion Complete! Check `output.md`.")
    else:
        print("No images found in the PDF.")
