import streamlit as st
import fitz  # PyMuPDF 라이브러리 (fitz로 import)
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os

# --------------------------------------------------------------------------
# [필수] Tesseract-OCR 경로 설정 (Windows 사용자)
# --------------------------------------------------------------------------
# Windows에서 Tesseract-OCR이 기본 경로에 설치되지 않은 경우, 아래 주석을 풀고
# tesseract.exe 파일의 실제 경로를 지정해야 합니다. (예: r'C:\Program Files\Tesseract-OCR\tesseract.exe')
# pytesseract.pytesseract.tesseract_cmd = r'' 
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# [규칙 1] 1페이지 고정 좌표 (BBOX) 변수
# A4 (595x842 pt) 기준이며, 예시 PDF 레이아웃을 기반으로 설정되었습니다.
# --------------------------------------------------------------------------
PAGE_1_BBOXES = [
    # 1. 사진 영역 (예시 이미지 기준)
    fitz.Rect(70, 65, 185, 215),
    
    # 2. 상단 표 (학년/반/번호/담임 값 영역) - 1, 2, 3학년 모두 포함
    # 1학년: 반/번호/담임
    fitz.Rect(370, 93, 405, 107), fitz.Rect(428, 93, 460, 107), fitz.Rect(480, 93, 560, 107),
    # 2학년: 반/번호/담임
    fitz.Rect(370, 110, 405, 124), fitz.Rect(428, 110, 460, 124), fitz.Rect(480, 110, 560, 124),
    # 3학년: 반/번호/담임
    fitz.Rect(370, 127, 405, 141), fitz.Rect(428, 127, 460, 141), fitz.Rect(480, 127, 560, 141),

    # 3. '1. 인적·학적사항' 표 (성명, 주민등록번호, 주소, 학적사항, 특기사항의 값 영역)
    fitz.Rect(115, 178, 560, 220), # 학생정보 (성명, 성별, 주민등록번호, 주소)
    fitz.Rect(115, 222, 560, 260), # 학적사항
    fitz.Rect(115, 262, 560, 280), # 특기사항
]

# --------------------------------------------------------------------------
# [규칙 2/3] 마스킹 대상 키워드 및 예외 영역
# --------------------------------------------------------------------------
# [규칙 2] 텍스트 검색 대상 키워드
KEYWORDS_TO_MASK = [
    "고등학교", # "( )고등학교"를 찾기 위한 핵심 키워드
    "반", 
    "번호", 
    "성명",
    "상명대학교사범대학부속여자고등학교장", 
    "대성고등학교" 
]

# 마스킹 제외 영역
TITLE_RECT = fitz.Rect(50, 20, 550, 50)  # 1페이지 상단 제목 제외 영역
PAGE_NUM_EXCLUSION_RECT = fitz.Rect(250, 800, 350, 842) # 중앙 하단 페이지 번호 제외 영역

