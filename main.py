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
            
            # 페이지 크기 (비율 계산을 위해 사용)
            page_height = page.rect.height
            page_width = page.rect.width

            # --- 1페이지 특정 영역 마스킹 (표 내용은 삭제, 표 구조는 유지) ---
            if page_num == 0:
                # 1. 상단 첫번째 표: 사진, 반, 번호, 담임성명 내용 제거
                
                # 사진 영역 마스킹 (좌측 상단 - 더 넓게)
                photo_rect = fitz.Rect(
                    page_width * 0.025,  # x0
                    page_height * 0.038, # y0
                    page_width * 0.195,  # x1
                    page_height * 0.152  # y1
                )
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 반/번호/담임성명 내용 영역 (1, 2, 3학년 모두 포함)
                table_content_rect = fitz.Rect(
                    page_width * 0.32,   # x0 - 학과 열 이후부터
                    page_height * 0.053, # y0 - 1학년 줄 시작
                    page_width * 0.98,   # x1 - 우측 끝까지
                    page_height * 0.14   # y1 - 3학년 줄 끝
                )
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))
                
                # 2. 1. 인적·학적사항 표 내용 제거
                
                # 학생정보 영역 (성명, 성별, 주민등록번호 - 한 줄로)
                student_info_rect = fitz.Rect(
                    page_width * 0.13,   # x0 - 성명: 이후
                    page_height * 0.162, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.184  # y1
                )
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))
                
                # 주소 영역
                address_rect = fitz.Rect(
                    page_width * 0.09,   # x0 - 주소: 이후
                    page_height * 0.184, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.206  # y1
                )
                page.add_redact_annot(address_rect, fill=(1, 1, 1))
                
                # 학적사항 내용 영역 (3줄)
                academic_rect = fitz.Rect(
                    page_width * 0.13,   # x0
                    page_height * 0.224, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.257  # y1
                )
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # 특기사항 내용 영역
                notes_rect = fitz.Rect(
                    page_width * 0.13,   # x0
                    page_height * 0.272, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.325  # y1
                )
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))
                
            # --- "(고등학교)" 키워드 검색 및 마스킹 (기존 로직 유지) ---
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"] 
            
            for text in search_texts:
                text_instances = page.search_for(text)
                for inst in text_instances:
                    page.add_redact_annot(inst, fill=(1, 1, 1))

            # --- 모든 페이지 맨 하단의 개인정보 마스킹 ---
            
            # 1) 맨 위 작은 글씨 (학교명/날짜/IP/이름)
            footer_top_rect = fitz.Rect(
                0,                      # x0 - 좌측 끝부터
                0,                      # y0 - 맨 위
                page_width,             # x1 - 우측 끝까지
                page_height * 0.015     # y1
            )
            page.add_redact_annot(footer_top_rect, fill=(1, 1, 1))

            # 2) 맨 아래 큰 글씨 - "/" 기호
            footer_slash_rect = fitz.Rect(
                page_width * 0.015,     # x0
                page_height * 0.982,    # y0
                page_width * 0.035,     # x1
                page_height * 0.992     # y1
            )
            page.add_redact_annot(footer_slash_rect, fill=(1, 1, 1))
            
            # 3) 맨 아래 큰 글씨 - 반, 번호, 성명 내용
            footer_bottom_rect = fitz.Rect(
                page_width * 0.72,      # x0 - "반" 숫자부터
                page_height * 0.982,    # y0
                page_width,             # x1 - 우측 끝까지
                page_height * 0.992     # y1
            )
            page.add_redact_annot(footer_bottom_rect, fill=(1, 1, 1))

            # 실제 리댁션 적용 (내용 제거)
            page.apply_redactions()

        # 처리된 PDF를 바이트로 출력
        output_bytes = doc.tobytes()
        doc.close()
        return output_bytes

    except Exception as e:
        st.error(f"PDF 처리 중 오류가 발생했습니다: {e}")
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
