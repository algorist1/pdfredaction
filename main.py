import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os
import re
import subprocess

# --- Tesseract 설치 확인 및 경로 설정 ---
def check_tesseract_installation():
    """Tesseract 설치 여부 확인 및 자동 경로 설정"""
    try:
        # 리눅스/클라우드 환경에서 tesseract 경로 찾기
        result = subprocess.run(['which', 'tesseract'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            tesseract_path = result.stdout.strip()
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            return True, tesseract_path
    except Exception:
        pass
    
    # Windows 환경 체크
    windows_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    ]
    for path in windows_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return True, path
    
    # 기본 명령어로 실행 시도
    try:
        pytesseract.get_tesseract_version()
        return True, "tesseract (기본 PATH)"
    except Exception:
        return False, None

# 앱 시작 시 Tesseract 확인
TESSERACT_AVAILABLE, TESSERACT_PATH = check_tesseract_installation()

# --- 1. 마스킹 좌표 설정 (규칙 1) ---
# 사용자가 쉽게 수정할 수 있도록 좌표 변수를 상단에 모음

# 1페이지의 고정 마스킹 영역 (BBOX: [x0, y0, x1, y1])
PAGE_1_BBOXES = [
    [262.2, 189.9, 447.9, 253.6],  # 반/번호/담임성명 영역
    [453.0, 124.7, 559.6, 256.6],  # 사진 영역
    [121.9, 280.6, 558.4, 333.8],  # 성명, 성별, 주민등록번호, 주소 영역
    [80.2, 337.3, 388.3, 369.7],  # 학적사항 영역
]

# 2페이지의 고정 마스킹 영역 (수상경력 계속)
PAGE_2_BBOXES = [
    [28.3, 80.0, 566.9, 520.0],   # 2페이지 수상경력란 전체
]

# 모든 페이지 공통 마스킹 영역
ALL_PAGES_BBOXES = [
    [28.3, 768.7, 277.8, 807.9],   # 모든 페이지 맨하단 고등학교이름 영역
    [328.0, 768.7, 566.9, 839.1],  # 모든 페이지 맨하단 반/번호/성명 영역
]

# --- 2. 텍스트 검색 키워드 설정 ---
# "(어쩌구)고등학교" 패턴을 찾기 위한 정규식
HIGH_SCHOOL_REGEX = re.compile(r'\S+고등학교')

# "반", "번호", "성명" 레이블 및 값
STUDENT_INFO_KEYWORDS = ["반", "번호", "성명"]

# --- 핵심 마스킹 함수 ---

def add_redaction_annot(page, rect):
    """페이지에 흰색 마스킹 주석을 추가하는 함수 (페이지 번호 보호 로직 강화)"""
    page_width = page.rect.width
    page_height = page.rect.height

    # 페이지 하단 중앙의 쪽 번호 영역은 마스킹하지 않도록 예외 처리
    # 조건 강화: 1)하단 영역, 2)중앙 영역, 3)너비가 좁은 영역(페이지 번호 특징)
    is_at_bottom = rect.y1 > page_height - 50
    is_at_center = (page_width / 2 - 50) < rect.x0 < (page_width / 2 + 50)
    is_narrow = rect.width < 100 # 페이지 번호 영역의 너비는 보통 100pt를 넘지 않음

    if is_at_bottom and is_at_center and is_narrow:
        return

    # 1페이지 상단 제목은 마스킹하지 않음
    if page.number == 0 and rect.y0 < 100:
        return

    page.add_redact_annot(rect, fill=(1, 1, 1))


def is_scanned_pdf(page):
    """PDF 페이지가 스캔본인지 확인 (텍스트 추출 가능 여부로 판단)"""
    try:
        text = page.get_text().strip()
        # 텍스트가 거의 없으면 스캔본으로 판단 (50자 미만)
        return len(text) < 50
    except Exception:
        return True


def process_pdf(uploaded_file):
    """PDF 파일을 읽어 민감정보를 마스킹하고 새로운 PDF 파일을 반환하는 메인 함수"""
    
    # OCR 경고 메시지를 한 번만 표시하기 위한 플래그
    tesseract_warning_shown = False
    
    try:
        # 업로드된 파일 데이터를 BytesIO로 읽어 fitz에서 열기
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
    except Exception as e:
        st.error(f"PDF 파일을 여는 중 오류가 발생했습니다: {e}")
        return None

    # 최대 23페이지까지만 처리
    num_pages_to_process = min(len(doc), 23)

    # 페이지 순회하며 마스킹 작업 수행
    for page_num in range(num_pages_to_process):
        page = doc[page_num]

        # [규칙 1] 고정 좌표 기반 마스킹 (모든 PDF에 적용)
        if page_num == 0: # 1페이지인 경우
            for bbox in PAGE_1_BBOXES:
                add_redaction_annot(page, fitz.Rect(bbox))
        
        if page_num == 1: # 2페이지인 경우
            for bbox in PAGE_2_BBOXES:
                add_redaction_annot(page, fitz.Rect(bbox))
        
        # 모든 페이지 공통 좌표 마스킹
        for bbox in ALL_PAGES_BBOXES:
            add_redaction_annot(page, fitz.Rect(bbox))

        # [규칙 2] 디지털 PDF만 텍스트 검색 기반 마스킹 수행
        if not is_scanned_pdf(page):
            # 1) "( )고등학교" 검색
            words = page.get_text("words")
            for word in words:
                word_text = word[4]
                if HIGH_SCHOOL_REGEX.search(word_text):
                    add_redaction_annot(page, fitz.Rect(word[:4]))
            
            # 2) 수상경력, 봉사활동 등 특정 영역의 "고등학교" 검색
            if page_num in [0, 1, 4, 5]: # 1~2, 5~6 페이지
                for inst in page.search_for("고등학교"):
                     add_redaction_annot(page, inst)

            # 3) 모든 페이지 하단 "반", "번호", "성명" 검색
            for keyword in STUDENT_INFO_KEYWORDS:
                for inst in page.search_for(keyword):
                    add_redaction_annot(page, inst)

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

# Tesseract 상태 표시
if TESSERACT_AVAILABLE:
    st.success(f"✅ OCR 엔진 활성화됨 (디지털 PDF 지원)")
else:
    st.warning("""
    ⚠️ OCR 엔진이 감지되지 않았습니다. 
    - **디지털 PDF**: 텍스트 검색으로 마스킹 진행
    - **스캔 PDF**: 지정된 좌표 영역만 마스킹됨
    """, icon="⚠️")

st.write("""
**사용 방법:**  
1️⃣ 나이스에서 다운로드한 학생부 PDF 파일 업로드  
2️⃣ 자동으로 주요 개인정보 마스킹 처리  
3️⃣ 처리된 PDF 파일 다운로드

**처리 방식:**
- 디지털 PDF: 좌표 마스킹 + 텍스트 검색 마스킹
- 스캔 PDF: 좌표 마스킹만 적용
""")

uploaded_file = st.file_uploader(
    "처리할 PDF 파일을 선택하세요 (최대 23페이지)",
    type="pdf",
    accept_multiple_files=False
)

if uploaded_file is not None:
    st.info(f"📄 '{uploaded_file.name}' 파일 업로드 완료")

    with st.spinner("🔒 개인정보 마스킹 중..."):
        processed_pdf_buffer = process_pdf(uploaded_file)

    if processed_pdf_buffer:
        st.success("✅ 마스킹 처리가 완료되었습니다!")

        original_filename = os.path.splitext(uploaded_file.name)[0]
        new_filename = f"(제거됨) {original_filename}.pdf"

        st.download_button(
            label="📥 마스킹된 PDF 다운로드",
            data=processed_pdf_buffer,
            file_name=new_filename,
            mime="application/pdf",
            type="primary"
        )
        
        st.info("💡 다운로드 후 반드시 PDF를 열어 개인정보가 제대로 마스킹되었는지 확인하세요.", icon="💡")
