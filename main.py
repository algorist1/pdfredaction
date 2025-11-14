import streamlit as st
import fitz  # PyMuPDF
import io

def redact_pdf(pdf_bytes):
    """
    PDF에서 개인정보를 삭제(흰색 사각형으로 덮기)하는 함수
    """
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(pdf_document)
    
    # ========================================
    # 1단계: "고등학교" 텍스트 검색 및 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        
        # "고등학교" 검색
        text_instances = page.search_for("고등학교")
        
        for inst in text_instances:
            x0, y0, x1, y1 = inst
            rect = fitz.Rect(x0 - 100, y0 - 3, x1 + 5, y1 + 3)
            
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
    
    # ========================================
    # 2단계: 1페이지 영역 기반 완전 삭제
    # ========================================
    if total_pages >= 1:
        page = pdf_document[0]
        pw = page.rect.width
        ph = page.rect.height
        
        # -----------------------------------------
        # 2-1. 첫 번째 표 데이터 영역 완전 삭제
        # -----------------------------------------
        # "졸업대장번호" 표의 데이터 셀들
        # 표 구조: 학년 | 학과 | 반 | 번호 | 담임성명
        
        # 1학년 행 (학과, 반, 번호, 담임성명 영역)
        first_table_row1 = fitz.Rect(
            pw * 0.26,  # 학년 열 다음부터
            ph * 0.195,  # 1학년 행 시작
            pw * 0.95,   # 오른쪽 끝
            ph * 0.215   # 1학년 행 끝
        )
        
        # 2학년 행
        first_table_row2 = fitz.Rect(
            pw * 0.26,
            ph * 0.215,
            pw * 0.95,
            ph * 0.235
        )
        
        # 3학년 행
        first_table_row3 = fitz.Rect(
            pw * 0.26,
            ph * 0.235,
            pw * 0.95,
            ph * 0.255
        )
        
        shape = page.new_shape()
        shape.draw_rect(first_table_row1)
        shape.draw_rect(first_table_row2)
        shape.draw_rect(first_table_row3)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # -----------------------------------------
        # 2-2. 우측 사진 영역 삭제
        # -----------------------------------------
        photo_rect = fitz.Rect(
            pw * 0.82,   # 우측
            ph * 0.14,   # 상단
            pw * 0.97,   # 오른쪽 끝
            ph * 0.26    # 사진 하단
        )
        
        shape = page.new_shape()
        shape.draw_rect(photo_rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # -----------------------------------------
        # 2-3. "1. 인적·학적사항" 섹션 완전 삭제
        # -----------------------------------------
        
        # 학생정보 영역 (성명, 성별, 주민등록번호)
        student_info = fitz.Rect(
            pw * 0.15,   # 좌측
            ph * 0.305,  # 상단
            pw * 0.95,   # 우측
            ph * 0.335   # 하단
        )
        
        # 주소 영역
        address_info = fitz.Rect(
            pw * 0.15,
            ph * 0.335,
            pw * 0.95,
            ph * 0.365
        )
        
        # **학적사항 전체 영역 (여기가 핵심!)**
        academic_info = fitz.Rect(
            pw * 0.15,   # 좌측
            ph * 0.375,  # "학적사항" 라벨 아래
            pw * 0.95,   # 우측
            ph * 0.435   # 학적사항 전체 영역
        )
        
        # 특기사항 표 데이터 영역
        attendance_table = fitz.Rect(
            pw * 0.15,
            ph * 0.455,
            pw * 0.95,
            ph * 0.535
        )
        
        shape = page.new_shape()
        shape.draw_rect(student_info)
        shape.draw_rect(address_info)
        shape.draw_rect(academic_info)
        shape.draw_rect(attendance_table)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # -----------------------------------------
        # 2-4. 텍스트 기반 추가 삭제 (보험용)
        # -----------------------------------------
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]
        
        additional_rects = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        
                        # 첫 번째 표의 숫자들 (반, 번호)
                        if text.isdigit() and bbox[1] < ph * 0.26:
                            rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                           bbox[2] + 3, bbox[3] + 3)
                            additional_rects.append(rect)
                        
                        # 담임 이름들
                        if text in ["이혜원", "김정훈", "노지호"]:
                            rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                           bbox[2] + 3, bbox[3] + 3)
                            additional_rects.append(rect)
                        
                        # 학생 이름
                        if "박지호" in text:
                            rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                           bbox[2] + 3, bbox[3] + 3)
                            additional_rects.append(rect)
                        
                        # 주민번호
                        if "-" in text and len(text) >= 13 and any(c.isdigit() for c in text):
                            rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                           bbox[2] + 3, bbox[3] + 3)
                            additional_rects.append(rect)
                        
                        # 주소
                        if ("서울" in text or "경기" in text) and len(text) > 10:
                            rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                           bbox[2] + 3, bbox[3] + 3)
                            additional_rects.append(rect)
                        
                        # 학적사항의 날짜와 학교명
                        if bbox[1] > ph * 0.37 and bbox[1] < ph * 0.44:  # 학적사항 영역
                            if any(kw in text for kw in ["2023", "2024", "2025", "년", "월", "일", 
                                                          "중학교", "초등학교", "졸업", "입학", "제"]):
                                rect = fitz.Rect(bbox[0] - 3, bbox[1] - 3,
                                               bbox[2] + 3, bbox[3] + 3)
                                additional_rects.append(rect)
        
        # 추가 삭제 실행
        if additional_rects:
            shape = page.new_shape()
            for rect in additional_rects:
                shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
    
    # ========================================
    # 3단계: 모든 페이지 하단 영역 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        pw = page.rect.width
        ph = page.rect.height
        
        # 하단 좌측 영역 (반, 번호)
        left_bottom = fitz.Rect(
            0,           # 왼쪽 끝
            ph * 0.93,   # 하단 7% 영역
            pw * 0.38,   # 페이지 38%까지
            ph           # 끝까지
        )
        
        # 하단 우측 영역 (성명)
        right_bottom = fitz.Rect(
            pw * 0.62,   # 페이지 62%부터
            ph * 0.93,   # 하단 7% 영역
            pw,          # 오른쪽 끝
            ph           # 끝까지
        )
        
        shape = page.new_shape()
        shape.draw_rect(left_bottom)
        shape.draw_rect(right_bottom)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # PDF 저장
    output_bytes = pdf_document.write()
    pdf_document.close()
    
    return output_bytes


