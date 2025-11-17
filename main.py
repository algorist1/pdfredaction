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
# 로컬 Windows에서만 테스트할 때는 아래 주석 해제
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- 1. 마스킹 좌표 설정 ---
PAGE_1_BBOXES = [
    [262.2, 189.9, 447.9, 253.6],  # 반/번호/담임성명 영역
    [453.0, 124.7, 559.6, 256.6],  # 사진 영역
    [121.9, 280.6, 558.4, 333.8],  # 성명, 성별, 주민등록번호, 주소 영역
    [80.2, 337.3, 388.3, 369.7],   # 학적사항 영역
]
ALL_PAGES_BBOXES = [
    [28.3, 768.7, 277.8, 807.9],   # 모든 페이지 맨하단 고등학교이름 영역
    [328.0, 768.7, 566.9, 839.1],  # 모든 페이지 맨하단 반/번호/성명 영역
]

# --- 2. 텍스트 검색 키워드 설정 ---
# [OCR용] '고 등 학 교' 처럼 띄어쓰기나 다른 문자가 포함돼도 찾을 수 있는 유연한 정규식
OCR_HIGH_SCHOOL_REGEX = re.compile(r'고\s*등\s*학\s*교')

# [디지털 PDF용] 공백 없이 '고등학교'가 붙어있는 경우를 찾는 정확한 정규식
DIGITAL_HIGH_SCHOOL_REGEX = re.compile(r'\S+고등학교')
STUDENT_INFO_KEYWORDS = ["반", "번호", "성명"]

# --- 핵심 마스킹 함수 ---
def add_redaction_annot(page, rect):
    """페이지에 흰색 마스킹 주석을 추가하는 함수 (페이지 번호 등 예외 처리 포함)"""
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
    """PDF 파일을 읽어 민감정보를 마스킹하고 새로운 PDF 파일을 반환하는 메인 함수"""
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
        words = page.get_text("words")
        for word in words:
            if DIGITAL_HIGH_SCHOOL_REGEX.search(word[4]):
                add_redaction_annot(page, fitz.Rect(word[:4]))
        for keyword in STUDENT_INFO_KEYWORDS:
            for inst in page.search_for(keyword):
                add_redaction_annot(page, inst)

        # [규칙 3] OCR 기반 마스킹 (스캔된 PDF)
        should_run_ocr = page_num <= 5
        if should_run_ocr:
            st.info(f"📄 {page_num + 1}페이지에 대해 OCR(광학 문자 인식)을 실행합니다...")
            try:
                # 이미지 추출 및 전처리
                pix = page.get_pixmap(dpi=300) # DPI는 300으로도 충분할 수 있습니다.
                pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
                cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                gray_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                _, binary_img = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                img_for_ocr = Image.fromarray(binary_img)
                
                # Tesseract OCR 실행하여 단어 단위 데이터 추출
                ocr_data = pytesseract.image_to_data(img_for_ocr, lang='kor', output_type=Output.DICT)

                # --- ★★★ 개선된 OCR 로직 ★★★ ---
                # 1. OCR 결과를 줄(line) 단위로 재구성
                lines = {}
                for i in range(len(ocr_data['text'])):
                    # 신뢰도 30% 이상인 단어만 사용
                    if int(ocr_data['conf'][i]) > 30:
                        key = (ocr_data['block_num'][i], ocr_data['par_num'][i], ocr_data['line_num'][i])
                        if key not in lines:
                            lines[key] = []
                        lines[key].append({
                            'text': ocr_data['text'][i],
                            'left': ocr_data['left'][i],
                            'top': ocr_data['top'][i],
                            'width': ocr_data['width'][i],
                            'height': ocr_data['height'][i]
                        })

                # 2. 재구성된 각 줄을 검사하여 '고등학교' 패턴이 있는지 확인
                ocr_found_count = 0
                for key in lines:
                    line_words = lines[key]
                    line_text = "".join([word['text'] for word in line_words])
                    
                    if OCR_HIGH_SCHOOL_REGEX.search(line_text):
                        # 3. 패턴이 발견되면 해당 줄 전체의 좌표를 계산하여 마스킹
                        x0 = min([word['left'] for word in line_words])
                        y0 = min([word['top'] for word in line_words])
                        x1 = max([word['left'] + word['width'] for word in line_words])
                        y1 = max([word['top'] + word['height'] for word in line_words])

                        scale = page.rect.width / pix.width
                        img_rect = fitz.Rect(x0, y0, x1, y1)
                        page_rect = img_rect * scale
                        page_rect.expand(2) # 여백 2px 추가
                        add_redaction_annot(page, page_rect)
                        ocr_found_count += 1
                
                if ocr_found_count > 0:
                    st.write(f"✔️ {page_num + 1}페이지에서 OCR로 '{ocr_found_count}'개 라인의 학교명을 찾아 마스킹했습니다.")
                else:
                    st.write(f"ℹ️ {page_num + 1}페이지 OCR 결과, 마스킹할 학교명을 찾지 못했습니다.")

            except pytesseract.TesseractNotFoundError:
                if not tesseract_warning_shown:
                    st.warning("Tesseract-OCR이 설치되지 않았거나 경로가 올바르지 않습니다.", icon="⚠️")
                    tesseract_warning_shown = True
                break
            except Exception as e:
                st.error(f"OCR 처리 중 오류 (페이지 {page_num + 1}): {e}")
                pass

        # 해당 페이지에 추가된 모든 마스킹 주석을 실제로 적용
        page.apply_redactions()

    # 처리된 PDF를 메모리에 저장
    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    doc.close()
    output_buffer.seek(0)
    return output_buffer

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="PDF 개인정보 마스킹 앱", page_icon="📄")
st.title("🪄 PDF 개인정보 마스킹 도구")
st.write("""
학생부 PDF 파일을 업로드하면 주민등록번호, 사진, 주소, 학교명 등 주요 개인정보를 마스킹 처리합니다.
(디지털 PDF와 스캔된 PDF 모두 처리 가능)
""")
uploaded_file = st.file_uploader(
    "처리할 PDF 파일을 선택하세요.",
    type="pdf"
)

if uploaded_file is not None:
    st.info(f"'{uploaded_file.name}' 파일 업로드 완료. 마스킹을 시작합니다.")
    with st.spinner("개인정보를 찾아 마스킹하는 중... 잠시만 기다려주세요."):
        processed_pdf_buffer = process_pdf(uploaded_file)
    if processed_pdf_buffer:
        st.success("✅ 마스킹 처리가 완료되었습니다!")
        original_filename = os.path.splitext(uploaded_file.name)[0]
        new_filename = f"(마스킹 완료) {original_filename}.pdf"
        st.download_button(
            label="마스킹된 PDF 파일 다운로드",
            data=processed_pdf_buffer,
            file_name=new_filename,
            mime="application/pdf"
        )
