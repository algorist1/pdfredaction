import streamlit as st
import fitz  # PyMuPDF
import io

def redact_sensitive_info(input_pdf_bytes):
    """
    PDF 파일의 민감 정보를 찾아 흰색 사각형으로 덮어씁니다.
    (PyMuPDF의 Redaction 기능을 사용하여 내용을 실제로 제거합니다)

    요청된 좌표 기반 마스킹 및 텍스트 검색 기반 마스킹을 수행합니다.
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        
        # 처리할 페이지 수 제한 (최대 23페이지)
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]

            # --- 1페이지 특정 영역 마스킹 (표 내용은 삭제, 표 구조는 유지) ---
            if page_num == 0:
                # 1. 상단 표: 반, 번호, 담임성명, 사진 내용만 제거
                # 사진 영역 (좌표는 30713 박지호.pdf 기준, 폭이 좁은 영역)
                # x0=60, y0=60, x1=160, y1=180
                photo_rect = fitz.Rect(page.rect.width * 0.12, page.rect.height * 0.07, page.rect.width * 0.3, page.rect.height * 0.22)
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 반/번호/담임성명 (내용이 들어가는 우측 영역만 제거)
                # y-axis for 1, 2, 3학년
                y_start = page.rect.height * 0.12  # 약 12%
                y_end = page.rect.height * 0.21   # 약 21%
                x_start = page.rect.width * 0.45  # 내용 시작점 (예상)
                x_end = page.rect.width * 0.9     # 끝까지
                
                rect_top_table_content = fitz.Rect(x_start, y_start, x_end, y_end)
                page.add_redact_annot(rect_top_table_content, fill=(1, 1, 1))
                
                
                # 2. 1. 인적·학적사항 표 내용만 제거
                # 성명, 성별, 주민등록번호, 주소, 학적사항, 특기사항의 "내용"이 들어가는 부분
                # 왼쪽 레이블('성명', '주소' 등)은 그대로 두고, 오른쪽 데이터 필드만 제거

                # '학생정보' 및 '주소' 내용 영역
                y_info_start = page.rect.height * 0.24 # 약 24%
                y_info_end = page.rect.height * 0.31  # 약 31%
                x_content_start = page.rect.width * 0.25 # 내용 시작점
                x_content_end = page.rect.width * 0.9   # 끝까지

                rect_info_content = fitz.Rect(x_content_start, y_info_start, x_content_end, y_info_end)
                page.add_redact_annot(rect_info_content, fill=(1, 1, 1))
                
                # '학적사항' 내용 영역
                y_h_start = page.rect.height * 0.32
                y_h_end = page.rect.height * 0.40
                rect_h_content = fitz.Rect(x_content_start, y_h_start, x_content_end, y_h_end)
                page.add_redact_annot(rect_h_content, fill=(1, 1, 1))

                # '특기사항' 내용 영역
                y_s_start = page.rect.height * 0.40
                y_s_end = page.rect.height * 0.45
                rect_s_content = fitz.Rect(x_content_start, y_s_start, x_content_end, y_s_end)
                page.add_redact_annot(rect_s_content, fill=(1, 1, 1))

            # --- "고등학교" 키워드 검색 및 마스킹 ---
            # (요청대로 이 부분은 유지됩니다. 학교 이름 텍스트 자체를 찾아서 제거)
            # 1~2페이지 수상경력, 5~6페이지 봉사활동, 모든 페이지 하단에 위치한 학교 이름 제거
            
            # 검색할 텍스트 리스트
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교"] 
            
            for text in search_texts:
                # 텍스트를 찾아 해당 영역을 마스킹합니다.
                text_instances = page.search_for(text)
                for inst in text_instances:
                    page.add_redact_annot(inst, fill=(1, 1, 1))

            # --- 모든 페이지 하단 꼬리말 제거 (삭제 요청이 있었으나, '그대로 둔다'로 최종 요청 변경) ---
            # 맨 하단 꼬리말 제거 코드는 최종 요청에 따라 삭제합니다.
            
            # 실제 리댁션 적용 (내용 제거)
            page.apply_redactions()

        # 처리된 PDF를 바이트로 출력
        output_bytes = doc.tobytes()
        doc.close()
        return output_bytes

    except Exception as e:
        st.error(f"PDF 처리 중 오류가 발생했습니다: {e}")
        # 오류 발생 시 원본 바이트 반환 (또는 None)
        return None


# --- Streamlit 앱 UI ---

st.set_page_config(page_title="PDF 개인정보 보호 앱", page_icon="🔒")

st.title("🔒 PDF 민감정보 마스킹 앱")
st.write("학교생활기록부 PDF 파일을 업로드하면, 민감정보(사진, 성명, 주소, 학교명 등)를 제거한 새 PDF 파일을 생성합니다.")
st.write("*(최대 23페이지까지 처리됩니다)*")

uploaded_file = st.file_uploader("PDF 파일 업로드 (23페이지 이내)", type=["pdf"])

if uploaded_file is not None:
    # 파일 읽기
    input_pdf_bytes = uploaded_file.getvalue()
    
    st.write("파일을 성공적으로 업로드했습니다. 민감정보를 처리 중입니다...")

    # 민감정보 처리 함수 호출
    with st.spinner('민감정보 마스킹 작업 진행 중...'):
        redacted_pdf_bytes = redact_sensitive_info(input_pdf_bytes)

    if redacted_pdf_bytes:
        st.success("민감정보 처리가 완료되었습니다!")
        
        # 원본 파일 이름에서 새 파일 이름 생성
        original_filename = uploaded_file.name
        if original_filename.endswith(".pdf"):
            new_filename = original_filename.replace(".pdf", "_masked.pdf")
        else:
            new_filename = f"{original_filename}_masked.pdf"

        st.download_button(
            label="처리된 PDF 파일 다운로드",
            data=redacted_pdf_bytes,
            file_name=new_filename,
            mime="application/pdf"
        )
    else:
        st.error("파일 처리 중 오류가 발생하여 다운로드할 수 없습니다.")
