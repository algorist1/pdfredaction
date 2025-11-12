import streamlit as st 
import fitz  # PyMuPDF
import io

def redact_sensitive_info(input_pdf_bytes):
    """PDF에서 민감정보(사진, 성명, 주소 등)만 흰색으로 덮어씌움"""
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            pw, ph = page.rect.width, page.rect.height

            def inset_rect(x0, y0, x1, y1, dx_ratio=0.004, dy_ratio=0.004):
                dx, dy = pw * dx_ratio, ph * dy_ratio
                return fitz.Rect(x0 + dx, y0 + dy, x1 - dx, y1 - dy)

            # ----------------------- 1페이지 상단 표 -----------------------
            if page_num == 0:
                # (1) 사진 영역 - 사진 부분만 덮음 (세로 살짝 더 넓힘)
                photo_cell = fitz.Rect(
                    pw * 0.027, ph * 0.032,  # 살짝 위쪽부터 시작
                    pw * 0.205, ph * 0.170   # 살짝 더 아래까지
                )
                photo_rect = inset_rect(photo_cell.x0, photo_cell.y0, photo_cell.x1, photo_cell.y1,
                                        dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # (2) 반/번호/담임성명 칸 - 표 내부 텍스트만 덮기
                table_right_block = fitz.Rect(
                    pw * 0.51, ph * 0.046,   # 약간 위로 확장
                    pw * 0.985, ph * 0.155   # 아래도 약간 더
                )
                table_content_rect = inset_rect(table_right_block.x0, table_right_block.y0,
                                                table_right_block.x1, table_right_block.y1,
                                                dx_ratio=0.004, dy_ratio=0.006)
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))

                # ----------------------- 인적·학적사항 표 -----------------------
                # (3) 학생정보 (성명·성별·주민번호)
                student_info_rect = inset_rect(
                    pw * 0.125, ph * 0.158, pw * 0.985, ph * 0.190,
                    dx_ratio=0.004, dy_ratio=0.004
                )
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))

                # (4) 주소
                address_rect = inset_rect(
                    pw * 0.090, ph * 0.195, pw * 0.985, ph * 0.226,
                    dx_ratio=0.004, dy_ratio=0.004
                )
                page.add_redact_annot(address_rect, fill=(1, 1, 1))

                # (5) 학적사항
                academic_rect = inset_rect(
                    pw * 0.125, ph * 0.230, pw * 0.985, ph * 0.268,
                    dx_ratio=0.004, dy_ratio=0.004
                )
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # (6) 특기사항
                notes_rect = inset_rect(
                    pw * 0.125, ph * 0.273, pw * 0.985, ph * 0.335,
                    dx_ratio=0.004, dy_ratio=0.004
                )
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))

            # ---------------------- "(고등학교)" 마스킹 유지 ----------------------
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"]
            for text in search_texts:
                try:
                    for inst in page.search_for(text):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    pass

            # ----------------------- 페이지 하단 공통 영역 -----------------------
            header_rect = fitz.Rect(0, 0, pw, ph * 0.015)
            page.add_redact_annot(header_rect, fill=(1, 1, 1))

            footer_slash = fitz.Rect(pw * 0.010, ph * 0.978, pw * 0.055, ph * 0.994)
            page.add_redact_annot(foot
