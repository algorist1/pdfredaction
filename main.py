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
if 'lock_time' not in st.session_state:
    st.session_state.lock_time = load_lock_status()

# ---------------------------
# CSS
# ---------------------------
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
}
.success-box{
    background-color:#D1E7DD;
    color:#0F5132;
    padding:0.45rem 0.6rem;
    border-radius:6px;
    border:1px solid #badbcc;
    font-size:0.95rem;
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
    st.caption("빌드: 11261 / 입력 공백 자동 제거")

    # 🔒 잠금 상태 유지 + 실시간 카운트다운
    if st.session_state.lock_time:
        elapsed = time.time() - st.session_state.lock_time
        if elapsed < LOCK_DURATION:
            remain = int(LOCK_DURATION - elapsed)
            minutes = remain // 60
            seconds = remain % 60
            st.error(f"🚫 5회 이상 잘못 입력하셨습니다. {minutes:02d}분 {seconds:02d}초 후 다시 시도 가능.")
            st.stop()
        else:
            st.session_state.lock_time = None
            st.session_state.attempts = 0
            save_lock_status(None)

    attempts = min(st.session_state.attempts, MAX_ATTEMPTS)
    remaining = max(MAX_ATTEMPTS - attempts, 0)
    st.info(f"시도: {attempts}/{MAX_ATTEMPTS}    &    남은 시도: {remaining}")

    # 입력(가운데 공백까지 제거하기 위해 안내)
    password_raw = st.text_input(
        "학교 CODE(5자리)를 입력하세요",
        type="password",
        max_chars=10,     # 공백이 섞여도 입력 가능하도록 여유
        key="pw_input"
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔓 접속하기", use_container_width=True):
            # ✅ 인증코드: 11261 기본 + (배포 환경에 secrets 가 있으면) 그것도 허용
            allowed = {"11261"}
            try:
                secret_pw = st.secrets.get("password")
                if secret_pw:
                    allowed.add(str(secret_pw).strip())
            except Exception:
                pass

            # 공백/안 보이는 문자 제거
            pw = (password_raw or "").strip().replace(" ", "")

            if pw in allowed:
                st.session_state.logged_in = True
                st.session_state.attempts = 0
                st.success("✅ 인증 성공!")
                st.experimental_rerun()
            else:
                st.session_state.attempts += 1
                if st.session_state.attempts >= MAX_ATTEMPTS:
                    st.session_state.lock_time = time.time()
                    save_lock_status(st.session_state.lock_time)
                    st.markdown(
                        '<div class="error-box">🚫 5회 이상 잘못 입력하여 10분간 접근이 제한됩니다.</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        '<div class="error-box">❌ CODE가 올바르지 않습니다.</div>',
                        unsafe_allow_html=True
                    )

    st.divider()
    st.caption("⚠️ 5회 실패 시, 모든 사용자가 10분간 잠깁니다.")
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
# PDF 민감정보 제거 함수 (제목 보존 / 하단 완전 덮기)
# ---------------------------
def mm(val):
    return val * 72.0 / 25.4  # mm → point

def redact_pdf(pdf_bytes):
    title_keywords = [
        "학교생활세부사항기록부(학교생활기록부II)",
        "학교생활세부사항기록부",
        "학교생활기록부II"
    ]
    start_sec1_keywords = ["1. 인적·학적사항", "1. 인적ㆍ학적사항", "1. 인적?학적사항"]
    start_sec2_keywords = ["2. 출결상황", "2. 출결 현황", "2. 출결상황 "]

    pad = mm(2)          # 제목 주변 여유 2mm
    footer_h = mm(17)    # 하단 15mm + 여유 2mm

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_rect = page.rect

        # --- 모든 페이지: 하단 반/번호/성명 완전 덮기 ---
        footer_rect = fitz.Rect(0, max(0, page_rect.height - footer_h), page_rect.width, page_rect.height)
        page.add_redact_annot(footer_rect, fill=(1, 1, 1))

        # --- 1쪽 전용 처리 ---
        if page_num == 0:
            # 1) 제목 위치 탐지
            title_rects = []
            for key in title_keywords:
                try:
                    title_rects += page.search_for(key)
                except Exception:
                    pass
            title_box = sorted(title_rects, key=lambda r: r.y0)[0] if title_rects else None

            # 2) 제목 윗부분(담임/사진 등) 덮기 - 제목은 보존
            if title_box is not None:
                top_rect = fitz.Rect(0, 0, page_rect.width, max(0, title_box.y0 - pad))
                if top_rect.height > 0:
                    page.add_redact_annot(top_rect, fill=(1, 1, 1))
            else:
                # 제목을 못 찾으면 상단 10%만 덮어 제목 훼손 최소화
                safe_top = fitz.Rect(0, 0, page_rect.width, page_rect.height * 0.10)
                page.add_redact_annot(safe_top, fill=(1, 1, 1))

            # 3) '1. 인적·학적사항' 블록 덮기 (가능하면 '2. 출결상황' 직전까지)
            sec1_rects, sec2_rects = [], []
            for key in start_sec1_keywords:
                try:
                    sec1_rects += page.search_for(key)
                except Exception:
                    pass
            for key in start_sec2_keywords:
                try:
                    sec2_rects += page.search_for(key)
                except Exception:
                    pass

            if sec1_rects:
                sec1_box = sorted(sec1_rects, key=lambda r: r.y0)[0]
                if sec2_rects:
                    sec2_box = sorted(sec2_rects, key=lambda r: r.y0)[0]
                    y0 = max(0, sec1_box.y0 - pad)
                    y1 = min(page_rect.height, sec2_box.y0 - mm(1))
                    if y1 > y0:
                        page.add_redact_annot(fitz.Rect(0, y0, page_rect.width, y1), fill=(1, 1, 1))
                else:
                    y0 = (title_box.y1 + pad) if title_box is not None else page_rect.height * 0.12
                    y1 = page_rect.height * 0.45
                    if y1 > y0:
                        page.add_redact_annot(fitz.Rect(0, y0, page_rect.width, y1), fill=(1, 1, 1))
            else:
                y0 = (title_box.y1 + pad) if title_box is not None else page_rect.height * 0.12
                y1 = page_rect.height * 0.45
                if y1 > y0:
                    page.add_redact_annot(fitz.Rect(0, y0, page_rect.width, y1), fill=(1, 1, 1))

        # 실제 마스킹 적용
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
    - ✅ 첫 페이지 상단의 담임 정보 및 사진(제목 **보존**)  
    - ✅ 1. 인적·학적사항 전체  
    - ✅ 모든 페이지 하단의 학교명 및 반/번호/성명(하단 15mm + 여유 2mm)
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
