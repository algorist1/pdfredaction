import streamlit as st
import fitz
from io import BytesIO
import time
import zipfile
import os
import json

MAX_ATTEMPTS = 5
LOCK_DURATION = 600  # 10분

LOCK_FILE = "lock_status.json"

st.set_page_config(
    page_title="PDF 민감정보 제거",
    page_icon="🔒",
    layout="centered"
)

# ---------------------------
# 서버 저장용 잠금 상태 관리
# ---------------------------
def load_lock_status():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                data = json.load(f)
                return data.get("lock_time")
        except:
            return None
    return None

def save_lock_status(lock_time):
    with open(LOCK_FILE, "w") as f:
        json.dump({"lock_time": lock_time}, f)

# ---------------------------
# 세션 상태 초기화
# ---------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'attempts' not in st.session_state:
    st.session_state.attempts = 0

# 서버 저장에서 잠금 시간 불러오기
if 'lock_time' not in st.session_state:
    st.session_state.lock_time = load_lock_status()

# CSS (기존 그대로)
hide_helpers_css = """
<style>
div[data-baseweb="input"] > div:nth-child(2),
div[data-testid="stTextInput"] div[role="presentation"] > div:nth-child(2),
div[data-testid="stTextInput"] small,
div[data-testid="stTextInput"] .css-1pbd9ic,
div[data-testid="stTextInput"] .css-1r6slb0,
div[role="group"] > div > label + div > div + div {
    display:none !important;
}

div.stButton > button:first-child {
    white-space: nowrap !important;
    height: auto !important;
    line-height: 1.2em !important;
}

.error-box{
    background-color:#F8D7DA;
    color:#842029;
    padding:0.45rem 0.6rem;
    border-radius:6px;
    border:1px solid #f5c2c7;
    font-size:0.95rem;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
    display:inline-block;
}

.success-box{
    background-color:#D1E7DD;
    color:#0F5132;
    padding:0.45rem 0.6rem;
    border-radius:6px;
    border:1px solid #badbcc;
    font-size:0.95rem;
    display:inline-block;
}
</style>
"""
st.markdown(hide_helpers_css, unsafe_allow_html=True)

# ---------------------------
# 로그인 화면
# ---------------------------
if not st.session_state.logged_in:
    st.title("🔐 PDF 민감정보 자동 제거 접근 인증")
    st.markdown("### 학교 관계자 전용 시스템")
    st.warning("⚠️ 승인된 사용자만 접근 가능합니다.")

    # 🔒 잠금 상태 유지 + 실시간 카운트다운
    if st.session_state.lock_time:
        elapsed = time.time() - st.session_state.lock_time
        if elapsed < LOCK_DURATION:
            remain = int(LOCK_DURATION - elapsed)
            minutes = remain // 60
            seconds = remain % 60
            st.error(f"🚫 5회 이상 잘못 입력하셨습니다. {minutes:02d}분 {seconds:02d}초 후, 다시 시도 가능합니다.")
            time.sleep(1)
            st.experimental_rerun()
        else:
            # 제한시간 종료 후 초기화
            st.session_state.lock_time = None
            st.session_state.attempts = 0
            save_lock_status(None)

    # 시도 횟수 표시
    attempts = min(st.session_state.attempts, MAX_ATTEMPTS)
    remaining = max(MAX_ATTEMPTS - attempts, 0)
    st.info(f"시도: {attempts}/{MAX_ATTEMPTS}    &    남은 시도: {remaining}")

    password = st.text_input(
        "학교 CODE(5자리)를 입력하세요",
        type="password",
        max_chars=5,
        label_visibility="visible",
        key="pw_input"
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔓 접속하기", use_container_width=True):
            # ✅ 이미 잠긴 상태면 즉시 차단
            if st.session_state.lock_time and (time.time() - st.session_state.lock_time) < LOCK_DURATION:
                st.error("🚫 접근이 제한되어 있습니다. 잠시 후 다시 시도해주세요.")
                st.stop()

            # ✅ 인증 성공
            CORRECT_PASSWORD = st.secrets.get("password")
            if password == CORRECT_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.attempts = 0
                st.success("✅ 인증 성공!")
                st.experimental_rerun()
            else:
                st.session_state.attempts += 1
                # ✅ 5번째 실패 시점에서만 문구 표시 + 잠금 시작
                if st.session_state.attempts >= MAX_ATTEMPTS:
                    st.session_state.lock_time = time.time()
                    save_lock_status(st.session_state.lock_time)  # 서버 저장
                    st.markdown(
                        '<div class="error-box">🚫 5회 이상 잘못 입력하여 10분간 접근이 제한됩니다.</div>',
                        unsafe_allow_html=True
                    )
                    time.sleep(1)
                    st.experimental_rerun()
                else:
                    st.markdown(
                        '<div class="error-box">❌ CODE가 올바르지 않습니다.</div>',
                        unsafe_allow_html=True
                    )

    st.divider()
    st.caption("⚠️ 5회 실패 시, <span style='color:red; text-decoration:underline;'>모든 사용자가 10분간 잠깁니다</span>.", unsafe_allow_html=True)
    st.caption("🔒 이 시스템은 개인정보 보호를 위해 보안이 적용되어 있습니다.")
    st.stop()

# ---------------------------
# 로그아웃 버튼
# ---------------------------
col1, col2 = st.columns([5, 1])
with col2:
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.experimental_rerun()

# ---------------------------
# PDF 민감정보 제거 함수
# ---------------------------
def redact_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        if page_num == 0:
            rect1 = fitz.Rect(0, page.rect.height * 0.12, page.rect.width, page.rect.height * 0.25)
            page.add_redact_annot(rect1, fill=(1, 1, 1))

            rect2 = fitz.Rect(0, page.rect.height * 0.25, page.rect.width, page.rect.height * 0.45)
            page.add_redact_annot(rect2, fill=(1, 1, 1))

        rect_footer = fitz.Rect(0, page.rect.height * 0.92, page.rect.width, page.rect.height)
        page.add_redact_annot(rect_footer, fill=(1, 1, 1))

        try:
            page.apply_redactions()
        except Exception:
            pass

    output = BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)
    return output.getvalue()

