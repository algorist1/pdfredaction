# main.py

import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import re
from shutil import which

# --- Configuration Section ---

# [Rule 1] BBOX coordinates for redaction on Page 1.
# Format: fitz.Rect(x0, y0, x1, y1)
# --- COORDINATES RE-CALIBRATED AND FINALIZED (2025-11-16) ---
# This new set is precisely matched to the user's latest document image for maximum accuracy.
PAGE_1_BBOXES = [
    # 1. Photo Area (Corrected position and size)
    fitz.Rect(460, 50, 565, 185),
    
    # 2. Top Table (Covers all values for Class, Number, and Homeroom Teacher)
    fitz.Rect(320, 120, 560, 180),
    
    # 3. Student Information Block (Name, Gender, RRN, Address)
    fitz.Rect(115, 204, 560, 248),
    
    # 4. Academic Information Block
    fitz.Rect(115, 250, 560, 288),
    
    # 5. Special Notes Block
    fitz.Rect(115, 290, 560, 310)
]

# [Rule 2 & 3] Text patterns for redaction
FOOTER_PII_KEYWORDS = ["반", "번호", "성명"]

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

def redact_school_names_by_regex(page):
    """Finds and redacts text matching '...고등학교'."""
    school_name_pattern = re.compile(r'\S+고등학교')
    blocks = page.get_text("blocks")
    for block in blocks:
        block_text = block[4]
        block_rect = fitz.Rect(block[:4])
        for match in school_name_pattern.finditer(block_text):
            school_name = match.group(0)
            areas_to_redact = page.search_for(school_name, clip=block_rect)
            for area in areas_to_redact:
                # Exclude the main title
                if area.y0 > 50:
                    page.add_redact_annot(area, fill=(1, 1, 1))

def redact_page_by_coordinates(page):
    """[Rule 1] Applies fixed-coordinate redactions to a page."""
    for rect in PAGE_1_BBOXES:
        page.add_redact_annot(rect, fill=(1, 1, 1))

def redact_page_by_text_search(page):
    """[Rule 2] Searches for and redacts specific text strings."""
    # 1. Redact any high school name using regex
    redact_school_names_by_regex(page)
    
    # 2. Redact footer PII while preserving the page number
    footer_rects = []
    for keyword in FOOTER_PII_KEYWORDS:
        footer_rects.extend(page.search_for(keyword))
    
    if footer_rects:
        # Combine all found keyword boxes into a single redaction area
        combined_rect = fitz.Rect(footer_rects[0].tl, footer_rects[0].br)
        for rect in footer_rects[1:]:
            combined_rect.include_rect(rect)
            
        # IMPORTANT: Only apply if it's in the footer region (y > 800)
        # This prevents accidental redaction in the main content and preserves the page number.
        if combined_rect.y0 > 800:
            # Extend the box to the right to cover the actual names/numbers
            combined_rect.x1 += 100 
            page.add_redact_annot(combined_rect, fill=(1, 1, 1))

def redact_page_by_ocr(page):
    """[Rule 3] Performs OCR and redacts text."""
    if not TESSERACT_INSTALLED:
        st.warning("Tesseract-OCR is not installed. OCR redaction is disabled.", icon="⚠️")
        return
    pix = page.get_pixmap(dpi=OCR_DPI)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        ocr_data = pytesseract.image_to_data(img, lang='kor', output_type=Output.DICT)
    except pytesseract.TesseractError as e:
        st.error(f"Tesseract OCR Error: {e}", icon="🚨")
        return
    
    school_name_pattern = re.compile(r'\S+고등학교')
    num_boxes = len(ocr_data['level'])
    
    for i in range(num_boxes):
        text, conf = ocr_data['text'][i], int(ocr_data['conf'][i])
        if conf < OCR_CONFIDENCE_THRESHOLD or not text.strip():
            continue
            
        is_school = school_name_pattern.search(text)
        is_footer_pii = any(keyword in text for keyword in FOOTER_PII_KEYWORDS)
        
        if is_school or is_footer_pii:
            (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
            bbox = fitz.Rect(x, y, x + w, y + h) / (OCR_DPI / 72)
            
            # Additional checks to avoid redacting the wrong thing
            if is_school and bbox.y0 < 50: continue # Don't redact title
            if is_footer_pii and bbox.y0 < 800: continue # Only redact footer PII
            
            page.add_redact_annot(bbox, fill=(1, 1, 1))

# --- Main Streamlit Application ---

def main():
    st.set_page_config(page_title="PDF Personal Info Redactor", page_icon="🔒")
    st.title("🔒 PDF Personal Information Redactor")
    st.markdown("Upload a Korean school record PDF to automatically redact sensitive information.")
    
    if not TESSERACT_INSTALLED:
        st.error("**OCR functionality unavailable.** Tesseract-OCR engine not found.", icon="🚨")
        
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file:
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
                    page.apply_redactions()
                        
                if is_likely_scanned and TESSERACT_INSTALLED:
                    st.info("Activating OCR for deeper analysis...", icon="📄")
                    for page in doc:
                        redact_page_by_ocr(page)
                        page.apply_redactions()
                        
                output_bytes = io.BytesIO()
                doc.save(output_bytes, garbage=4, deflate=True, clean=True)
                output_bytes.seek(0)
                doc.close()
                
            st.success("✅ Redaction process completed successfully!", icon="🎉")
            new_filename = f"(REDACTED)_{uploaded_file.name}"
            st.download_button(label="📥 Download Redacted PDF", data=output_bytes, file_name=new_filename, mime="application/pdf")
            
        except Exception as e:
            st.error(f"An error occurred: {e}", icon="🚨")

if __name__ == "__main__":
    main()
