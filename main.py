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
    #   (학년/학과 열은 남기고, 반/번호/담임성명만 포함되는 우측 영역을 강조)
    table_content_rect = fitz.Rect(
        page_width * 0.52,    # x0  <- 우측 절반부터
        page_height * 0.052,  # y0  <- 1학년 행 시작 위 살짝
        page_width * 0.985,   # x1
        page_height * 0.150   # y1  <- 3학년 행 하단까지
    )
    page.add_redact_annot(table_content_rect, fill=(1, 1, 1))

    # 2) "1. 인적·학적사항" 표: 성명/성별/주민등록번호/주소/학적사항/특기사항 내용 제거

    # (C) 학생정보(성명·성별·주민등록번호) 라인 전체
    student_info_rect = fitz.Rect(
        page_width * 0.125,   # x0  <- '성명:' 라벨 오른쪽부터
        page_height * 0.162,  # y0
        page_width * 0.985,   # x1
        page_height * 0.193   # y1  <- 라인 높이 여유있게
    )
    page.add_redact_annot(student_info_rect, fill=(1, 1, 1))

    # (D) 주소 라인 전체
    address_rect = fitz.Rect(
        page_width * 0.090,   # x0  <- '주소:' 라벨 오른쪽부터
        page_height * 0.198,  # y0
        page_width * 0.985,   # x1
        page_height * 0.228   # y1
    )
    page.add_redact_annot(address_rect, fill=(1, 1, 1))

    # (E) 학적사항 내용(여러 줄) — 박스 전체를 충분히 포괄
    academic_rect = fitz.Rect(
        page_width * 0.125,   # x0
        page_height * 0.232,  # y0
        page_width * 0.985,   # x1
        page_height * 0.268   # y1
    )
    page.add_redact_annot(academic_rect, fill=(1, 1, 1))

    # (F) 특기사항 내용(여러 줄) — 박스 전체를 충분히 포괄
    notes_rect = fitz.Rect(
        page_width * 0.125,   # x0
        page_height * 0.274,  # y0
        page_width * 0.985,   # x1
        page_height * 0.335   # y1
    )
    page.add_redact_annot(notes_rect, fill=(1, 1, 1))

# --- "(고등학교)" 키워드 검색/마스킹은 기존 코드 유지 ---

# --- 모든 페이지 맨 하단 개인정보 마스킹(강화) ---

# (1) 페이지 최상단 얇은 머리글(학교/날짜/IP/이름) — 기존 유지
footer_top_rect = fitz.Rect(
    0,
    0,
    page_width,
    page_height * 0.015
)
page.add_redact_annot(footer_top_rect, fill=(1, 1, 1))

# (2) 하단 좌측의 "/" 표기 근방 — 약간 확장
footer_slash_rect = fitz.Rect(
    page_width * 0.010,      # x0
    page_height * 0.978,     # y0
    page_width * 0.055,      # x1
    page_height * 0.994      # y1
)
page.add_redact_annot(footer_slash_rect, fill=(1, 1, 1))

# (3) 하단 우측의 "반/번호/성명" 영역 — 더 넓고 두껍게
footer_bottom_rect = fitz.Rect(
    page_width * 0.60,       # x0  <- 0.72 → 0.60으로 넓혀, '반' 앞의 숫자 변동 대응
    page_height * 0.977,     # y0  <- 0.982 → 0.977로 위로 조금 올림
    page_width * 0.995,      # x1
    page_height * 0.996      # y1  <- 높이 여유 확보
)
page.add_redact_annot(footer_bottom_rect, fill=(1, 1, 1))

# (4) 하단 아주 아래 줄(작은 글씨 이름 등) — 얇은 추가 라인
footer_bottom_hairline_rect = fitz.Rect(
    page_width * 0.58,       # x0
    page_height * 0.996,     # y0
    page_width * 0.995,      # x1
    page_height * 1.000      # y1
)
page.add_redact_annot(footer_bottom_hairline_rect, fill=(1, 1, 1))
