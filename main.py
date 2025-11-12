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
    hits = page.search_for(text, hit_max=32)
    if not hits:
        return None
    hits = sorted(hits, key=lambda r: (r.y0, r.x0))
    return hits[0]


def words_in_range(
    page: fitz.Page, y0: float, y1: float, x_min: float | None = None, x_max: float | None = None
) -> List[Tuple[float, float, float, float, str]]:
    """
    단어 리스트 중 주어진 y구간(필수), x구간(옵션)에 들어오는 것만 반환.
    반환: (x0, y0, x1, y1, text)
    """
    words = page.get_text("words")  # (x0,y0,x1,y1,word, block_no, line_no, word_no)
    results: List[Tuple[float, float, float, float, str]] = []
    for w in words:
        wx0, wy0, wx1, wy1, wtxt = w[0], w[1], w[2], w[3], w[4]
        if (wy1 >= y0) and (wy0 <= y1):
            if (x_min is None or wx1 >= x_min) and (x_max is None or wx0 <= x_max):
                if str(wtxt).strip():
                    results.append((wx0, wy0, wx1, wy1, wtxt))
    return results


def union_rect_of_words(
    words: List[Tuple[float, float, float, float, str]], x_min: float | None = None, x_max: float | None = None
) -> List[fitz.Rect]:
    """
    단어들을 같은 줄 기준으로 묶어 최소 bbox 리스트로 반환.
    (x_min/x_max 제한을 주면 열 경계 밖은 자동 배제)
    """
    if not words:
        return []
    # 라인 그룹핑: y0가 가까운 것끼리 묶기
    words = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    lines: List[List[Tuple[float, float, float, float, str]]] = []
    for w in words:
        placed = False
        for line in lines:
            if abs(line[0][1] - w[1]) < 2.5:  # 2.5pt 이내면 같은 줄로 처리
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])

    rects: List[fitz.Rect] = []
    for line in lines:
        xs0 = [w[0] for w in line]
        ys0 = [w[1] for w in line]
        xs1
