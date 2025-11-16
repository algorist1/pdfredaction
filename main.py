import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import os
import re

# ============================================
# 1페이지 고정 좌표 설정 (사용자 수정 가능)
# ============================================
# A4 용지 기준: 가로 약 595pt, 세로 약 842pt
# 좌표 형식: [x0, y0, x1, y1] (왼쪽 위 x, 왼쪽 위 y, 오른쪽 아래 x, 오른쪽 아래 y)

# 1페이지 마스킹 영역들 (검정 박스로 표시된 영역 기준)
# PDF 좌표계: 왼쪽 아래가 (0,0), A4 = 595x842pt
PAGE_1_BBOXES = [
    # 우측 상단 사진 영역
    [345, 585, 420, 740],
    
    # 상단 표: 1학년 반/번호/담임성명 값
    [193, 680, 333, 700],  # 1학년 반~담임성명 전체 행
    
    # 상단 표: 2학년 반/번호/담임성명 값  
    [193, 660, 333, 680],  # 2학년 반~담임성명 전체 행
    
    # 상단 표: 3학년 반/번호/담임성명 값
    [193, 640, 333, 660],  # 3학년 반~담임성명 전체 행
    
    # 1. 인적·학적사항 - 전체 학생정보 행 (성명, 성별, 주민등록번호)
    [60, 555, 425, 575],
    
    # 주소 전체 행
    [60, 535, 425, 555],
    
    # 학적사항 내용 (졸업, 입학 정보 2줄)
    [60, 495, 425, 535],
    
    # 페이지 하단 좌측 (학교명, 날짜)
    [5, 5, 110, 25],
    
    # 페이지 하단 우측 (반/번호/성명)
    [330, 5, 425, 25],
]

# Tesseract 경로 설정 (Windows 사용자는 주석 해제 후 경로 수정)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ============================================
# 유틸리티 함수들
# ============================================

def check_tesseract():
    """Tesseract 설치 여부 확인"""
    try:
        pytesseract.get_tesseract_version()
        return True
    except:
        return False

def is_page_number(rect, page_rect, text):
    """페이지 번호인지 확인 (중앙 하단의 숫자)"""
    page_width = page_rect.width
    page_height = page_rect.height
    
    # 중앙 하단 영역 체크
    is_bottom = rect.y1 > page_height * 0.9
    is_center = abs(rect.x0 - page_width / 2) < page_width * 0.15
    
    # 숫자만 있는지 체크
    is_number = text.strip().isdigit()
    
    return is_bottom and is_center and is_number

def is_title(rect, page_rect, text):
    """페이지 맨 위 제목인지 확인"""
    is_top = rect.y0 < page_rect.height * 0.1
    is_title_text = "학교생활세부사항기록부" in text or "학교생활기록부" in text
    
    return is_top and is_title_text

def mask_page_1_fixed_coords(page):
    """1페이지 고정 좌표 마스킹"""
    for bbox in PAGE_1_BBOXES:
        rect = fitz.Rect(bbox)
        page.add_redact_annot(rect, fill=(1, 1, 1))