# --------------------------------------------------------------------------
# 핵심 로직: PDF 마스킹 처리 함수
# --------------------------------------------------------------------------
def mask_pdf(input_pdf_stream):
    """PDF 스트림을 받아 하이브리드 방식으로 민감정보를 마스킹한 PDF의 바이트를 반환합니다."""
    
    try:
        # 1. 원본 PDF와 출력용 빈 PDF 문서 객체 생성
        doc = fitz.open(stream=input_pdf_stream.read(), filetype="pdf")
        output_doc = fitz.open()

        tesseract_available = True 
        ocr_warning_shown = False 

        # 2. 페이지 순회 (최대 23페이지 제한)
        for page_num, page in enumerate(doc):
            if page_num >= 23:
                break
            
            # **[수정]** 원본 페이지를 output_doc에 복사하고, 새로 추가된 페이지(new_page)를 참조
            # PyMuPDF에서 페이지를 복사하는 올바른 방법은 Document 객체의 insert_pdf 메서드를 사용하는 것입니다.
            output_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_page = output_doc[-1] # 새로 추가된 (가장 마지막) 페이지를 가져옵니다.

            # --- [규칙 1] 1페이지 고정 좌표 마스킹 ---
            if page_num == 0:
                for rect in PAGE_1_BBOXES:
                    new_page.add_redact_annot(rect, text=" ", fill=(1, 1, 1)) # 흰색 채우기

            # --- [규칙 2] 텍스트 검색 기반 마스킹 (디지털 PDF) ---
            text_instances = []
            # 1~2, 5~6 페이지와 모든 페이지 하단에서 키워드 검색
            is_relevant_page = (page_num <= 1) or (4 <= page_num <= 5) or True # 모든 페이지 하단
            
            if is_relevant_page:
                for keyword in KEYWORDS_TO_MASK:
                    # 텍스트를 검색하여 인스턴스(BBOX) 목록을 가져옴
                    text_instances.extend(new_page.search_for(keyword, quads=False))

            digital_text_found = bool(text_instances)

            for inst in text_instances:
                # 예외 처리: 제목 영역과 페이지 번호 영역은 마스킹하지 않음
                if (page_num == 0 and inst.intersects(TITLE_RECT)) or inst.intersects(PAGE_NUM_EXCLUSION_RECT):
                    continue
                
                # 1페이지의 경우, [규칙 1]의 고정 좌표 영역과 겹치면 중복 마스킹 방지
                if page_num == 0:
                    is_in_bbox = False
                    for bbox in PAGE_1_BBOXES:
                        # 텍스트 검색 결과가 고정 좌표 영역 안에 완전히 포함되면 중복 처리로 간주
                        if inst in bbox: 
                            is_in_bbox = True
                            break
                    if is_in_bbox:
                        continue
                
                new_page.add_redact_annot(inst, text=" ", fill=(1, 1, 1))

            # --- [규칙 3] OCR 기반 마스킹 (스캔된 PDF) ---
            # (디지털 텍스트 검색 결과가 거의 없고, Tesseract가 사용 가능한 경우)
            # 1페이지는 이미 [규칙 1]로 주요 인적사항 처리됨
            if not digital_text_found and page_num > 0 and tesseract_available:
                try:
                    # 페이지를 고해상도 이미지로 변환 (DPI 300)
                    pix = page.get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))

                    # OCR 실행 (한국어)
                    ocr_data = pytesseract.image_to_data(img, lang='kor', output_type=Output.DICT)
                    
                    # OCR 좌표(픽셀)를 PDF 좌표(pt)로 변환하기 위한 스케일 계산
                    scale_x = page.rect.width / img.width
                    scale_y = page.rect.height / img.height

                    for i in range(len(ocr_data['text'])):
                        conf = int(ocr_data['conf'][i])
                        text = ocr_data['text'][i].strip()
                        
                        # 신뢰도 50 이상이고, 마스킹 대상 키워드가 포함된 경우
                        if conf > 50 and text and any(k in text for k in KEYWORDS_TO_MASK):
                            
                            l, t, w, h = ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i]
                            # OCR 좌표를 PDF 좌표로 변환
                            bbox = fitz.Rect(l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y)

                            # 페이지 번호 영역 예외 처리
                            if bbox.intersects(PAGE_NUM_EXCLUSION_RECT):
                                continue
                            
                            new_page.add_redact_annot(bbox, text=" ", fill=(1, 1, 1))

                except pytesseract.TesseractNotFoundError:
                    tesseract_available = False
                    if not ocr_warning_shown:
                        st.warning("Tesseract-OCR이 감지되지 않았습니다. 스캔된 PDF의 마스킹(OCR)이 비활성화됩니다.")
                        ocr_warning_shown = True
                except Exception:
                    # 한국어 데이터팩 누락 등의 기타 OCR 오류
                    if not ocr_warning_shown:
                        st.warning(f"OCR 처리 중 오류 발생 (페이지 {page_num + 1}): 텍스트 인식 불가. Tesseract 설치 및 'kor' 데이터팩을 확인하세요.")
                        ocr_warning_shown = True
                    tesseract_available = False

            # 4. 해당 페이지의 모든 마스킹(Redaction Annotation)을 최종 적용
            new_page.apply_redactions()

        # 5. 마스킹 완료된 PDF를 바이트로 반환
        output_bytes = output_doc.tobytes()
        return output_bytes

    except Exception as e:
        # Streamlit 에러 출력 전에 문서 닫기
        if 'doc' in locals() and doc:
            doc.close()
        if 'output_doc' in locals() and output_doc:
            output_doc.close()
        # 오류 메시지 출력
        st.error(f"PDF 처리 중 예상치 못한 오류가 발생했습니다: {e}")
        return None
    finally:
        # 최종적으로 문서 닫기 (오류가 발생했더라도)
        if 'doc' in locals() and doc:
            doc.close()
        if 'output_doc' in locals() and output_doc:
            output_doc.close()


# --------------------------------------------------------------------------
# Streamlit UI 구성
# --------------------------------------------------------------------------

st.set_page_config(page_title="PDF 민감정보 마스킹", layout="wide")
st.title("🛡️ PDF 민감정보 자동 마스킹 앱 (학기록 용)")

# Tesseract-OCR 설치 안내
with st.expander("⚠️ Tesseract-OCR 설치 안내 (스캔 PDF 처리 필수)"):
    st.markdown("""
    스캔된(이미지) PDF를 처리하려면 **Tesseract-OCR 엔진**과 **한국어(kor) 데이터팩**이 시스템에 설치되어 있어야 합니다.
    
    * **Windows**: [Tesseract 공식 사이트](https://github.com/UB-Mannheim/tesseract/wiki)에서 설치 후, 설치 경로를 시스템 PATH에 추가하거나 코드 상단에 명시해야 합니다. **'Korean' 언어팩을 반드시 포함**하여 설치하세요.
    * **macOS (Homebrew)**: `brew install tesseract tesseract-lang`
    * **Linux (Ubuntu)**: `sudo apt-get install tesseract-ocr tesseract-ocr-kor`
    
    Tesseract가 없어도 **1페이지 고정 좌표 마스킹**과 **디지털 텍스트 마스킹**은 정상 작동합니다.
    """)

# 파일 업로드 인터페이스
uploaded_file = st.file_uploader(
    "민감정보를 제거할 PDF 파일을 업로드하세요 (최대 23페이지).",
    type=["pdf"]
)

if uploaded_file is not None:
    original_filename = uploaded_file.name
    
    # 마스킹 처리 실행
    with st.spinner(f"**{original_filename}** 파일을 분석하고 민감정보를 마스킹 중입니다..."):
        masked_pdf_bytes = mask_pdf(uploaded_file)
    
    if masked_pdf_bytes:
        st.success("✅ 마스킹 처리가 완료되었습니다!")
        
        # 다운로드 버튼
        new_filename = f"(제거됨){original_filename}"
        st.download_button(
            label="마스킹된 PDF 파일 다운로드",
            data=masked_pdf_bytes,
            file_name=new_filename,
            mime="application/pdf"
        )
