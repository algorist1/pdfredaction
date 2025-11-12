import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO
# 비밀번호 설정
CORRECT_PASSWORD = "11261"
st.set_page_config(
    page_title="PDF 민감정보 제거",
    page_icon="🔒",
    layout="centered"
)# 로그인 상태 확인
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
# 로그인 페이지
if not st.session_state.logged_in:
    st.title("🔐 PDF 민감정보 자동 제거 접근 인증")
    st.markdown("### 학교 관계자 전용 시스템")
    st.warning("⚠ 승인된 사용자만 접근 가능합니다.")
    
    password = st.text_input("학교 CODE (5자리)를 입력하세요", type="password", max_chars=5)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔓 접속하기", use_container_width=True):
            if password == CORRECT_PASSWORD:
                st.session_state.logged_in = True
                st.success("✅ 인증 성공!")
                st.rerun()
            else:
                st.error("❌ CODE가 올바르지 않습니다.")
    
    st.divider()
    st.caption("🔒 이 시스템은 개인정보 보호를 위해 보안이 적용되어 있습니다.")
    st.stop()
# 로그아웃 버튼
col1, col2 = st.columns([5, 1])
with col2:
    if st.button("🚪 로그아웃"):
        st.session_state.logged_in = False
        st.rerun()
def redact_pdf(pdf_bytes):
    """PDF에서 민감정보를 제거하는 함수"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 첫 페이지 처리
        if page_num == 0:
            # 상단 표와 사진 영역만 제거 (제목은 제외, 약 12%~25%)
            rect1 = fitz.Rect(0, page.rect.height * 0.12, page.rect.width, page.rect.height * 0.25)
            page.add_redact_annot(rect1, fill=(1, 1, 1))
            
            # "1. 인적·학적사항" 섹션 제거 (대략적 위치)
            rect2 = fitz.Rect(0, page.rect.height * 0.25, page.rect.width, page.rect.height * 0.45)
            page.add_redact_annot(rect2, fill=(1, 1, 1))
        
        # 모든 페이지 하단 꼬리말 제거 (하단 8%)
        rect_footer = fitz.Rect(0, page.rect.height * 0.92, page.rect.width, page.rect.height)
        page.add_redact_annot(rect_footer, fill=(1, 1, 1))
        
        # 실제 제거 적용
        page.apply_redactions()
    
    # 수정된 PDF를 바이트로 저장
    output = BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)
    
    return output.getvalue()
# UI 구성
st.title("🔒 PDF 민감정보 자동 제거기")
st.markdown("학교 생활기록부의 개인정보를 안전하게 제거합니다~✂")
st.divider()
# 제거될 정보 안내
with st.expander("ℹ 자동으로 제거되는 정보", expanded=True):
    st.markdown("""
    - ✅ 첫 페이지 상단의 담임 정보 및 사진
    - ✅ 1. 인적·학적사항 전체
    - ✅ 모든 페이지 하단의 학교명 및 반/번호/성명
    """)
# 파일 업로드
uploaded_file = st.file_uploader(
    "PDF 파일을 업로드하세요",
    type=['pdf'],
    help="파일 크기 제한: 200MB")
if uploaded_file is not None:
    # 파일 정보 표시
    st.success(f"✅ {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")
    
    # 처리 버튼
    if st.button("🚀 민감정보 제거 시작", type="primary", use_container_width=True):
        with st.spinner("처리 중입니다... 잠시만 기다려주세요."):
            try:
                # PDF 읽기
                pdf_bytes = uploaded_file.read()
                
                # 민감정보 제거
                redacted_pdf = redact_pdf(pdf_bytes)
                
                # 성공 메시지
                st.success("✅ 처리가 완료되었습니다!")
                
                # 다운로드 버튼
                st.download_button(
                    label="📥 제거된 PDF 다운로드",
                    data=redacted_pdf,
                    file_name=f"제거됨_{uploaded_file.name}",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                st.info("PDF 형식이나 보안 설정을 확인해주세요.")
st.divider()
# 주의사항
st.caption("⚠ 처리된 파일을 다운로드한 후, 반드시 내용을 확인하세요.")
st.caption("💡 OCR이 차단된 PDF도 처리 가능합니다.")
st.caption("🔒 이 프로그램은 메모리에서만 작동하며 파일을 저장하지 않습니다.")
