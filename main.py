import streamlit as st
import fitz  # PyMuPDF

def redact_sensitive_info(input_pdf_bytes):
    """
    PDF의 개인정보 영역(성명, 사진, 학적사항 등)을 좌표 기반으로 흰색으로 덮음.
    - 1페이지: 상단 첫 표(사진, 반, 번호, 담임성명)
    - 1페이지: '1. 인적·학적사항' 표의 성명, 성별, 주민번호, 주소, 학적사항, 특기사항
    - 모든 페이지 하단: 반, 번호, 성명 및 교사 이름 영역
    - "( )고등학교" 마스킹은 기존 로직 유지
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            page_height = page.rect.height
            page_width = page.rect.width

            # --- 1페이지 상단 첫 번째 표 ---
            if page_num == 0:
                # 사진 영역
                photo_rect = fitz.Rect(
                    page_width * 0.02,
                    page_height * 0.035,
                    page_width * 0.20,
                    page_height * 0.155
                )
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 반/번호/담임성명 등 내용 영역
                first_table_rect = fitz.Rect(
                    page_width * 0.30,
                    page_height * 0.05,
                    page_width * 0.98,
                    page_height * 0.145
                )
                page.add_redact_annot(first_table_rect, fill=(1, 1, 1))

                # --- 1. 인적·학적사항 표 ---
                # 성명·성별·주민등록번호
                personal_rect = fitz.Rect(
                    page_width * 0.13,
                    page_height * 0.162,
                    page_width * 0.98,
                    page_height * 0.184
                )
                page.add_redact_annot(personal_rect, fill=(1, 1, 1))

                # 주소
                address_rect = fitz.Rect(
                    page_width * 0.09,
                    page_height * 0.184,
                    page_width * 0.98,
                    page_height * 0.206
                )
                page.add_redact_annot(address_rect, fill=(1, 1, 1))

                # 학적사항
                academic_rect = fitz.Rect(
                    page_width * 0.13,
                    page_height * 0.224,
                    page_width * 0.98,
                    page_height * 0.257
                )
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # 특기사항
                special_rect = fitz.Rect(
                    page_width * 0.13,
                    page_height * 0.272,
                    page_width * 0.98,
                    page_height * 0.325
                )
                page.add_redact_annot(special_rect, fill=(1, 1, 1))

            # --- "(고등학교)" 키워드 마스킹 (기존 유지) ---
            search_texts = ["(", "고등학교"]
            for text in search_texts:
                for inst in page.search_for(text):
                    page.add_redact_annot(inst, fill=(1, 1, 1))

            # --- 모든 페이지 하단 개인정보 영역 ---
            # 상단 작은 글씨 (학교명/날짜/IP/이름)
            top_small_rect = fitz.Rect(
                0,
                0,
                page_width,
                page_height * 0.015
            )
            page.add_redact_annot(top_small_rect, fill=(1, 1, 1))

            # 하단 슬래시(“/” 구분) 근처
            slash_rect = fitz.Rect(
                page_width * 0.01,
                page_height * 0.98,
                page_width * 0.04,
                page_height * 0.993
            )
            page.add_redact_annot(slash_rect, fill=(1, 1, 1))

            # 반/번호/성명/교사 이름 포함 전체 하단 영역
            bottom_name_rect = fitz.Rect(
                page_width * 0.60,
                page_height * 0.978,
                page_width,
                page_height
            )
            page.add_redact_annot(bottom_name_rect, fill=(1, 1, 1))

            page.apply_redactions()

        output_bytes = doc.tobytes()
        doc.close()
        return output_bytes

    except Exception as e:
        st.error(f"PDF 처리 중 오류 발생: {e}")
        return None

# --- Streamlit 인터페이스 ---
st.set_page_config(page_title="PDF 개인정보 보호", page_icon="🧊")
st.title("🧊 학교생활기록부 개인정보 마스킹")
st.write("1페이지 상단 표, 인적·학적사항, 모든 페이지 하단의 성명/반/번호를 완전 마스킹합니다.")

uploaded = st.file_uploader("학교생활기록부 PDF 업로드", type=["pdf"])

if uploaded:
    st.info("파일 분석 및 개인정보 마스킹 중입니다...")
    result = redact_sensitive_info(uploaded.getvalue())
    if result:
        st.success("민감정보 마스킹이 완료되었습니다.")
        st.download_button("📄 마스킹된 PDF 다운로드", result, file_name=uploaded.name.replace(".pdf", "_masked.pdf"))
