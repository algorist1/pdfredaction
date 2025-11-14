import streamlit as st
import fitz  # PyMuPDF
import re
from typing import List, Tuple


# -------------------- 유틸 --------------------
def border_safe_trim(rect: fitz.Rect, pw: float, ph: float,
                     pad_lr: float = 0.0010,   # 좌우 소폭 확장(글자 잔여 제거)
                     trim_tb: float = 0.0050   # 상하 크게 깎아 가로선 보존
                     ) -> fitz.Rect:
    """표 선을 건드리지 않도록, 위아래를 줄이고 좌우를 아주 살짝 늘린 사각형 반환."""
    dx = pw * pad_lr
    dy = ph * trim_tb
    x0 = rect.x0 - dx
    x1 = rect.x1 + dx
    y0 = rect.y0 + dy
    y1 = rect.y1 - dy
    if y1 <= y0:
        mid = (rect.y0 + rect.y1) / 2
        y0, y1 = mid - 0.15, mid + 0.15
    return fitz.Rect(x0, y0, x1, y1)


def inflate(rect: fitz.Rect, dx: float, dy: float) -> fitz.Rect:
    """선이 없는 영역(예: 사진)에서 여유를 주는 확장."""
    return fitz.Rect(rect.x0 - dx, rect.y0 - dy, rect.x1 + dx, rect.y1 + dy)


def redact_rects(page: fitz.Page, rects: List[fitz.Rect], fill=(1, 1, 1)):
    for r in rects:
        page.add_redact_annot(r, fill=fill)


def search_single_bbox(page: fitz.Page, text: str) -> fitz.Rect | None:
    hits = page.search_for(text, hit_max=64)
    if not hits:
        return None
    hits = sorted(hits, key=lambda r: (r.y0, r.x0))
    return hits[0]


def words_in_range(
    page: fitz.Page, y0: float, y1: float, x_min: float | None = None, x_max: float | None = None
) -> List[Tuple[float, float, float, float, str]]:
    """
    y 대역(필수) + 선택적 x 대역에 들어오는 단어 목록 반환.
    반환: (x0, y0, x1, y1, text)
    """
    words = page.get_text("words")  # (x0,y0,x1,y1,word, block_no, line_no, word_no)
    out: List[Tuple[float, float, float, float, str]] = []
    for w in words:
        x0, y0w, x1, y1w, txt = w[0], w[1], w[2], w[3], w[4]
        if (y1w >= y0) and (y0w <= y1):
            if (x_min is None or x1 >= x_min) and (x_max is None or x0 <= x_max):
                if str(txt).strip():
                    out.append((x0, y0w, x1, y1w, txt))
    return out


def union_rect_of_words(
    words: List[Tuple[float, float, float, float, str]], x_min: float | None = None, x_max: float | None = None
) -> List[fitz.Rect]:
    """같은 줄 단어들을 묶어 최소 bbox 리스트 생성. (x_min/x_max가 있으면 그 안쪽만 남김)"""
    if not words:
        return []
    words = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    lines: List[List[Tuple[float, float, float, float, str]]] = []
    for w in words:
        placed = False
        for line in lines:
            if abs(line[0][1] - w[1]) < 2.5:
                line.append(w); placed = True; break
        if not placed:
            lines.append([w])

    rects: List[fitz.Rect] = []
    for line in lines:
        xs0 = [w[0] for w in line]; ys0 = [w[1] for w in line]
        xs1 = [w[2] for w in line]; ys1 = [w[3] for w in line]
        r = fitz.Rect(min(xs0), min(ys0), max(xs1), max(ys1))
        if x_min is not None or x_max is not None:
            clip_x0 = r.x0 if x_min is None else max(r.x0, x_min)
            clip_x1 = r.x1 if x_max is None else min(r.x1, x_max)
            if clip_x1 > clip_x0:
                r = fitz.Rect(clip_x0, r.y0, clip_x1, r.y1)
            else:
                continue
        rects.append(r)
    return rects


