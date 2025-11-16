import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os

# --------------------------------------------------------------------------
# [중요] Tesseract-OCR 경로 설정 (Windows 사용자)
# --------------------------------------------------------------------------
# Windows에 Tesseract-OCR을 기본 경로가 아닌 곳에 설치한 경우,
# 아래 주석을 풀고 실제 tesseract.exe 파일의 경로를 지정해야 합니다.
# 예:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# [규칙 1] 1페이지 고정 좌표 (BBOX) 리스트 (x0, y0, x1, y1)
# A4 (595x842 pt) 기준이며, 예시 PDF 레이아웃을 기반으로 합니다.
# --------------------------------------------------------------------------
PAGE_1_BBOXES = [
    # 1. 사진 영역
    fitz.Rect(70, 65, 185, 215),
    
    # 2. 상단 표 (학년/반/번호/담임 값 영역)
    # 1학년
    fitz.Rect(370, 93, 405, 107),  # 반
    fitz.Rect(428, 93, 460, 107),  # 번호
    fitz.Rect(480, 93, 560, 107),  # 담임
    # 2학년
    fitz.Rect(370, 110, 405, 124), # 반
    fitz.Rect(428, 110, 460, 124), # 번호
    fitz.Rect(480, 110, 560, 124), # 담임
    # 3학년
    fitz.Rect(370, 127, 405, 141), # 반
    fitz.Rect(428, 127, 460, 141), # 번호
    fitz.Rect(480, 127, 560, 141), # 담임

    # 3. '1. 인적·학적사항' 표 (값 영역)
    fitz.Rect(115, 178, 560, 220), # 학생정보 (성명, 성별, 주민등록번호, 주소)
    fitz.Rect(115, 222, 560, 260), # 학적사항
    fitz.Rect(115, 262, 560, 280), # 특기사항
]

# --------------------------------------------------------------------------
# [규칙 2/3] 예외 처리용 고정 좌표
# --------------------------------------------------------------------------
# 1. 마스킹 제외: 1페이지 상단 제목
TITLE_RECT = fitz.Rect(50, 20, 550, 50)  # "학교생활세부사항기록부(학교생활기록부II)"

# 2. 마스킹 제외: 중앙 하단 페이지 번호 (쪽 번호)
PAGE_NUM_EXCLUSION_RECT = fitz.Rect(250, 800, 350, 842) # 중앙 하단 영역

# 3. 마스킹 대상 키워드
# (참고: 예시 파일의 '상명대학교사범대학부속여자고등학교장'은 마스킹 대상이 아니었으나,
# '대성고등학교'는 마스킹 대상이었습니다. 요구사항에 따라 "( )고등학교"를 포함하는
# 예시 PDF의 키워드를 추가했습니다.)
KEYWORDS_TO_MASK = [
    "대성고등학교", 
    "상명대학교사범대학부속여자고등학교장", # '고등학교'가 포함된 수여기관
    "반", 
    "번호", 
    "성명"
]

# OCR 마스킹 대상 키워드 (OCR은 "고등학교"만 포함해도 "대성고등학교" 등을 찾음)
OCR_KEYWORDS = ["고등학교", "반", "번호", "성명"]

