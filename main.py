import streamlit as st
import fitz  # PyMuPDF
from typing import List, Tuple


# -------------------- 유틸 --------------------
def inflate(rect: fitz.Rect, dx: float, dy: float) -> fitz.Rect:
    """사각형을 사방으로 살짝 키움(표 라인/테두리 침범 방지용 아주 소폭만)."""
    return fitz.Rect(rect.x0 - dx, rect.y0 - dy, rect.x1 + dx, rect.y1 + dy)


def redact_rects(page: fitz.Page, rects: List[fitz.Rect], fill=(1, 1, 1)):
    """여러 사각형을 리댁션 주석으로 추가."""
    for r in rects:
        page.add_redact_annot(r, fill=fill)


def search_single_bbox(page: fitz.Page, text: str) -> fitz.Rect | None:
    """문자열을 찾아 가장 왼쪽 위 인스턴스의 bbox 반환(없으면 None)."""
    hits = page.search_for(text, hit_max=16)
    if not hits:
        return None
    hits = sorted(hits, key=lambda r: (r.y0, r.x0))
    return hits[0]


def words_in_range(page: fitz.Page, y0: float, y1: float, x_min: float = None, x_max: float = None) -> List[Tuple[float,float,float,float,str]]:
    """
    단어 리스트 중 주어진 y구간(필수), x구간(옵션)에 들어오는 것만 반환.
    반환: (x0, y0, x1, y1, text)
    """
    words = page.get_text("words")  # (x0,y0,x1,y1,word, block_no, line_no, word_no)
    results = []
    for w in words:
        wx0, wy0, wx1, wy1, wtxt = w[0], w[1], w[2], w[3], w[4]
        # y대역 교집합(라인 두께 고려해 살짝 여유)
        if (wy1 >= y0) and (wy0 <= y1):
            if (x_min is None or wx1 >= x_min) and (x_max is None or wx0 <= x_max):
                if str(wtxt).strip():
                    results.append((wx0, wy0, wx1, wy1, wtxt))
    return results


