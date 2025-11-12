import streamlit as st
import fitz  # PyMuPDF
import io

def redact_sensitive_info(input_pdf_bytes):
    """
    원본 '(    )고등학교' 텍스트 마스킹 로직은 변경하지 않고,
    좌표 기반 마스킹 영역만 재조정한 함수입니다.
    최대 23페이지 처리, 각 페이지에 좌표 비율로 마스킹 적용 후 redaction 수행.
    """
    try:
        doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        
        # 처리할 페이지 수 제한 (최대 23페이지)
        page_count = min(doc.page_count, 23)

        for page_num in range(page_count):
            page = doc[page_num]
            page_height = page.rect.height
            page_width = page.rect.width

            # --- 1페이지 특정 영역 마스킹 (표 내용은 삭제, 표 구조는 유지) ---
            if page_num == 0:
                # 1) 상단 첫번째 표: 사진 영역 (조금 더 넓게 / 세로 위치 보정)
                photo_rect = fitz.Rect(
                    page_width * 0.020,  # x0 (왼쪽 여백)
                    page_height * 0.045, # y0 (상단 약간 아래)
                    page_width * 0.195,  # x1 (사진 오른쪽)
                    page_height * 0.165  # y1 (사진 아랫부분)
                )
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 1) 상단 첫번째 표: 반, 번호, 담임성명(표 오른쪽 부분) — 더 좁고 정확히
                table_content_rect = fitz.Rect(
                    page_width * 0.28,   # x0 - 표의 정보 시작 지점(왼쪽보다 조금 더 앞으로)
                    page_height * 0.050, # y0 - 표 상단
                    page_width * 0.98,   # x1 - 우측 끝(안전여유 둠)
                    page_height * 0.150   # y1 - 표 하단(약간 위로 당김)
                )
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))
                
                # 2) 1. 인적·학적사항 표: 성명/성별/주민등록번호 한 줄 영역
                student_info_rect = fitz.Rect(
                    page_width * 0.12,   # x0 - 성명 이후 영역 포함
                    page_height * 0.155, # y0 - 약간 위로 당김
                    page_width * 0.98,   # x1 - 우측 끝
                    page_height * 0.184  # y1 - 한 줄 높이
                )
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))
                
                # 주소 영역 (줄 바꿈 고려, 충분히 넓게 커버)
                address_rect = fitz.Rect(
                    page_width * 0.08,   # x0
                    page_height * 0.182, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.206  # y1
                )
                page.add_redact_annot(address_rect, fill=(1, 1, 1))
                
                # 학적사항 내용 영역 (여러 줄 커버)
                academic_rect = fitz.Rect(
                    page_width * 0.10,   # x0
                    page_height * 0.215, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.260  # y1 (여유 있게)
                )
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                # 특기사항 내용 영역 (아랫부분 포함)
                notes_rect = fitz.Rect(
                    page_width * 0.10,   # x0
                    page_height * 0.265, # y0
                    page_width * 0.98,   # x1
                    page_height * 0.330  # y1
                )
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))
                
            # --- "(고등학교)" 키워드 검색 및 마스킹 (원본 로직 **절대 수정하지 않음**) ---
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"] 
            
            for text in search_texts:
                text_instances = page.search_for(text)
                for inst in text_instances:
                    page.add_redact_annot(inst, fill=(1, 1, 1))

            # --- 모든 페이지 맨 하단의 개인정보 마스킹 ---