# --------------------------------------------------------------------------
# 핵심: PDF 마스킹 처리 함수
# --------------------------------------------------------------------------
def mask_pdf(input_pdf_stream):
    """
    PDF 파일 스트림을 받아 민감정보를 마스킹한 PDF의 바이트를 반환합니다.
    하이브리드 방식 (좌표 + 텍스트 검색 + OCR) 사용
    """
    try:
        # 1. 원본 PDF 열기 (스트림에서)
        doc = fitz.open(stream=input_pdf_stream.read(), filetype="pdf")
        
        # 2. 마스킹된 내용을 담을 새 PDF (사본) 생성
        output_doc = fitz.open()

        tesseract_available = True # Tesseract-OCR 사용 가능 여부 플래그
        ocr_warning_shown = False # OCR 경고 표시 여부

        # 3. 페이지 순회 (최대 23페이지 제한)
        for page_num, page in enumerate(doc):
            if page_num >= 23:
                break
            
            # 원본 페이지를 사본 PDF에 복사
            new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_pdf(doc, from_page=page_num, to_page=page_num)

            # [규칙 1] 1페이지 - 고정 좌표(BBOX) 기반 마스킹
            if page_num == 0:
                for rect in PAGE_1_BBOXES:
                    new_page.add_redact_annot(rect, text=" ", fill=(1, 1, 1)) # 흰색 채우기

            # [규칙 2] 텍스트 검색 기반 마스킹 (디지털 PDF용)
            text_instances = []
            for keyword in KEYWORDS_TO_MASK:
                text_instances.extend(new_page.search_for(keyword, quads=False))

            digital_text_found = bool(text_instances)

            for inst in text_instances:
                # 예외 1: 1페이지 제목은 마스킹하지 않음
                if page_num == 0 and inst.intersects(TITLE_RECT):
                    continue
                
                # 예외 2: 중앙 하단 페이지 번호(쪽 번호)는 마스킹하지 않음
                if inst.intersects(PAGE_NUM_EXCLUSION_RECT):
                    continue
                
                # 예외 3: 1페이지의 고정 좌표 영역은 이미 처리했으므로 중복 제외
                if page_num == 0:
                    is_in_bbox = False
                    for bbox in PAGE_1_BBOXES:
                        if inst.intersects(bbox):
                            is_in_bbox = True
                            break
                    if is_in_bbox:
                        continue
                
                new_page.add_redact_annot(inst, text=" ", fill=(1, 1, 1))

            # [규칙 3] OCR 기반 마스킹 (스캔된 PDF용)
            # (1페이지가 아니고, 디지털 텍스트를 거의 찾지 못했으며, Tesseract가 사용 가능한 경우)
            if not digital_text_found and page_num > 0 and tesseract_available:
                try:
                    # 페이지를 고해상도 이미지로 변환 (DPI 300)
                    pix = page.get_pixmap(dpi=300)
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))

                    # OCR 실행 (한국어)
                    ocr_data = pytesseract.image_to_data(img, lang='kor', output_type=Output.DICT)
                    
                    num_items = len(ocr_data['text'])
                    
                    # OCR 결과를 PDF 좌표로 변환하기 위한 스케일 계산
                    scale_x = page.rect.width / img.width
                    scale_y = page.rect.height / img.height

                    for i in range(num_items):
                        conf = int(ocr_data['conf'][i])
                        text = ocr_data['text'][i].strip()

                        # 신뢰도 50 이상이고 텍스트가 있는 경우
                        if conf > 50 and text:
                            for keyword in OCR_KEYWORDS:
                                if keyword in text:
                                    # OCR 좌표(px)를 PDF 좌표(pt)로 변환
                                    l, t, w, h = ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i]
                                    bbox = fitz.Rect(l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y)

                                    # 예외: 중앙 하단 페이지 번호(쪽 번호)는 마스킹하지 않음
                                    if bbox.intersects(PAGE_NUM_EXCLUSION_RECT):
                                        continue
                                    
                                    new_page.add_redact_annot(bbox, text=" ", fill=(1, 1, 1))
                                    break # 이 단어는 마스킹했으므로 다음 단어로 이동

                except pytesseract.TesseractNotFoundError:
                    # Tesseract가 설치되지 않은 경우
                    tesseract_available = False # 플래그 변경
                    if not ocr_warning_shown:
                        st.warning("Tesseract-OCR이 감지되지 않았습니다. 스캔된 PDF의 텍스트 마스킹(OCR)이 비활성화됩니다.")
                        ocr_warning_shown = True
                except Exception as e:
                    # 기타 OCR 오류 (예: 한국어 데이터팩 없음)
                    if not ocr_warning_shown:
                        st.warning(f"OCR 처리 중 오류 발생 (페이지 {page_num + 1}): {e}\n"
                                 f"Tesseract-OCR이 올바르게 설치되었는지, 'kor' 언어 데이터팩이 있는지 확인하세요.")
                        ocr_warning_shown = True
                    tesseract_available = False # 오류 발생 시 해당 세션에서 OCR 중지

            # 4. 해당 페이지의 모든 마스킹 적용
            new_page.apply_redactions()

        # 5. 마스킹 완료된 PDF를 바이트로 저장
        output_bytes = output_doc.tobytes()
        
        return output_bytes

    except Exception as e:
        st.error(f"PDF 처리 중 오류가 발생했습니다: {e}")
        return None
    finally:
        if 'doc' in locals() and doc:
            doc.close()
        if 'output_doc' in locals() and output_doc:
            output_doc.close()