def mask_by_text_search(page, page_num, total_pages):
    """텍스트 검색 기반 마스킹 (디지털 PDF용)"""
    page_rect = page.rect
    
    # 검색할 키워드들
    keywords = []
    
    # 1~2페이지: 수상경력의 고등학교명
    if 1 <= page_num <= 2:
        keywords.append("고등학교장")
    
    # 5~6페이지: 봉사활동실적의 고등학교명
    if 5 <= page_num <= 6:
        keywords.append("고등학교")
    
    # 모든 페이지 하단: 반, 번호, 성명과 고등학교명
    keywords.extend(["고등학교", "반", "번호", "성명"])
    
    masked_count = 0
    
    for keyword in keywords:
        instances = page.search_for(keyword)
        
        for inst in instances:
            # 해당 영역의 텍스트 추출
            text = page.get_text("text", clip=inst).strip()
            
            # 페이지 번호는 제외
            if is_page_number(inst, page_rect, text):
                continue
            
            # 제목은 제외
            if is_title(inst, page_rect, text):
                continue
            
            # "고등학교"를 포함한 전체 단어 찾기
            if keyword == "고등학교":
                # 앞쪽 텍스트도 포함하기 위해 확장된 영역에서 텍스트 추출
                extended_rect = fitz.Rect(
                    max(0, inst.x0 - 100),
                    inst.y0,
                    inst.x1,
                    inst.y1
                )
                extended_text = page.get_text("text", clip=extended_rect).strip()
                
                # "XXX고등학교" 패턴 찾기
                pattern = r'[\w가-힣]+고등학교'
                matches = re.finditer(pattern, extended_text)
                
                for match in matches:
                    # 매칭된 전체 단어를 마스킹할 영역 계산
                    school_name = match.group()
                    school_instances = page.search_for(school_name)
                    
                    for school_inst in school_instances:
                        school_text = page.get_text("text", clip=school_inst).strip()
                        
                        if is_page_number(school_inst, page_rect, school_text):
                            continue
                        if is_title(school_inst, page_rect, school_text):
                            continue
                        
                        page.add_redact_annot(school_inst, fill=(1, 1, 1))
                        masked_count += 1
            
            # "반", "번호", "성명"은 하단 영역만 마스킹 (테두리 포함)
            elif keyword in ["반", "번호", "성명"]:
                # 하단 영역인지 확인 (페이지 하단 10%)
                is_bottom = inst.y0 > page_rect.height * 0.9
                
                if is_bottom:
                    # 레이블과 값을 모두 포함하도록 영역 확장
                    extended_rect = fitz.Rect(
                        inst.x0 - 5,
                        inst.y0 - 5,
                        min(inst.x1 + 100, page_rect.width),
                        inst.y1 + 5
                    )
                    page.add_redact_annot(extended_rect, fill=(1, 1, 1))
                    masked_count += 1
            else:
                # 기타 키워드는 일반 마스킹
                page.add_redact_annot(inst, fill=(1, 1, 1))
                masked_count += 1
    
    return masked_count

def mask_by_ocr(page, page_num):
    """OCR 기반 마스킹 (스캔된 PDF용)"""
    try:
        # 페이지를 고해상도 이미지로 변환
        mat = fitz.Matrix(2.0, 2.0)  # 2배 확대
        pix = page.get_pixmap(matrix=mat)
        
        # PIL Image로 변환
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # OCR 실행
        ocr_data = pytesseract.image_to_data(
            img,
            lang='kor',
            output_type=pytesseract.Output.DICT
        )
        
        page_rect = page.rect
        masked_count = 0
        
        # OCR 결과 순회
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i])
            
            # 신뢰도가 낮은 결과는 제외
            if conf < 30 or not text:
                continue
            
            # 좌표 계산 (이미지 좌표를 PDF 좌표로 변환)
            x = ocr_data['left'][i] / 2.0
            y = ocr_data['top'][i] / 2.0
            w = ocr_data['width'][i] / 2.0
            h = ocr_data['height'][i] / 2.0
            
            bbox = fitz.Rect(x, y, x + w, y + h)
            
            # 페이지 번호는 제외
            if is_page_number(bbox, page_rect, text):
                continue
            
            # 제목은 제외
            if is_title(bbox, page_rect, text):
                continue
            
            # "고등학교"를 포함한 단어 찾기
            if "고등학교" in text:
                # 1페이지의 경우 이미 좌표로 처리되었으므로 스킵 (성능 최적화)
                if page_num != 1:
                    page.add_redact_annot(bbox, fill=(1, 1, 1))
                    masked_count += 1
            
            # 하단의 "반", "번호", "성명" 마스킹
            elif text in ["반", "번호", "성명"]:
                is_bottom = bbox.y0 > page_rect.height * 0.9
                if is_bottom:
                    # 레이블과 값을 포함하도록 확장
                    extended_rect = fitz.Rect(
                        bbox.x0 - 5,
                        bbox.y0 - 5,
                        min(bbox.x1 + 100, page_rect.width),
                        bbox.y1 + 5
                    )
                    page.add_redact_annot(extended_rect, fill=(1, 1, 1))
                    masked_count += 1
        
        return masked_count
        
    except Exception as e:
        st.warning(f"OCR 처리 중 오류 발생 (페이지 {page_num}): {str(e)}")
        return 0

