import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os
import re

# --- Tesseract-OCR 경로 설정 (선택 사항) ---
# 시스템 PATH에 Tesseract 경로가 없는 경우, 아래 주석을 해제하고 직접 경로를 지정하세요.
# 예: pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- 1. 마스킹 좌표 설정 (규칙 1) ---
# 1페이지의 고정 마스킹 영역 (BBOX: [x0, y0, x1, y1])
PAGE_1_BBOXES = [
    [262.2, 189.9, 447.9, 254.6],  # 반/번호/담임성명 영역
    [457.0, 124.7, 559.6, 258.6],  # 사진 영역
    [84.2, 280.6, 562.4, 333.8],  # 성명, 성별, 주민등록번호, 주소 영역
    [84.2, 337.3, 562.4, 369.7],  # 학적사항 영역
]

# 모든 페이지에 공통으로 적용될 마스킹 영역
ALL_PAGES_BBOXES = [
    [28.3, 768.7, 277.8, 807.9],   # 모든 페이지 맨하단 고등학교이름 영역
    [328.0, 768.7, 566.9, 839.1],  # 모든 페이지 맨하단 반/번호/성명 영역
]

# --- 2. 텍스트 및 OCR 검색 키워드 설정 ---
# "(어쩌구)고등학교" 패턴을 찾기 위한 정규식
HIGH_SCHOOL_REGEX = re.compile(r'\S+고등학교')

# [추가됨] "(어쩌구)대학교(어쩌구)" 패턴을 찾기 위한 정규식
# 예: "동국대학교", "동국대학교부속", "인하대학교사범대학부속" 등 포함
UNIVERSITY_REGEX = re.compile(r'\S*대학교\S*')

# "반", "번호", "성명" 레이블 및 값
STUDENT_INFO_KEYWORDS = ["반", "번호", "성명"]

# --- 핵심 마스킹 함수 ---

def add_redaction_annot(page, rect):
    """페이지에 흰색 마스킹 주석을 추가하는 함수 (페이지 번호 보호 로직 강화)"""
    page_width = page.rect.width
    page_height = page.rect.height

    # 페이지 하단 중앙의 쪽 번호 영역은 마스킹하지 않도록 예외 처리
    is_at_bottom = rect.y1 > page_height - 50
    is_at_center = (page_width / 2 - 50) < rect.x0 < (page_width / 2 + 50)
    is_narrow = rect.width < 100 

    if is_at_bottom and is_at_center and is_narrow:
        return

    # 1페이지 상단 제목은 마스킹하지 않음
    if page.number == 0 and rect.y0 < 100:
        return

    page.add_redact_annot(rect, fill=(1, 1, 1))


def process_pdf(uploaded_file):
    """PDF 파일을 읽어 민감정보를 마스킹하고 새로운 PDF 파일을 반환하는 메인 함수"""
    
    tesseract_warning_shown = False
    
    try:
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
    except Exception as e:
        st.error(f"PDF 파일을 여는 중 오류가 발생했습니다: {e}")
        return None

    # 최대 23페이지까지만 처리
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
        
        # 1) 정규식 검색 (고등학교 + 대학교 포함 단어)
        words = page.get_text("words")
        for word in words:
            word_text = word[4]
            # 고등학교 패턴 OR 대학교 패턴 검색
            if HIGH_SCHOOL_REGEX.search(word_text) or UNIVERSITY_REGEX.search(word_text):
                add_redaction_annot(page, fitz.Rect(word[:4]))
                text_found = True
        
        # 2) 단순 문자열 검색 ("고등학교", "대학교" 키워드 자체도 한번 더 체크)
        if page_num in [0, 1, 4, 5]: 
            # 고등학교 검색
            for inst in page.search_for("고등학교"):
                 add_redaction_annot(page, inst)
                 text_found = True
            # [추가됨] 대학교 검색 (혹시 정규식에서 놓친 텍스트 조각을 위해)
            for inst in page.search_for("대학교"):
                 add_redaction_annot(page, inst)
                 text_found = True

        # 3) 학생 정보 키워드 검색
        for keyword in STUDENT_INFO_KEYWORDS:
            for inst in page.search_for(keyword):
                add_redaction_annot(page, inst)
                text_found = True

        # [규칙 3] OCR 기반 마스킹 (스캔된 PDF)
        if not text_found and page_num > 0:
            try:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_data = pytesseract.image_to_data(img, lang='kor', output_type=Output.DICT)
                
                n_boxes = len(ocr_data['level'])
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    if not text:
                        continue

                    # 고등학교 패턴 OR 대학교 패턴 OR 학생정보 키워드 검색
                    if (HIGH_SCHOOL_REGEX.search(text) or 
                        UNIVERSITY_REGEX.search(text) or 
                        text in STUDENT_INFO_KEYWORDS):
                        
                        (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                        img_rect = fitz.Rect(x, y, x + w, y + h)
                        page_rect = img_rect * page.rect.width / img.width 
                        add_redaction_annot(page, page_rect)

            except pytesseract.TesseractNotFoundError:
                if not tesseract_warning_shown:
                    st.warning("Tesseract-OCR이 설치되지 않았거나 경로가 올바르지 않습니다. 스캔된 PDF의 텍스트 마스킹이 제한됩니다.", icon="⚠")
                    tesseract_warning_shown = True
                pass
            except Exception as e:
                st.error(f"OCR 처리 중 오류가 발생했습니다: {e}")
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
2️⃣ 단, 스캔한 PDF는 스캔 해상도 품질에 따라 수상경력과 봉사실적란에 학교명이 노출  
""")

uploaded_file = st.file_uploader(
    "처리할 PDF 파일을 선택하세요. (최대 23페이지 내외)",
    type="pdf",
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.info(f"'{uploaded_file.name}' 파일이 업로드 되었습니다. 잠시 후, 마스킹이 시작됩니다...")

    with st.spinner("개인정보(학교명, 대학명 등)를 찾아 마스킹하는 중..."):
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
