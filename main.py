# main.py

import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os
import re
from shutil import which

# --- Configuration Section ---

# [Rule 1] BBOX coordinates for redaction on Page 1.
# Format: fitz.Rect(x0, y0, x1, y1)
# --- COORDINATES UPDATED BASED ON USER FEEDBACK (2025-11-16) ---
# These coordinates were carefully re-calibrated for higher accuracy.
PAGE_1_BBOXES = [
    # 1. Photo Area (Enlarged for full coverage)
    fitz.Rect(463, 53, 562, 184),
    
    # 2. Top Table Values (Adjusted to cover all three years)
    fitz.Rect(320, 120, 460, 178),  # Class (반) & Number (번호) Values
    fitz.Rect(470, 120, 555, 178),  # Homeroom Teacher (담임성명) Values
    
    # 3. Personal & Academic Info Table Values (Original coordinates were mostly correct)
    fitz.Rect(120, 205, 180, 220),  # Name (성명)
    fitz.Rect(280, 205, 320, 220),  # Gender (성별)
    fitz.Rect(430, 205, 550, 220),  # Resident Registration Number (주민등록번호)
    
    # Address & Academic Status (Fine-tuned for precision)
    fitz.Rect(120, 224, 555, 246),  # Address (주소)
    fitz.Rect(120, 249, 555, 286),  # Academic Status (학적사항)
    
    fitz.Rect(120, 290, 550, 310),  # Special Notes (특기사항)
]

# [Rule 2 & 3] Text patterns for redaction
SCHOOL_NAME_TEXT = "대성고등학교"
FOOTER_PII_KEYWORDS = ["반", "번호", "성명"]

# OCR confidence threshold
OCR_CONFIDENCE_THRESHOLD = 40
# Heuristic to determine if a PDF is scanned
SCANNED_PDF_TEXT_BLOCK_THRESHOLD = 10
# DPI for rendering PDF pages for OCR
OCR_DPI = 300

# --- Tesseract-OCR Availability Check ---

def is_tesseract_available():
    """Checks if the Tesseract-OCR executable is in the system's PATH."""
    return which("tesseract") is not None

TESSERACT_INSTALLED = is_tesseract_available()

# --- Redaction Logic Functions ---

def redact_page_by_coordinates(page):
    """[Rule 1] Applies fixed-coordinate redactions to a page."""
    for rect in PAGE_1_BBOXES:
        page.add_redact_annot(rect, fill=(1, 1, 1))

def redact_page_by_text_search(page):
    """[Rule 2] Searches for and redacts specific text strings."""
    redaction_count = 0
    # 1. Redact the specific high school name
    sensitive_areas = page.search_for(SCHOOL_NAME_TEXT)
    redaction_count += len(sensitive_areas)
    for area in sensitive_areas:
        page.add_redact_annot(area, fill=(1, 1, 1))

    # 2. Redact the footer PII block
    footer_rects = []
    for keyword in FOOTER_PII_KEYWORDS:
        footer_rects.extend(page.search_for(keyword))
    
    if footer_rects:
        combined_rect = fitz.Rect(footer_rects[0].tl, footer_rects[0].br)
        for rect in footer_rects[1:]:
            combined_rect.include_rect(rect)
        
        if combined_rect.y0 > 750: # Only apply to footer region
            combined_rect.x1 += 100 
            page.add_redact_annot(combined_rect, fill=(1, 1, 1))
            redaction_count += 1
            
    return redaction_count