def process_pdf(uploaded_file):
    """PDF 파일 처리 메인 함수"""
    # PDF 열기
    pdf_bytes = uploaded_file.read()
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    total_pages = len(pdf_document)
    
    # Tesseract 사용 가능 여부 확인
    has_tesseract = check_tesseract()
    if not has_tesseract:
        st.warning("⚠️ Tesseract OCR이 설치되지 않았습니다. 텍스트 인식 기능을 사용할 수 없으며, 좌표 기반 마스킹만 수행됩니다.")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 각 페이지 처리
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        current_page = page_num + 1
        
        status_text.text(f"처리 중: {current_page}/{total_pages} 페이지")
        
        if current_page == 1:
            # 1페이지: 고정 좌표 마스킹
            mask_page_1_fixed_coords(page)
        
        # 텍스트 검색 기반 마스킹 시도
        masked_count = mask_by_text_search(page, current_page, total_pages)
        
        # 텍스트 검색으로 마스킹된 항목이 적고, OCR 사용 가능한 경우
        if masked_count < 3 and has_tesseract and current_page != 1:
            # OCR 기반 마스킹 추가
            mask_by_ocr(page, current_page)
        
        # 마스킹 적용
        page.apply_redactions()
        
        # 진행률 업데이트
        progress_bar.progress((current_page) / total_pages)
    
    status_text.text("✅ 마스킹 처리 완료!")
    progress_bar.progress(1.0)
    
    # 처리된 PDF를 바이트로 저장
    output_bytes = pdf_document.write()
    pdf_document.close()
    
    return output_bytes

# ============================================
# Streamlit 앱 UI
# ============================================

def main():
    st.set_page_config(
        page_title="PDF 개인정보 마스킹",
        page_icon="🔒",
        layout="centered"
    )
    
    st.title("🔒 PDF 개인정보 마스킹 도구")
    st.markdown("""
    학교생활기록부 PDF에서 민감한 개인정보를 자동으로 마스킹합니다.
    
    **마스킹 대상:**
    - 1페이지: 사진, 인적사항 (이름, 주민번호, 주소 등)
    - 모든 페이지: 학교명, 하단의 반/번호/성명
    """)
    
    # Tesseract 설치 안내
    with st.expander("📋 Tesseract OCR 설치 안내"):
        st.markdown("""
        **Tesseract OCR**은 스캔된 PDF의 텍스트를 인식하는 데 필요합니다.
        
        **설치 방법:**
        - **Windows**: [Tesseract 설치 프로그램](https://github.com/UB-Mannheim/tesseract/wiki) 다운로드 후 설치
          - 설치 후 `main.py` 파일에서 경로 설정 필요
          - 예: `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`
        - **macOS**: `brew install tesseract tesseract-lang`
        - **Linux**: `sudo apt-get install tesseract-ocr tesseract-ocr-kor`
        
        **중요**: 한국어 데이터팩(kor)도 함께 설치해야 합니다!
        
        OCR이 설치되지 않은 경우, 좌표 기반 마스킹만 수행됩니다.
        """)
    
    # 파일 업로드
    uploaded_file = st.file_uploader(
        "PDF 파일을 업로드하세요 (최대 23페이지)",
        type=['pdf'],
        help="학교생활기록부 PDF 파일을 선택하세요"
    )
    
    if uploaded_file is not None:
        # 파일 정보 표시
        st.info(f"📄 파일명: {uploaded_file.name} ({uploaded_file.size:,} bytes)")
        
        # 처리 시작 버튼
        if st.button("🔒 마스킹 시작", type="primary"):
            try:
                with st.spinner("처리 중입니다..."):
                    # PDF 처리
                    output_bytes = process_pdf(uploaded_file)
                
                # 다운로드 버튼
                original_name = uploaded_file.name
                new_name = f"(제거됨){original_name}"
                
                st.success("✅ 마스킹이 완료되었습니다!")
                
                st.download_button(
                    label="📥 마스킹된 PDF 다운로드",
                    data=output_bytes,
                    file_name=new_name,
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                st.exception(e)
    
    # 사용 안내
    st.markdown("---")
    st.markdown("""
    **사용 방법:**
    1. PDF 파일을 업로드합니다
    2. '마스킹 시작' 버튼을 클릭합니다
    3. 처리가 완료되면 마스킹된 PDF를 다운로드합니다
    
    **주의사항:**
    - 모든 PDF는 A4 동일 양식이어야 합니다
    - 최대 23페이지까지 처리 가능합니다
    - 페이지 번호는 마스킹되지 않습니다
    """)

if __name__ == "__main__":
    main()
