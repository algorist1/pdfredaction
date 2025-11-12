import streamlit as st
import fitz  # PyMuPDF
import io
from typing import List, Tuple


def inflate(rect: fitz.Rect, dx: float, dy: float) -> fitz.Rect:
    """사각형을 사방으로 살짝 키움(테두리 보호 위해 아주 소폭만)."""
    return fitz.Rect(rect.x0 - dx, rect.y0 - dy, rect.x1 + dx, rect.y1 + dy)


def redact_rects(page: fitz.Page, rects: List[fitz.Rect], fill=(1, 1, 1)):
    for r in rects:
        page.add_redact_annot(r, fill=fill)


def find_heading_y(page: fitz.Page, needles: List[str]) -> List[Tuple[str, float]]:
    """주어진 문자열(섹션 제목 등)의 첫 bbox y0를 찾아 반환."""
    found = []
    for t in needles:
        try:
            hits = page.search_for(t, hit_max=16)
        except Exception:
            hits = []
        if hits:
            found.append((t, min(h.y0 for h in hits)))
    return found


def redact_sensitive_info(input_pdf_bytes: bytes) -> bytes | None:
    """
    PDF의 민감정보를 (테두리/표선 보존하며) '내용만' 마스킹.
    - 1p 상단 표: 우측(반/번호/담임성명) 텍스트 블록들만 마스킹
    - 1p 사진: 상단 이미지 블록만 마스킹
    - 1. 인적·학적사항: 라벨 컬럼 제외, 내용 컬럼만 마스킹
    - "(고등학교)" 관련 검색 마스킹: 기존 유지
    - 모든 페이지 하단: 반/번호/성명 줄 + 아랫줄 소문구 마스킹
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            pw, ph = page.rect.width, page.rect.height

            # ========== 1) 1페이지 상단 첫 표 ==========
            if page_num == 0:
                rects_to_redact: List[fitz.Rect] = []

                # 1-a) 상단 40% 안의 이미지(증명사진)만 마스킹
                raw = page.get_text("rawdict")
                img_rects = []
                for blk in raw.get("blocks", []):
                    # block이 image이면 "type":1 또는 "image" 키를 가짐
                    if blk.get("type") == 1 or "image" in blk:
                        (x0, y0, x1, y1) = blk["bbox"]
                        r = fitz.Rect(x0, y0, x1, y1)
                        # 상단 40%에 있는 이미지만 (증명사진으로 가정)
                        if r.y0 < ph * 0.40:
                            img_rects.append(r)
                # 가장 오른쪽(증명사진)을 우선적으로 선택 (여러 이미지가 있어도 오른쪽 상단이 사진일 확률 높음)
                if img_rects:
                    img_rects.sort(key=lambda r: (r.x0, r.area), reverse=True)
                    # 약간 여유를 두되 테두리는 침범하지 않도록 소폭만 inflate
                    rects_to_redact.append(inflate(img_rects[0], pw * 0.004, ph * 0.004))

                # 1-b) 상단 첫 표의 우측(반/번호/담임/…) 텍스트 블록만 마스킹
                # 상단 영역을 0%~40%로 잡고, 우측 절반(x>0.45pw) 텍스트만 선택
                # 라벨/세로줄은 벡터라 그대로 남고, 텍스트 블록만 지워짐.
                blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
                for b in blocks:
                    x0, y0, x1, y1, text, *_ = b
                    if y0 < ph * 0.40 and x0 > pw * 0.45 and text.strip():
                        # 표 라인에 닿지 않게 아주 소폭만 확장
                        rects_to_redact.append(inflate(fitz.Rect(x0, y0, x1, y1), pw * 0.002, ph * 0.003))

                # 1-c) 1. 인적·학적사항 표: "1." ~ "2." 사이에서, 좌측 라벨열 제외 텍스트만 마스킹
                # 기준 y를 제목으로 자동 산출
                headings = find_heading_y(page, ["1.", "1. 인적", "1 . 인적", "2.", "2 .", "2. 출결상황"])
                y_1 = None
                y_2 = None
                for name, y in headings:
                    if name.startswith("1"):
                        y_1 = y
                    if name.startswith("2"):
                        y_2 = y
                # fallback: 대략적 위치
                if y_1 is None:
                    y_1 = ph * 0.42
                if y_2 is None:
                    y_2 = ph * 0.74

                # 라벨 컬럼 폭 (좌측 머리칸) 보존: x < 0.18pw는 건드리지 않음
                CONTENT_X_MIN = pw * 0.18
                # 인적·학적사항 범위 내의 텍스트 블록 중 내용 컬럼만 마스킹
                for b in blocks:
                    x0, y0, x1, y1, text, *_ = b
                    if (y0 >= y_1 - ph * 0.01) and (y1 <= y_2 + ph * 0.01) and text.strip():
                        if x0 >= CONTENT_X_MIN:
                            rects_to_redact.append(inflate(fitz.Rect(x0, y0, x1, y1), pw * 0.003, ph * 0.002))

                redact_rects(page, rects_to_redact)

            # ========== 2) "(고등학교)" 관련 검색 마스킹(유지) ==========
            for text in ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"]:
                try:
                    for inst in page.search_for(text):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    pass

            # ========== 3) 모든 페이지 하단 공통 영역 ==========
            # 상단 얇은 머리글(학교/날짜/IP/이름 등)
            page.add_redact_annot(fitz.Rect(0, 0, pw, ph * 0.015), fill=(1, 1, 1))

            # 하단 "/" 부근
            page.add_redact_annot(fitz.Rect(pw * 0.010, ph * 0.978, pw * 0.055, ph * 0.994), fill=(1, 1, 1))

            # 하단 우측 "반/번호/성명" 줄
            rb = fitz.Rect(pw * 0.60, ph * 0.977, pw * 0.995, ph * 0.996)
            page.add_redact_annot(inflate(rb, pw * 0.002, ph * 0.001), fill=(1, 1, 1))

            # 맨 아래 아주 얇은 작은 글씨 줄
            rs = fitz.Rect(pw * 0.58, ph * 0.996, pw * 0.995, ph * 1.000)
            page.add_redact_annot(inflate(rs, pw * 0.002, 0), fill=(1, 1, 1))

            # 실제 적용
            page.apply_redactions()

        out = doc.tobytes()
        doc.close()
        return out

    except Exception as e:
        st.error(f"PDF 처리 중 오류: {e}")
        return None


# ======================= Streamlit UI =======================
st.set_page_config(page_title="PDF 개인정보 보호 앱", page_icon="🔒")
st.title("🔒 PDF 민감정보 마스킹 앱")
st.write("상단 표/테두리는 유지하고, **내용(텍스트/사진)만** 동적으로 마스킹합니다.")
st.write("*(최대 23페이지 처리)*")

uploaded_file = st.file_uploader("PDF 파일 업로드", type=["pdf"])

if uploaded_file:
    data = uploaded_file.getvalue()
    with st.spinner("처리 중..."):
        out = redact_sensitive_info(data)
    if out:
        st.success("✅ 완료!")
        st.download_button(
            "처리된 PDF 다운로드",
            data=out,
            file_name=uploaded_file.name.replace(".pdf", "_masked.pdf"),
            mime="application/pdf",
        )
    else:
        st.error("❌ 처리 중 오류가 발생했습니다.")