# -------------------- 핵심 처리 --------------------
def redact_sensitive_info(input_pdf_bytes: bytes) -> bytes | None:
    """
    - 1페이지 첫 표: '반/번호/담임성명' 내용만 삭제(테두리/중간선 보존)
    - 1페이지 인적·학적사항: 학생정보(성명/성별/주민등록번호/주소) 내용만 삭제
    - 1페이지 학적사항: 두 줄 연도(예: 2023) 포함 내용 전체 삭제(‘202’ 잔여 방지 강화, 표선 보존)
    - '(고등학교)' 검색 마스킹 + 모든 페이지 하단:
        · 하단 표/날짜/이름 전체 삭제(표선까지 포함, 즉 완전 제거)
        · 단, '페이지수(예: 1 / 16)'만 정확히 보존
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            pw, ph = page.rect.width, page.rect.height

            # ---------------- A. 1페이지 ----------------
            if page_num == 0:
                # --- A1) 첫 표 열 경계 ---
                hdr_ban = search_single_bbox(page, "반")
                hdr_beonho = search_single_bbox(page, "번호")
                hdr_damim = search_single_bbox(page, "담임성명")
                top_anchor = search_single_bbox(page, "학년")
                sec1 = search_single_bbox(page, "1.")
                table_y_top = top_anchor.y0 if top_anchor else ph * 0.17
                table_y_bottom = (sec1.y0 - ph * 0.01) if sec1 else ph * 0.35

                x_ban = hdr_ban.x0 if hdr_ban else pw * 0.52
                x_beonho = hdr_beonho.x0 if hdr_beonho else pw * 0.63
                x_damim = hdr_damim.x0 if hdr_damim else pw * 0.75
                x_right = pw * 0.985

                words = words_in_range(page, table_y_top, table_y_bottom)

                # 반 열
                w_ban = [w for w in words if w[0] >= x_ban - pw*0.006 and w[2] <= x_beonho - pw*0.004]
                r_ban = union_rect_of_words(w_ban, x_min=x_ban + pw*0.002, x_max=x_beonho - pw*0.003)

                # 번호 열
                w_no = [w for w in words if w[0] >= x_beonho - pw*0.006 and w[2] <= x_damim - pw*0.004]
                r_no = union_rect_of_words(w_no, x_min=x_beonho + pw*0.002, x_max=x_damim - pw*0.003)

                # 담임성명 열
                w_dm = [w for w in words if w[0] >= x_damim - pw*0.006]
                r_dm = union_rect_of_words(w_dm, x_min=x_damim + pw*0.002, x_max=x_right - pw*0.003)

                safe_rects = [border_safe_trim(r, pw, ph) for r in (r_ban + r_no + r_dm)]
                redact_rects(page, safe_rects)

                # --- A2) 사진: 상단 40%의 가장 오른쪽 이미지 ---
                raw = page.get_text("rawdict")
                imgs: List[fitz.Rect] = []
                for blk in raw.get("blocks", []):
                    if blk.get("type") == 1 or "image" in blk:
                        x0, y0, x1, y1 = blk["bbox"]
                        r = fitz.Rect(x0, y0, x1, y1)
                        if r.y0 < ph * 0.40:
                            imgs.append(r)
                if imgs:
                    imgs.sort(key=lambda r: (r.x0, (r.width * r.height)), reverse=True)
                    page.add_redact_annot(inflate(imgs[0], pw*0.004, ph*0.004), fill=(1, 1, 1))

                # --- A3) 1. 인적·학적사항 ---
                title_1 = search_single_bbox(page, "1.")
                title_2 = search_single_bbox(page, "2.")
                y1_top = title_1.y0 if title_1 else ph * 0.42
                y1_bot = (title_2.y0 - ph * 0.01) if title_2 else ph * 0.74

                lab_name = search_single_bbox(page, "성명")
                lab_gender = search_single_bbox(page, "성별")
                lab_rrn = search_single_bbox(page, "주민등록번호")
                lab_addr = search_single_bbox(page, "주소")
                lab_acad = search_single_bbox(page, "학적사항")
                lab_extra = search_single_bbox(page, "특기사항")

                # 학생정보(성명/성별/주민번호) 라인: 라벨 오른쪽만
                if lab_name:
                    y0, y1 = lab_name.y0 - ph*0.006, lab_name.y1 + ph*0.006
                    line_words = words_in_range(page, y0, y1)
                    rects = []
                    if lab_name:
                        rects += union_rect_of_words([w for w in line_words if w[0] > lab_name.x1 + pw*0.004],
                                                     x_min=lab_name.x1 + pw*0.004)
                    if lab_gender:
                        rects += union_rect_of_words([w for w in line_words if w[0] > lab_gender.x1 + pw*0.004],
                                                     x_min=lab_gender.x1 + pw*0.004)
                    if lab_rrn:
                        rects += union_rect_of_words([w for w in line_words if w[0] > lab_rrn.x1 + pw*0.004],
                                                     x_min=lab_rrn.x1 + pw*0.004)
                    rects = [border_safe_trim(r, pw, ph) for r in rects]
                    redact_rects(page, rects)

                # 주소 라인
                if lab_addr:
                    ay0, ay1 = lab_addr.y0 - ph*0.006, lab_addr.y1 + ph*0.006
                    addr_words = words_in_range(page, ay0, ay1)
                    addr_rects = union_rect_of_words(
                        [w for w in addr_words if w[0] > lab_addr.x1 + pw*0.004],
                        x_min=lab_addr.x1 + pw*0.004
                    )
                    addr_rects = [border_safe_trim(r, pw, ph) for r in addr_rects]
                    redact_rects(page, addr_rects)

                # 학적사항(특기사항 전까지) — 라벨 오른쪽 전체 + 숫자라인 보강 + 표선 보존 하드-와이프
                if lab_acad:
                    y_top = lab_acad.y0 - ph*0.004
                    y_bot = (lab_extra.y0 - ph*0.004) if lab_extra else y1_bot

                    # ★ x_min을 더 붙게 조정: 라벨 바로 오른쪽부터 거의 즉시 스캔
                    acad_words = words_in_range(page, y_top, y_bot, x_min=lab_acad.x1 + pw * 0.0005)

                    # 1차: 전체 라인 마스킹(선 보존)
                    acad_rects = union_rect_of_words(acad_words, x_min=lab_acad.x1 + pw * 0.0005)
                    acad_rects = [border_safe_trim(r, pw, ph) for r in acad_rects]
                    redact_rects(page, acad_rects)

                    # 2차: 숫자 포함 라인 보강(좌우 더 크게 → '202' 잔여 제거)
                    numeric_words = [w for w in acad_words if re.fullmatch(r"\d{1,4}", str(w[4]).strip())]
                    if numeric_words:
                        num_line_rects = union_rect_of_words(numeric_words)
                        # ★ 좌우 여유를 강하게: 0.0080 (0.0060에서 증가)
                        num_line_rects = [border_safe_trim(r, pw, ph, pad_lr=0.0080, trim_tb=0.0028) for r in num_line_rects]
                        redact_rects(page, num_line_rects)

                    # 3차: 하드-와이프 — 각 줄의 마지막 글자보다 2% 오른쪽까지만 덮기(표 우측선 보존)
                    line_rects = union_rect_of_words(acad_words)  # 줄 단위 bbox들
                    hard_rects = []
                    for r in line_rects:
                        y0 = r.y0 + ph * 0.0015   # 위/아래 살짝 깎아 가로선 보호
                        y1 = r.y1 - ph * 0.0015
                        x0 = lab_acad.x1 + pw * 0.0005          # 라벨 바로 오른쪽부터
                        x1 = min(pw * 0.975, r.x1 + pw * 0.5)  # 마지막 글자보다 2% 더, 단 표선 안전선 0.975 이내
                        if y1 > y0 and x1 > x0:
                            hard_rects.append(fitz.Rect(x0, y0, x1, y1))
                    redact_rects(page, hard_rects)

            # ---------------- B. "(고등학교)" 등 검색 마스킹(유지) ----------------
            for t in ["대성고등학교", "상명대학교사범대학부속여자고등학교", "고등학교"]:
                try:
                    for inst in page.search_for(t):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    pass

            # ---------------- C. 모든 페이지 하단: 표/날짜/이름 완전 삭제 + 페이지수 보존 ----------------
            band_y0 = ph * 0.93
            band_y1 = ph * 1.00

            fwords = words_in_range(page, band_y0, band_y1)

            keep_rect = None
            for i, w in enumerate(fwords):
                if str(w[4]).strip() == "/":
                    sx = (w[0] + w[2]) / 2
                    same_line_nums = [ww for ww in fwords if abs(ww[1] - w[1]) < 3.0 and re.fullmatch(r"\d+", str(ww[4]).strip())]
                    same_line_nums.sort(key=lambda ww: abs(((ww[0] + ww[2]) / 2) - sx))
                    left = [ww for ww in same_line_nums if ((ww[0] + ww[2]) / 2) < sx]
                    right = [ww for ww in same_line_nums if ((ww[0] + ww[2]) / 2) >= sx]
                    keep = [left[0]] if left else []
                    if right:
                        keep.append(right[0])
                    keep.append(w)
                    xs0 = [r[0] for r in keep]; ys0 = [r[1] for r in keep]
                    xs1 = [r[2] for r in keep]; ys1 = [r[3] for r in keep]
                    margin_x = pw * 0.006
                    margin_y = ph * 0.004
                    keep_rect = fitz.Rect(min(xs0) - margin_x, min(ys0) - margin_y,
                                          max(xs1) + margin_x, max(ys1) + margin_y)
                    break

            if keep_rect is not None:
                left_rect = fitz.Rect(0, band_y0, max(keep_rect.x0, 0), band_y1)
                right_rect = fitz.Rect(min(keep_rect.x1, pw), band_y0, pw, band_y1)
                expand = ph * 0.002
                left_rect = fitz.Rect(left_rect.x0, max(0, left_rect.y0 - expand), left_rect.x1, min(band_y1, left_rect.y1 + expand))
                right_rect = fitz.Rect(right_rect.x0, max(0, right_rect.y0 - expand), right_rect.x1, min(band_y1, right_rect.y1 + expand))
                redact_rects(page, [left_rect, right_rect])
            else:
                redact_rects(page, [fitz.Rect(0, band_y0, pw, band_y1)])

            page.apply_redactions()

        out = doc.tobytes()
        doc.close()
        return out

    except Exception as e:
        st.error(f"PDF 처리 중 오류: {e}")
        return None


# -------------------- Streamlit UI --------------------
st.set_page_config(page_title="PDF 개인정보 보호 앱", page_icon="🔒")
st.title("🔒 PDF 민감정보 마스킹 앱")
st.write("상단 표/인적·학적사항(연도 포함)과 하단(표·날짜·이름)은 완전 삭제, 페이지수(예: 1 / 16)만 남깁니다.")
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