def redact_page_by_ocr(page):
    """[Rule 3] Performs OCR and redacts text found in the resulting image data."""
    if not TESSERACT_INSTALLED:
        st.warning("Tesseract-OCR is not installed or not in PATH. OCR-based redaction is disabled.", icon="⚠️")
        return

    pix = page.get_pixmap(dpi=OCR_DPI)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    try:
        ocr_data = pytesseract.image_to_data(
            img, lang='kor', output_type=Output.DICT
        )
    except pytesseract.TesseractError as e:
        st.error(f"Tesseract OCR Error: {e}. Please ensure Tesseract is installed with the Korean language pack.", icon="🚨")
        return

    num_boxes = len(ocr_data['level'])
    redaction_rects = []

    for i in range(num_boxes):
        text = ocr_data['text'][i]
        conf = int(ocr_data['conf'][i])

        if conf < OCR_CONFIDENCE_THRESHOLD or not text.strip():
            continue
        
        if SCHOOL_NAME_TEXT in text:
            (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
            bbox = fitz.Rect(x, y, x + w, y + h) / (OCR_DPI / 72)
            redaction_rects.append(bbox)

        if any(keyword in text for keyword in FOOTER_PII_KEYWORDS):
             (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
             bbox = fitz.Rect(x, y, x + w, y + h) / (OCR_DPI / 72)
             if bbox.y0 > 750:
                if i + 1 < num_boxes and ocr_data['line_num'][i] == ocr_data['line_num'][i+1]:
                    (x2, y2, w2, h2) = (ocr_data['left'][i+1], ocr_data['top'][i+1], ocr_data['width'][i+1], ocr_data['height'][i+1])
                    bbox2 = fitz.Rect(x2, y2, x2 + w2, y2 + h2) / (OCR_DPI / 72)
                    bbox.include_rect(bbox2)
                redaction_rects.append(bbox)

    for rect in redaction_rects:
        page.add_redact_annot(rect, fill=(1, 1, 1))


# --- Main Streamlit Application ---

def main():
    st.set_page_config(
        page_title="PDF Personal Info Redactor",
        page_icon="🔒",
        layout="centered"
    )

    st.title("🔒 PDF Personal Information Redactor")
    st.markdown("""
        Upload a Korean school record PDF to automatically redact sensitive personal information.
        This tool uses a hybrid approach:
        1.  **Fixed Coordinates**: For known fields on Page 1.
        2.  **Text Search**: For digital PDFs.
        3.  **OCR (Tesseract)**: For scanned (image-based) PDFs.
    """)

    if not TESSERACT_INSTALLED:
        st.error("**OCR functionality unavailable.** Tesseract-OCR engine not found in your system's PATH. The application will proceed with fixed-coordinate and text-search redaction only.", icon="🚨")


    uploaded_file = st.file_uploader(
        "Choose a PDF file (up to 23 pages)",
        type="pdf",
        accept_multiple_files=False
    )

    if uploaded_file is not None:
        try:
            pdf_bytes = uploaded_file.getvalue()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            is_likely_scanned = True

            with st.spinner('Processing PDF... This may take a moment for scanned documents.'):
                for i, page in enumerate(doc):
                    if i == 0:
                        redact_page_by_coordinates(page)

                    redact_page_by_text_search(page)
                    
                    if len(page.get_text("blocks")) > SCANNED_PDF_TEXT_BLOCK_THRESHOLD:
                        is_likely_scanned = False
                    
                    page.apply_redactions()

                if is_likely_scanned and TESSERACT_INSTALLED:
                    st.info("Digital text not found. Activating OCR for deeper analysis...", icon="📄")
                    for page in doc:
                        redact_page_by_ocr(page)
                        page.apply_redactions()

                output_bytes = io.BytesIO()
                doc.save(output_bytes, garbage=4, deflate=True, clean=True)
                output_bytes.seek(0)
                doc.close()

            st.success("✅ Redaction process completed successfully!", icon="🎉")

            new_filename = f"(REDACTED)_{uploaded_file.name}"
            st.download_button(
                label="📥 Download Redacted PDF",
                data=output_bytes,
                file_name=new_filename,
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"An error occurred during PDF processing: {e}", icon="🚨")
            st.error("Please ensure you have uploaded a valid, non-corrupted PDF file.")

if __name__ == "__main__":
    main()
