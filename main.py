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

            # --- 1페이지 특정 영역 마스킹 ---
            if page_num == 0:
                # 1. 사진 영역 (좌표는 예시 PDF 기반으로 추정)
                # (x0, y0, x1, y1)
                photo_rect = fitz.Rect(60, 60, 160, 180) 
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 2. 상단 표 (반, 번호, 담임성명)
                # (학년, 구분, 학과, 반, 번호, 담임성명)
                # 1학년
                page.add_redact_annot(fitz.Rect(350, 100, 550, 115), fill=(1, 1, 1)) 
                # 2학년
                page.add_redact_annot(fitz.Rect(350, 115, 550, 130), fill=(1, 1, 1))
                # 3학년
                page.add_redact_annot(fitz.Rect(350, 130, 550, 145), fill=(1, 1, 1))

                # 3. 1. 인적·학적사항 (성명, 성별, 주민등록번호, 주소)
                page.add_redact_annot(fitz.Rect(150, 200, 550, 250), fill=(1, 1, 1)) 
                
                # 4. 1. 인적·학적사항 (학적사항, 특기사항 내용)
                # 학적사항
                page.add_redact_annot(fitz.Rect(150, 250, 550, 300), fill=(1, 1, 1))
                # 특기사항
                page.add_redact_annot(fitz.Rect(150, 300, 550, 320), fill=(1, 1, 1))

            # --- "고등학교" 키워드 검색 및 마스킹 ---
            # "(  )고등학교" 또는 "대성고등학교" 등 구체적인 학교 이름
            # 예시 파일의 "대성고등학교"를 기준으로 검색
            # 1~2페이지 수상경력, 5~6페이지 봉사활동, 모든 페이지 하단
            
            # 검색할 텍스트 리스트
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교"] 
            
            for text in search_texts:
                text_instances = page.search_for(text)
                for inst in text_instances:
                    page.add_redact_annot(inst, fill=(1, 1, 1))

            # --- 모든 페이지 하단 (반, 번호, 성명) 마스킹 ---
            # (좌표는 예시 PDF 기반으로 추정)
            # 예: "반 7 번호 13 성명 박지호"
            footer_rect = fitz.Rect(300, 780, 550, 810) 
            page.add_redact_annot(footer_rect, fill=(1, 1, 1))

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