# --------------------------------------------------------------------------
# Streamlit 웹 앱 UI 구성
# --------------------------------------------------------------------------

st.set_page_config(page_title="PDF 민감정보 마스킹", layout="wide")
st.title("📄 PDF 민감정보 마스킹 (학교생활기록부)")
st.info("이 앱은 PDF 내 민감정보(사진, 인적사항, 학교명, 하단정보 등)를 마스킹합니다.")

# Tesseract-OCR 설치 안내 (별도 섹션)
with st.expander("⚠️ [필독] Tesseract-OCR 설치 안내 (스캔 PDF 처리를 위한 필수 사항)"):
    st.markdown("""
    이 앱이 스캔된(이미지) PDF의 텍스트를 인식하고 마스킹하려면 **Tesseract-OCR 엔진**과 **한국어(kor) 데이터팩**이 시스템에 설치되어 있어야 합니다.
    
    1.  **Windows**:
        * [여기(클릭)](https://github.com/UB-Mannheim/tesseract/wiki)에서 최신 설치 프로그램(예: `tesseract-ocr-w64-setup-v5.x.x.exe`)을 다운로드하여 설치합니다.
        * **[매우 중요]** 설치 과정 중 "Additional language data" 섹션에서 **'Korean' (한국어)**을 반드시 체크하여 함께 설치해야 합니다.
        * 설치 시 "Add Tesseract to system PATH" 옵션을 체크하는 것이 좋습니다.
    
    2.  **macOS** (Homebrew 사용):
        ```bash
        brew install tesseract tesseract-lang
        ```
        (위 명령어는 한국어(`kor`)를 포함한 모든 언어팩을 설치합니다.)

    3.  **Linux** (Ubuntu/Debian 기준):
        ```bash
        sudo apt-get install tesseract-ocr tesseract-ocr-kor
        ```
    
    **설치 후:** 앱이 Tesseract를 찾지 못하면 **Streamlit 앱을 재시작**해야 할 수 있습니다.
    
    **참고:** Tesseract-OCR이 설치되지 않아도, **[규칙 1]의 1페이지 고정 좌표 마스킹**과 **[규칙 2]의 디지털 텍스트 마스킹**은 정상적으로 작동합니다.
    """)

# 1. 파일 업로드
uploaded_file = st.file_uploader(
    "민감정보를 제거할 PDF 파일을 업로드하세요 (최대 23페이지).",
    type=["pdf"]
)

if uploaded_file is not None:
    # 파일명 확인
    original_filename = uploaded_file.name
    
    # 2. 마스킹 처리
    with st.spinner("PDF를 분석하고 민감정보를 마스킹 중입니다... (OCR이 필요한 경우 시간이 다소 걸릴 수 있습니다)"):
        masked_pdf_bytes = mask_pdf(uploaded_file)
    
    if masked_pdf_bytes:
        st.success("✅ 마스킹 처리가 완료되었습니다!")
        
        # 3. 결과 다운로드
        new_filename = f"(제거됨){original_filename}"
        st.download_button(
            label="마스킹된 PDF 파일 다운로드",
            data=masked_pdf_bytes,
            file_name=new_filename,
            mime="application/pdf"
        )
