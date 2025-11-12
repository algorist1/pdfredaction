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
            
            # 페이지 크기 (비율 계산을 위해 사용)
            pw = page.rect.width
            ph = page.rect.height

            # --- 테두리 보존을 위한 inset(여백) 도우미 ---
            # 테두리를 덮지 않도록, 셀 내부만 가리게 약간 안쪽으로 줄인 사각형을 만들어줍니다.
            def inset_rect(x0, y0, x1, y1, dx_ratio=0.004, dy_ratio=0.004):
                dx = pw * dx_ratio
                dy = ph * dy_ratio
                return fitz.Rect(x0 + dx, y0 + dy, x1 - dx, y1 - dy)

            # --- 1페이지 특정 영역 마스킹 (표 내용은 삭제, 표 테두리는 유지) ---
            if page_num == 0:
                # 1) 상단 첫 번째 표: 좌측 "사진" 칸의 사진만 마스킹 (테두리/라벨은 살림)
                #    사진 칸 전체 좌표를 대략적으로 잡은 뒤 안쪽으로 inset
                photo_cell = fitz.Rect(
                    pw * 0.028,  # x0 (셀 바깥)
                    ph * 0.038,  # y0
                    pw * 0.208,  # x1
                    ph * 0.162   # y1
                )
                photo_rect = inset_rect(photo_cell.x0, photo_cell.y0, photo_cell.x1, photo_cell.y1,
                                        dx_ratio=0.010, dy_ratio=0.010)  # 사진 영역은 더 깊게 inset
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 1-2) 같은 표의 우측 영역(학년/학과 열 제외, "반/번호/담임성명" 내용만)
                #      표 테두리/선은 남기고 셀 내부 텍스트만 가리도록 inset 적용
                #      (행 3줄 높이를 한 번에 커버하되, 선/테두리를 피하도록 상하좌우 여유)
                table_right_block = fitz.Rect(
                    pw * 0.52,   # x0: 우측 절반부터
                    ph * 0.052,  # y0: 1학년 행 시작 위로 약간
                    pw * 0.985,  # x1
                    ph * 0.150   # y1: 3학년 행 하단까지
                )
                table_content_rect = inset_rect(table_right_block.x0, table_right_block.y0,
                                                table_right_block.x1, table_right_block.y1,
                                                dx_ratio=0.010, dy_ratio=0.012)
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))

                # 2) "1. 인적·학적사항" 표: 성명/성별/주민등록번호/주소/학적사항/특기사항 **내용만** 마스킹
                #    각 라인/블록을 표 내부 여백으로만 가리도록 좌표를 세밀히 조정

                # (C) 학생정보(성명·성별·주민등록번호) 라인 전체(내용만)
                student_info_line = fitz.Rect(
                    pw * 0.125,  # '성명:' 라벨 오른쪽부터
                    ph * 0.162,
                    pw * 0.985,
                    ph * 0.193
                )
                student_info_rect = inset_rect(student_info_line.x0, student_info_line.y0,
                                               student_info_line.x1, student_info_line.y1,
                                               dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))

                # (D) 주소 라인 전체(내용만)
                address_line = fitz.Rect(
                    pw * 0.090,  # '주소:' 라벨 오른쪽부터
                    ph * 0.198,
                    pw * 0.985,
                    ph * 0.228
                )
                address_rect = inset_rect(address_line.x0, address_line.y0,
                                          address_line.x1, address_line.y1,
                                          dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(address_rect, fill=(1, 1, 1))

                # (E) 학적사항 내용(여러 줄) — 내부 텍스트만 가리도록 블록 inset
                academic_block = fitz.Rect(
                    pw * 0.125,
                    ph * 0.232,
                    pw * 0.985,
                    ph * 0.268
                )
                academic_rect = inset_rect(academic_block.x0, academic_block.y0,
                                           academic_block.x1, academic_block.y1,
                                           dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # (F) 특기사항 내용(여러 줄) — 내부 텍스트만
                notes_block = fitz.Rect(
                    pw * 0.125,
                    ph * 0.274,
                    pw * 0.985,
                    ph * 0.335
                )
                notes_rect = inset_rect(notes_block.x0, notes_block.y0,
                                        notes_block.x1, notes_block.y1,
                                        dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))

            # --- "(고등학교)" 키워드 검색 및 마스킹 (기존 로직 유지: 수정하지 않음) ---
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"] 
            for text in search_texts:
                try:
                    for inst in page.search_for(text):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    # 검색 실패 시에도 앱이 멈추지 않도록
