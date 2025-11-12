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
                # 1) 상단 첫 번째 표: 사진, 반/번호/담임성명 내용 제거

                # (A) 사진 영역 — 좌측 상단 박스 조금 더 넓게
                photo_rect = fitz.Rect(
                    page_width * 0.028,   # x0
                    page_height * 0.038,  # y0
                    page_width * 0.208,   # x1
                    page_height * 0.162   # y1
                )
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # (B) 반/번호/담임성명 내용 영역 — 표 오른쪽 절반 전체를 넉넉히 커버
                table_content_rect = fitz.Rect(
                    page_width * 0.52,    # x0
                    page_height * 0.052,  # y0
                    page_width * 0.985,   # x1
                    page_height * 0.150   # y1
                )
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))

                # 2) "1. 인적·학적사항" 표: 성명/성별/주민등록번호/주소/학적사항/특기사항 내용 제거

                # (C) 학생정보(성명·성별·주민등록번호) 라인 전체
                student_info_rect = fitz.Rect(
                    page_width * 0.125,   # x0
                    page_height * 0.162,  # y0
                    page_width * 0.985,   # x1
                    page_height * 0.193   # y1
                )
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))

                # (D) 주소 라인 전체
                address_rect = fitz.Rect(
                    page_width * 0.090,   # x0
                    page_height * 0.198,  # y0
                    page_width * 0.985,   # x1
                    page_height * 0.228   # y1
                )
                page.add_redact_annot(address_rect, fill=(1, 1, 1))

                # (E) 학적사항 내용
                academic_rect = fitz.Rect(
                    page_width * 0.125,   # x0
                    page_height * 0.232,  # y0
                    page_width * 0.985,   # x1
                    page_height * 0.268   # y1
                )
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # (F) 특기사항 내용
                notes_rect = fitz.Rect(
                    page_width * 0.125,   # x0
                    page_height * 0.274,  # y0
                    page_width * 0.985,   # x1
                    page_height * 0.335   # y1
                )
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))

            # --- "(고등학교)" 키워드 검색 및 마스킹 (기존 로직 유지) ---
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"] 
            
            for text in search_texts:
                try:
                    text_instances = page.search_for(text)
                    for inst in text_instances:
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    pass

            # --- 모든 페이지 맨 하단의 개인정보 마스킹 ---
            
            # (1) 페이지 최상단 얇은 머리글 (학교명/날짜/IP/이름)
            footer_top_rect = fitz.Rect(
                0, 0, page_width, page_height * 0.015
            )
            page.add_redact_annot(footer_top_rect, fill=(1, 1, 1))

            # (2) 하단 좌측 "/" 부근
            footer_slash_rect = fitz.Rect(
                page_width * 0.010,
                page_height * 0.978,
                page_width * 0.055,
                page_height * 0.994
            )
            page.add_redact_annot(footer_slash_rect, fill=(1, 1, 1))

            # (3) 하단 우측 "반/번호/성명" 영역
            footer_bottom_rect = fitz.Rect(
                page_width * 0.60,
                page_height * 0.977,
                page_width * 0.995,
                page_height * 0.996
            )
            page.add_redact_annot(footer_bottom_rect, fill=(1, 1, 1))

            # (4) 아주 아래 얇은 라인(작은 글씨)
            footer_bottom_hairline_rect = fitz.Rect(
                page_width * 0.58,
                page_height * 0.996,
                page_width * 0.995,
                page_height * 1.000
            )
            page.add_redact_annot(footer_bottom_hairline_rect, fill=(1, 1, 1))

            # 실제 리댁션 적용
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
