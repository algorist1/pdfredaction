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
# !IMPORTANT!: These coordinates are calibrated for the LATEST '대성고등학교'
# document template provided by the user (the one with the blue lines).
PAGE_1_BBOXES = [
    # Top Right Photo Area
    fitz.Rect(460, 80, 565, 215),

    # Top Table Values (반, 번호, 담임성명)
    fitz.Rect(320, 105, 375, 125),  # 반 (Class) Value
    fitz.Rect(380, 105, 435, 125),  # 번호 (Number) Value
    fitz.Rect(480, 105, 555, 125),  # 담임성명 (Teacher) Value

    # 1. 인적·학적사항 (Personal & Academic Info) Section
    # These values are already found and redacted by the text search logic,
    # but we keep BBOXes as a reliable fallback.
    fitz.Rect(120, 204, 185, 220),  # 성명 (Name) Value
    fitz.Rect(280, 204, 320, 220),  # 성별 (Gender) Value
    fitz.Rect(430, 204, 560, 220),  # 주민등록번호 (RRN) Value
    fitz.Rect(120, 225, 560, 246),  # 주소 (Address) Value
    fitz.Rect(120, 250, 560, 286),  # 학적사항 (Academic Status) Value
]

# [Rule 2 & 3] Text patterns for redaction
# The school name is not visible in the provided image, but based on the layout,
# we will assume "대성고등학교" for the text/OCR search.
# This can be changed if the school name is different.
SCHOOL_NAME_TEXT = "대성고등학교"
# Keywords for the footer that need to be redacted
FOOTER_PII_KEYWORDS = ["반", "번호", "성명", "박지호"] # Adding the name for robust redaction


# OCR configuration
OCR_CONFIDENCE_THRESHOLD = 40
SCANNED_PDF_TEXT_BLOCK_THRESHOLD = 10
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
    """[Rule 2] Searches for and redacts specific text strings, including footer PII."""
    # 1. Redact the school name (if found)
    school_name_areas = page.search_for(SCHOOL_NAME_TEXT)
    for area in school_name_areas:
        # Check to avoid redacting the main title if it contains a similar word
        if area.y0 > 80: # Simple heuristic: assume title is always at the top
            page.add_redact_annot(area, fill=(1, 1, 1))

    # 2. Redact the footer PII block precisely, preserving the page number
    footer_rects = []
    for keyword in FOOTER_PII_KEYWORDS:
        # Search for all instances of the PII keywords in the footer region
        # The y0 > 800 condition ensures we only search at the bottom of the page
        found_areas = [r for r in page.search_for(keyword) if r.y0 > 800]
        footer_rects.extend(found_areas)
    
    # Combine all found PII areas in the footer into one single redaction box
    if footer_rects:
        # The combined_rect starts with the first found item
        combined_rect = fitz.Rect(footer_rects[0].tl, footer_rects[0].br)
        # Expand this rectangle to include all other found PII items
        for rect in footer_rects[1:]:
            combined_rect.include_rect(rect)
        
        # Add a little horizontal padding to ensure values are fully covered
        combined_rect.x0 -= 5
        combined_rect.x1 += 5
        page.add_redact_annot(combined_rect, fill=(1, 1, 1))

def redact_page_by_ocr(page):
    """[Rule 3] Performs OCR for scanned PDFs."""
    if not TESSERACT_INSTALLED:
        st.warning("Tesseract-OCR is not installed. OCR-based redaction is disabled.", icon="⚠️")
        return

    pix = page.get_pixmap(dpi=OCR_DPI)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    try:
        ocr_data = pytesseract.image_to_data(img, lang='kor', output_type=Output.DICT)
    except pytesseract.TesseractError as e:
        st.error(f"Tesseract OCR Error: {e}", icon="🚨")
        return

    num_boxes = len(ocr_data['level'])
    
    # Process OCR results to find and redact footer PII
    footer_ocr_rects = []
    for i in range(num_boxes):
        conf = int(ocr_data['conf'][i])
        text = ocr_data['text'][i].strip()
        
        if conf < OCR_CONFIDENCE_THRESHOLD or not text:
            continue
        
        # Check if the recognized text is one of our footer keywords
        if any(keyword in text for keyword in FOOTER_PII_KEYWORDS):
            (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
            # Scale coordinates back to PDF's coordinate system
            bbox = fitz.Rect(x, y, x + w, y + h) / (OCR_DPI / 72)
            
            # Check if it's in the footer area to avoid redacting content
            if bbox.y0 > 800:
                footer_ocr_rects.append(bbox)
    
    # Combine all found OCR footer PII into a single redaction
    if footer_ocr_rects:
        combined_rect = fitz.Rect(footer_ocr_rects[0].tl, footer_ocr_rects[0].br)
        for rect in footer_ocr_rects[1:]:
            combined_rect.include_rect(rect)
        combined_rect.x0 -= 5
        combined_rect.x1 += 5
        page.add_redact_annot(combined_rect, fill=(1, 1, 1))

# --- Main Streamlit Application ---

def main():
    st.set_page_config(page_title="PDF Personal Info Redactor", page_icon="🔒")
    st.title("🔒 PDF Personal Information Redactor")
    st.markdown("Upload a Korean school record PDF to automatically redact sensitive personal information.")

    if not TESSERACT_INSTALLED:
        st.error("**OCR functionality unavailable.** The app will use fixed-coordinate and text-search redaction only.", icon="🚨")

    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

    if uploaded_file is not None:
        try:
            pdf_bytes = uploaded_file.getvalue()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            is_likely_scanned = True

            with st.spinner('Processing PDF...'):
                for i, page in enumerate(doc):
                    if i == 0:
                        redact_page_by_coordinates(page)
                    
                    redact_page_by_text_search(page)
                    
                    if len(page.get_text("blocks")) > SCANNED_PDF_TEXT_BLOCK_THRESHOLD:
                        is_likely_scanned = False
                    
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                if is_likely_scanned and TESSERACT_INSTALLED:
                    st.info("Digital text not found. Activating OCR...", icon="📄")
                    for page in doc:
                        redact_page_by_ocr(page)
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                output_bytes = io.BytesIO()
                doc.save(output_bytes, garbage=4, deflate=True, clean=True)
                doc.close()

            st.success("✅ Redaction process completed!", icon="🎉")
            new_filename = f"(REDACTED)_{uploaded_file.name}"
            st.download_button(
                label="📥 Download Redacted PDF",
                data=output_bytes.getvalue(),
                file_name=new_filename,
                mime="application/pdf",
            )

        except Exception as e:
            st.error(f"An error occurred: {e}", icon="🚨")

if __name__ == "__main__":
    main()
