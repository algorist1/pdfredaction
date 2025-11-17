import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os
import re
import cv2
import numpy as np

# --- Tesseract-OCR 경로 설정 ---
# Streamlit Cloud 배포 시에는 경로 지정이 필요 없음 (자동 인식)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- 1. 마스킹 좌표 설정 (규칙 1) ---
PAGE_1_BBOXES = [
    [262.2, 189.9, 447.9, 253.6],
    [453.0, 124.7, 559.6, 256.6],
    [121.9, 280.6, 558.4, 333.8],
    [80.2, 337.3, 388.3, 369.7],
]
PAGE_2_BBOXES = [
    [28.3, 80.0, 566.9, 520.0],
]
ALL_PAGES_BBOXES = [
    [28.3, 768.7, 277.8, 807.9],
    [328.0, 768.7, 566.9, 839.1],
]

# --- 2. 텍스트 및 OCR 검색 키워드 설정 ---
HIGH_SCHOOL_REGEX = re.compile(r'\S+고등학교')
STUDENT_INFO_KEYWORDS = ["반", "번호", "성명"]

# --- 핵심 마스킹 함수 ---
def add_redaction_annot(page, rect):
    page_width = page.rect.width
    page_height = page.rect.height
    is_at_bottom = rect.y1 > page_height - 50
    is_at_center = (page_width / 2 - 50) < rect.x0 < (page_width / 2 + 50)
    is_narrow = rect.width < 100
    if is_at_bottom and is_at_center and is_narrow:
        return
    if page.number == 0 and rect.y0 < 100:
        return
    page.add_redact_annot(rect, fill=(1, 1, 1))

def process_pdf(uploaded_file):
    tesseract_warning_shown = False
    try:
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
    except Exception as e:
        st.error(f"PDF 파일을 여는 중 오류가 발생했습니다: {e}")
        return None

    num_pages_to_process = min(len(doc), 23)

    for page_num in range(num_pages_to_process):
        page = doc[page_num]

        # [규칙 1] 고정 좌표 기반 마스킹
        if page_num == 0:
            for bbox in PAGE_1_BBOXES:
                add_redaction_annot(page, fitz.Rect(bbox))
        for bbox in ALL_PAGES_BBOXES:
            add_redaction_annot(page, fitz.Rect(bbox))

        # [규칙 2] 텍스트 검색 기반 마스킹 (디지털 PDF)
        text_found = False
        words = page.get_text("words")
        for word in words:
            if HIGH_SCHOOL_REGEX.search(word[4]):
                add_redaction_annot(page, fitz.Rect(word[:4]))
                text_found = True
        if page_num in [0, 1, 4, 5]:
            for inst in page.search_for("고등학교"):
                add_redaction_annot(page, inst)
                text_found = True
        for keyword in STUDENT_INFO_KEYWORDS:
            for inst in page.search_for(keyword):
                add_redaction_annot(page, inst)
                text_found = True

        # [규칙 3] OCR 기반 마스킹 (스캔된 PDF)
        # ★★★ 수정된 부분 ★★★
        # 1~6페이지(인덱스 0~5)는 디지털 텍스트 발견 여부와 관계없이 항상 OCR을 실행하도록 변경
        should_run_ocr = page_num <= 5
        
        if should_run_ocr:
            # --- 디버깅 코드 1: OCR 실행 여부를 Streamlit UI에 표시 ---
            st.info(f"📄 {page_num + 1}페이지에 대해 OCR(광학 문자 인식)을 실행합니다...")
            
            try:
                pix = page.get_pixmap(dpi=400)
                img_bytes = pix.tobytes("png")
                pil_img = Image.open(io.BytesIO(img_bytes))
                cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                gray_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                _, binary_img = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                img_for_ocr = Image.fromarray(binary_img)
                
                custom_config = r'--oem 3 --psm 3'
                ocr_data = pytesseract.image_to_data(
                    img_for_ocr,
                    lang='kor',
                    output_type=Output.DICT,
                    config=custom_config
                )
                
                # --- 디버깅 코드 2: OCR로 인식된 전체 텍스트를 로그에 출력 ---
                all_text = " ".join(ocr_data['text']).strip()
                if all_text:
                    print(f"--- 페이지 {page_num + 1} OCR 결과 ---")
                    print(all_text)
                    print("------------------------------")
                
                ocr_found_count = 0
                n_boxes = len(ocr_data['level'])
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    if HIGH_SCHOOL_REGEX.search(text):
                        (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                        scale = page.rect.width / pix.width
                        page_rect = fitz.Rect(x, y, x + w, y + h) * scale
                        page_rect.expand(2) # 여백 2px 추가
                        add_redaction_annot(page, page_rect)
                        ocr_found_count += 1
                
                if ocr_found_count > 0:
                     st.write(f"✔️ {page_num + 1}페이지에서 OCR로 '{ocr_found_count}'개의 학교명을 찾아 마스킹했습니다.")
                else:
                     st.write(f"ℹ️ {page_num + 1}페이지 OCR 결과, 마스킹할 학교명을 찾지 못했습니다.")

            except pytesseract.TesseractNotFoundError:
                if not tesseract_warning_shown:
                    st.warning("Tesseract-OCR이 설치되지 않았거나 경로가 올바르지 않습니다.", icon="⚠️")
                    tesseract_warning_shown = True
                pass
            except Exception as e:
                st.error(f"OCR 처리 중 오류 (페이지 {page_num + 1}): {e}")
                pass

        page.apply_redactions()

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    doc.close()
    output_buffer.seek(0)
    return output_buffer

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="PDF 개인정보 마스킹 앱", page_icon="📄")
st.title("🪄 PDF 개인정보 마스킹 도구")
st.write("""
1️⃣ 나이스에서 다운로드한 학생부 PDF 파일을 업로드 후, 주요 개인정보 마스킹 처리  
2️⃣ 단, 스캔한 PDF는 Tesseract-OCR를 설치 후 사용, 그렇치 않으면 수상경력과 봉사실적란에 학교명이 노출 
""")
uploaded_file = st.file_uploader(
    "처리할 PDF 파일을 선택하세요. (최대 23페이지 내외)",
    type="pdf"
)

if uploaded_file is not None:
    st.info(f"'{uploaded_file.name}' 파일 업로드 완료. 마스킹을 시작합니다.")
    with st.spinner("개인정보를 찾아 마스킹하는 중..."):
        processed_pdf_buffer = process_pdf(uploaded_file)
    if processed_pdf_buffer:
        st.success("✅ 마스킹 처리가 완료되었습니다!")
        original_filename = os.path.splitext(uploaded_file.name)[0]
        new_filename = f"(제거됨) {original_filename}.pdf"
        st.download_button(
            label="마스킹된 PDF 파일 다운로드",
            data=processed_pdf_buffer,
            file_name=new_filename,
            mime="application/pdf"
        )