# ---------------------------
# PDF 처리 UI
# ---------------------------
st.title("🔒 PDF 민감정보 자동 제거기")
st.markdown("학교 생활기록부의 개인정보를 안전하게 제거합니다~✂️")

st.divider()

with st.expander("ℹ️ 자동으로 제거되는 정보", expanded=True):
    st.markdown("""
    - ✅ 첫 페이지 상단의 담임 정보 및 사진  
    - ✅ 1. 인적·학적사항 전체  
    - ✅ 모든 페이지 하단의 학교명 및 반/번호/성명
    """)

uploaded_files = st.file_uploader(
    "PDF 파일을 업로드하세요 (여러 개 선택 가능)",
    type=['pdf'],
    accept_multiple_files=True,
    help="Ctrl(또는 Cmd)을 누른 채로 여러 파일 선택 가능"
)

if uploaded_files:
    if len(uploaded_files) == 1:
        st.success(f"✅ {uploaded_files[0].name} ({uploaded_files[0].size / 1024 / 1024:.2f} MB)")
    else:
        st.success(f"✅ {len(uploaded_files)}개 파일 업로드됨")
        with st.expander("📋 업로드된 파일 목록", expanded=True):
            for i, file in enumerate(uploaded_files, 1):
                st.write(f"{i}. {file.name} ({file.size / 1024 / 1024:.2f} MB)")

    if st.button("🚀 민감정보 제거 시작", type="primary", use_container_width=True):
        with st.spinner("처리 중입니다..."):
            try:
                processed_files = {}
                
                for uploaded_file in uploaded_files:
                    pdf_bytes = uploaded_file.read()
                    redacted_pdf = redact_pdf(pdf_bytes)
                    new_filename = f"제거됨_{uploaded_file.name}"
                    processed_files[new_filename] = redacted_pdf
                
                st.success(f"✅ {len(processed_files)}개 파일 처리 완료!")
                
                if len(processed_files) == 1:
                    filename = list(processed_files.keys())[0]
                    pdf_data = processed_files[filename]
                    
                    st.download_button(
                        label=f"📥 {filename} 다운로드",
                        data=pdf_data,
                        file_name=filename,
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename, pdf_data in processed_files.items():
                            zip_file.writestr(filename, pdf_data)
                    
                    zip_buffer.seek(0)
                    
                    st.download_button(
                        label=f"📦 {len(processed_files)}개 파일 ZIP 다운로드",
                        data=zip_buffer.getvalue(),
                        file_name="제거됨_PDF파일들.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    
                    with st.expander("📋 다운로드될 파일 목록"):
                        for filename in processed_files.keys():
                            st.write(f"✅ {filename}")
                
            except Exception as e:
                st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                st.info("PDF 형식이나 보안 설정(암호, DRM 등)을 확인해주세요.")

st.divider()
st.caption("⚠️ 처리된 파일을 다운로드한 후, 반드시 내용을 확인하세요.")
st.caption("📦 2개 이상 파일은 자동으로 ZIP으로 다운로드됩니다.")
st.caption("🔒 이 프로그램은 메모리에서만 작동하며 파일을 저장하지 않습니다.")