def union_rect_of_words(words: List[Tuple[float,float,float,float,str]], x_min=None, x_max=None) -> List[fitz.Rect]:
    """
    단어들을 같은 줄 기준으로 묶어 최소 bbox 리스트로 반환.
    (x_min/x_max 제한을 주면 열 경계 밖은 자동 배제)
    """
    if not words:
        return []
    # 라인 그룹핑: y0를 기준으로 근접한 것끼리 묶기
    words = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    lines: List[List[Tuple[float,float,float,float,str]]] = []
    for w in words:
        placed = False
        for line in lines:
            # 같은 라인 판단: y가 매우 가까우면 같은 줄
            if abs(line[0][1] - w[1]) < 2.5:  # 2.5pt 이내면 같은 줄로 가정
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    rects: List[fitz.Rect] = []
    for line in lines:
        xs0 = [w[0] for w in line]
        ys0 = [w[1] for w in line]
        xs1 = [w[2] for w in line]
        ys1 = [w[3] for w in line]
        r = fitz.Rect(min(xs0), min(ys0), max(xs1), max(ys1))
        # 열 경계 x_min/x_max가 있으면 교차부분만 남김
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
    요구사항:
    1) 1페이지 첫 번째 표의 '반/번호/담임성명' 칸 내용만 삭제 (테두리 유지)
    2) 두 번째 표(1. 인적·학적사항)의 학생정보 칸 중 '성명/성별/주민등록번호/주소' 내용만 삭제
    3) 같은 표의 '학적사항' 내용 삭제 (특기사항 이전까지)
    + "(고등학교)" 검색 마스킹, 모든 페이지 하단 공통 마스킹 유지
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            pw, ph = page.rect.width, page.rect.height
            dx_small, dy_small = pw * 0.002, ph * 0.002

            # ---------------- A. 1페이지 전용: 표 기반 마스킹 ----------------
            if page_num == 0:
                # --- A1) 첫 번째 표: 헤더 단어 위치로 열 경계 추정 ---
                # 기준 헤더 탐지
                hdr_hakgwa = search_single_bbox(page, "학과")
                hdr_ban = search_single_bbox(page, "반")
                hdr_beonho = search_single_bbox(page, "번호")
                hdr_damim = search_single_bbox(page, "담임성명")

                # 표의 수직 대역(상/하) 추정: '학년' 라벨과 표 하단 실선 근처 텍스트로 보수적으로 지정
                top_anchor = search_single_bbox(page, "학년")
                # '담임성명'이 있으면 그 y를 표 상단 대략으로 사용
                table_y_top = (top_anchor.y0 if top_anchor else ph * 0.17) if top_anchor else ph * 0.17
                # 표 하단은 '1.'(인적·학적사항 제목) y 상단까지
                sec1 = search_single_bbox(page, "1.")
                table_y_bottom = (sec1.y0 - ph * 0.01) if sec1 else ph * 0.35

                # 열 x 경계
                x_hakgwa = hdr_hakgwa.x0 if hdr_hakgwa else pw * 0.32
                x_ban = hdr_ban.x0 if hdr_ban else pw * 0.52
                x_beonho = hdr_beonho.x0 if hdr_beonho else pw * 0.63
                x_damim = hdr_damim.x0 if hdr_damim else pw * 0.75
                x_table_right = pw * 0.985  # 우측 여백 부근(테두리선 살리기 위해 실제 마스킹은 inset)

                # 각 열에 포함된 "내용 텍스트"만 단어 위치로 수집 → 라인별 bbox로 합치기
                words = words_in_range(page, table_y_top, table_y_bottom)

                # 반 열
                ban_words = [w for w in words if w[0] >= x_ban - pw*0.005 and w[2] <= x_beonho - pw*0.005]
                ban_rects = union_rect_of_words(ban_words, x_min=x_ban + pw*0.004, x_max=x_beonho - pw*0.006)

                # 번호 열
                beonho_words = [w for w in words if w[0] >= x_beonho - pw*0.005 and w[2] <= x_damim - pw*0.005]
                beonho_rects = union_rect_of_words(beonho_words, x_min=x_beonho + pw*0.004, x_max=x_damim - pw*0.006)

                # 담임성명 열
                damim_words = [w for w in words if w[0] >= x_damim - pw*0.005]
                damim_rects = union_rect_of_words(damim_words, x_min=x_damim + pw*0.004, x_max=x_table_right - pw*0.006)

                redact_rects(page, [inflate(r, dx_small, dy_small) for r in (ban_rects + beonho_rects + damim_rects)])

                # --- A2) 첫 표의 사진 칸 (있다면) 이미지 블록만 삭제 ---
                raw = page.get_text("rawdict")
                img_rects = []
                for blk in raw.get("blocks", []):
                    if blk.get("type") == 1 or "image" in blk:
                        x0, y0, x1, y1 = blk["bbox"]
                        r = fitz.Rect(x0, y0, x1, y1)
                        # 상단 표 대역 안쪽만 사진으로 간주
                        if r.y0 >= table_y_top - ph*0.05 and r.y1 <= table_y_bottom + ph*0.05:
                            img_rects.append(r)
                if img_rects:
                    # 오른쪽에 위치한 것이 사진일 확률이 큼
                    img_rects.sort(key=lambda r: (r.x0, (r.width * r.height)), reverse=True)
                    page.add_redact_annot(inflate(img_rects[0], dx_small*2, dy_small*2), fill=(1,1,1))

                # --- A3) 두 번째 표(인적·학적사항) 처리 ---
                # 제목들 위치로 y대역 자동 산출
                title_1 = search_single_bbox(page, "1.")
                title_2 = search_single_bbox(page, "2.")
                y1_top = title_1.y0 if title_1 else ph * 0.42
                y1_bot = (title_2.y0 - ph * 0.01) if title_2 else ph * 0.74

                # 라벨 기준 bbox
                lab_name = search_single_bbox(page, "성명")
                lab_gender = search_single_bbox(page, "성별")
                lab_rrn = search_single_bbox(page, "주민등록번호")
                lab_addr = search_single_bbox(page, "주소")

                # 2-1) '학생정보' 라인의 성명/성별/주민등록번호 오른쪽 내용만 삭제
                # 학생정보 줄 y대역을 '성명' 라벨 y로 추정
                if lab_name:
                    line_y0, line_y1 = lab_name.y0 - ph*0.006, lab_name.y1 + ph*0.006
                    all_words = words_in_range(page, line_y0, line_y1)
                    rects = []
                    # 성명 오른쪽
                    if lab_name:
                        rects += union_rect_of_words([w for w in all_words if w[0] > lab_name.x1 + pw*0.005],
                                                     x_min=lab_name.x1 + pw*0.006)
                    # 성별 오른쪽
                    if lab_gender:
                        rects += union_rect_of_words([w for w in all_words if w[0] > lab_gender.x1 + pw*0.005],
                                                     x_min=lab_gender.x1 + pw*0.006)
                    # 주민등록번호 오른쪽
                    if lab_rrn:
                        rects += union_rect_of_words([w for w in all_words if w[0] > lab_rrn.x1 + pw*0.005],
                                                     x_min=lab_rrn.x1 + pw*0.006)
                    redact_rects(page, [inflate(r, dx_small, dy_small) for r in rects])

                # 2-2) '주소' 줄: '주소' 라벨 오른쪽 내용만 삭제
                if lab_addr:
                    addr_y0, addr_y1 = lab_addr.y0 - ph*0.006, lab_addr.y1 + ph*0.006
                    addr_words = words_in_range(page, addr_y0, addr_y1)
                    addr_rects = union_rect_of_words([w for w in addr_words if w[0] > lab_addr.x1 + pw*0.005],
                                                     x_min=lab_addr.x1 + pw*0.006)
                    redact_rects(page, [inflate(r, dx_small, dy_small) for r in addr_rects])

                # 2-3) '학적사항' 내용: '학적사항' 라벨 오른쪽 영역을 '특기사항' 라벨 전까지 삭제
                lab_acad = search_single_bbox(page, "학적사항")
                lab_extra = search_single_bbox(page, "특기사항")
                if lab_acad:
                    y_acad_top = lab_acad.y0 - ph*0.004
                    y_acad_bot = (lab_extra.y0 - ph*0.004) if lab_extra else y1_bot
                    acad_words = words_in_range(page, y_acad_top, y_acad_bot, x_min=lab_acad.x1 + pw*0.005)
                    acad_rects = union_rect_of_words(acad_words, x_min=lab_acad.x1 + pw*0.006)
                    redact_rects(page, [inflate(r, dx_small, dy_small) for r in acad_rects])

            # ---------------- B. "(고등학교)" 등 검색 마스킹(기존 유지) ----------------
            for t in ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"]:
                try:
                    for inst in page.search_for(t):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    pass

            # ---------------- C. 모든 페이지 하단 공통 마스킹 ----------------
            # 상단 얇은 머리글
            page.add_redact_annot(fitz.Rect(0, 0, pw, ph * 0.015), fill=(1, 1, 1))
            # 하단 "/" 부근
            page.add_redact_annot(fitz.Rect(pw * 0.010, ph * 0.978, pw * 0.055, ph * 0.994), fill=(1, 1, 1))
            # 하단 반/번호/성명 줄
            rb = fitz.Rect(pw * 0.60, ph * 0.977, pw * 0.995, ph * 0.996)
            page.add_redact_annot(inflate(rb, pw * 0.002, ph * 0.001), fill=(1, 1, 1))
            # 맨 아래 작은 글씨
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


# -------------------- Streamlit UI --------------------
st.set_page_config(page_title="PDF 개인정보 보호 앱", page_icon="🔒")
st.title("🔒 PDF 민감정보 마스킹 앱")
st.write("첫 표의 '반·번호·담임성명'과, 인적·학적사항의 개인정보(성명·성별·주민등록번호·주소·학적사항 내용)만 정확히 가립니다.")
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