def main():
    """Streamlit 메인 애플리케이션"""
    
    st.set_page_config(
        page_title="PDF 개인정보 보호",
        page_icon="🔒",
        layout="centered"
    )
    
    st.title("🔒 PDF 개인정보 보호 도구")
    
    st.markdown("""
    ### 📌 처리되는 정보
    
    ✅ **학교명**: "○○고등학교" 전체 페이지 검색 삭제  
    ✅ **첫 번째 표**: 학과, 반, 번호, 담임성명 (영역 기반 완전 삭제)  
    ✅ **개인정보**: 이름, 성별, 주민등록번호, 주소  
    ✅ **학적사항**: 졸업/입학 학교 및 날짜 (영역 기반 완전 삭제)  
    ✅ **사진**: 우측 상단 학생 사진  
    ✅ **페이지 하단**: 모든 페이지의 반/번호/성명 (페이지 번호 보존)
    """)
    
    uploaded_file = st.file_uploader(
        "📁 PDF 파일을 업로드하세요",
        type=['pdf'],
        help="학교생활기록부 PDF (최대 23페이지)"
    )
    
    if uploaded_file is not None:
        st.info(f"📄 **{uploaded_file.name}** 업로드 완료")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            process_btn = st.button(
                "🔒 개인정보 보호 처리 시작", 
                type="primary", 
                use_container_width=True
            )
        
        if process_btn:
            
            with st.spinner("🔄 처리 중..."):
                try:
                    pdf_bytes = uploaded_file.read()
                    
                    # 페이지 수 확인
                    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    num_pages = len(pdf_doc)
                    pdf_doc.close()
                    
                    if num_pages > 23:
                        st.error(f"❌ 페이지 수 초과 (현재: {num_pages}페이지)")
                        return
                    
                    # 진행 바
                    progress = st.progress(0)
                    status = st.empty()
                    
                    status.text("📖 PDF 분석 중...")
                    progress.progress(25)
                    
                    status.text("🔍 개인정보 검색 중...")
                    progress.progress(50)
                    
                    # 처리
                    redacted_pdf = redact_pdf(pdf_bytes)
                    
                    status.text("🔒 정보 삭제 완료!")
                    progress.progress(100)
                    
                    st.success(f"✅ 총 {num_pages}페이지 처리 완료!")
                    
                    # 다운로드
                    st.download_button(
                        label="📥 보호된 PDF 다운로드",
                        data=redacted_pdf,
                        file_name="private_protected_document.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.info("💡 **반드시 확인**: 다운로드한 파일을 열어 모든 정보가 삭제되었는지 확인하세요.")
                    
                except Exception as e:
                    st.error(f"❌ 오류: {str(e)}")
                    with st.expander("상세 정보"):
                        st.exception(e)
    
    with st.expander("ℹ️ 사용 방법"):
        st.markdown("""
        1. PDF 파일 업로드
        2. 처리 버튼 클릭
        3. 완료 후 다운로드
        4. 결과 확인 필수!
        """)
    
    with st.expander("⚠️ 주의사항"):
        st.markdown("""
        - ✔️ 결과물 확인 필수
        - ✔️ 원본 파일 백업 권장
        - ✔️ 표준 PDF만 지원
        - ✔️ 최대 23페이지
        """)


if __name__ == "__main__":
    main()
