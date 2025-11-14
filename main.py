import streamlit as st
import fitz  # PyMuPDF
import io

def redact_pdf(pdf_bytes):
    """
    PDF에서 개인정보를 삭제(흰색 사각형으로 덮기)하는 함수
    
    Args:
        pdf_bytes: 업로드된 PDF 파일의 바이트 데이터
    
    Returns:
        처리된 PDF 파일의 바이트 데이터
    """
    # PDF 문서 열기
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(pdf_document)
    
    # ========================================
    # 1단계: 텍스트 검색 기반 삭제 - "( )고등학교" 문구만 정확히 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        
        # "고등학교" 텍스트 검색
        text_instances = page.search_for("고등학교")
        
        for inst in text_instances:
            x0, y0, x1, y1 = inst
            
            # 앞쪽 괄호와 학교명을 포함한 영역 확장
            # 예: "대성고등학교", "(   )고등학교" 등
            padding_left = 80   # 왼쪽으로 확장 (학교명 포함)
            padding_right = 5   # 오른쪽으로 약간 확장
            padding_top = 2     # 위아래 여백
            padding_bottom = 2
            
            rect = fitz.Rect(
                x0 - padding_left, 
                y0 - padding_top, 
                x1 + padding_right, 
                y1 + padding_bottom
            )
            
            # 흰색 사각형으로 덮기
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
    
    # ========================================
    # 2단계: 좌표 기반 영역 삭제
    # ========================================
    
    # 첫 페이지 처리
    if total_pages >= 1:
        page = pdf_document[0]
        page_rect = page.rect
        pw = page_rect.width   # 페이지 너비
        ph = page_rect.height  # 페이지 높이
        
        # -----------------------------------------
        # 2-1. 첫 번째 표: 상단 우측의 졸업대장번호 표
        # -----------------------------------------
        # 이 표는 우측 상단에 있으므로 건드리지 않음
        
        # -----------------------------------------
        # 2-2. 두 번째 표: 학년/학과/반/번호/담임성명 표
        # -----------------------------------------
        # 표 구조를 보존하고 내용만 삭제
        # 표 시작: 대략 y = 100~140 영역
        
        # 학년 열은 그대로 두고, 학과/반/번호/담임성명 열의 데이터만 삭제
        table1_areas = [
            # 1학년 행의 데이터 (학과, 반, 번호, 담임)
            fitz.Rect(pw * 0.20, ph * 0.165, pw * 0.95, ph * 0.185),
            # 2학년 행의 데이터
            fitz.Rect(pw * 0.20, ph * 0.185, pw * 0.95, ph * 0.205),
            # 3학년 행의 데이터
            fitz.Rect(pw * 0.20, ph * 0.205, pw * 0.95, ph * 0.225),
        ]
        
        shape = page.new_shape()
        for rect in table1_areas:
            shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # -----------------------------------------
        # 2-3. 우측 사진 영역 삭제
        # -----------------------------------------
        photo_rect = fitz.Rect(pw * 0.83, ph * 0.13, pw * 0.97, ph * 0.24)
        shape = page.new_shape()
        shape.draw_rect(photo_rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # -----------------------------------------
        # 2-4. "1. 인적·학적사항" 표의 내용 삭제
        # -----------------------------------------
        # 표 제목 아래의 학생정보 섹션
        personal_info_areas = [
            # 성명/성별/주민등록번호 행
            fitz.Rect(pw * 0.12, ph * 0.275, pw * 0.97, ph * 0.305),
            # 주소 행
            fitz.Rect(pw * 0.12, ph * 0.305, pw * 0.97, ph * 0.335),
        ]
        
        # 학적사항 섹션 - "2023년 01월 04일..." 부분
        academic_info_areas = [
            # 졸업 정보
            fitz.Rect(pw * 0.12, ph * 0.355, pw * 0.97, ph * 0.375),
            # 입학 정보
            fitz.Rect(pw * 0.12, ph * 0.375, pw * 0.97, ph * 0.395),
        ]
        
        # 특기사항 테이블 내용
        attendance_table = [
            # 1학년 출결 데이터
            fitz.Rect(pw * 0.12, ph * 0.43, pw * 0.97, ph * 0.455),
            # 2학년 출결 데이터
            fitz.Rect(pw * 0.12, ph * 0.455, pw * 0.97, ph * 0.48),
            # 3학년 출결 데이터
            fitz.Rect(pw * 0.12, ph * 0.48, pw * 0.97, ph * 0.505),
        ]
        
        shape = page.new_shape()
        for rect in personal_info_areas + academic_info_areas + attendance_table:
            shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # ========================================
    # 3단계: 모든 페이지 하단 처리
    # ========================================
    # 하단의 "반 7 번호 13 성명 박지호" 부분만 삭제
    # 가운데 페이지 번호는 보존
    
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        page_rect = page.rect
        pw = page_rect.width
        ph = page_rect.height
        
        # 하단 좌측 영역 (반, 번호 부분)
        left_bottom = fitz.Rect(
            0,                    # 왼쪽 끝
            ph - 40,              # 하단에서 40pt 위
            pw * 0.40,            # 페이지 너비의 40%까지
            ph                    # 하단 끝
        )
        
        # 하단 우측 영역 (성명 부분)
        right_bottom = fitz.Rect(
            pw * 0.60,            # 페이지 너비의 60%부터
            ph - 40,              # 하단에서 40pt 위
            pw,                   # 오른쪽 끝
            ph                    # 하단 끝
        )
        
        shape = page.new_shape()
        shape.draw_rect(left_bottom)
        shape.draw_rect(right_bottom)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # 수정된 PDF를 바이트로 저장
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
    이 앱은 학교생활기록부 등의 PDF 문서에서 개인정보를 자동으로 삭제합니다.
    
    **처리 항목:**
    - ✅ 학교명 (텍스트 검색: "○○고등학교")
    - ✅ 학년별 학과/반/번호/담임 정보
    - ✅ 이름, 주민등록번호, 주소
    - ✅ 학적사항 (졸업/입학 정보)
    - ✅ 출결 데이터
    - ✅ 사진
    - ✅ 모든 페이지 하단의 반/번호/성명
    
    ⚠️ **주의:** 최대 23페이지까지 처리 가능합니다.
    """)
    
    # 파일 업로드
    uploaded_file = st.file_uploader(
        "PDF 파일을 업로드하세요",
        type=['pdf'],
        help="학교생활기록부 PDF 파일 (최대 23페이지)"
    )
    
    if uploaded_file is not None:
        # 파일 정보 표시
        st.info(f"📄 업로드된 파일: {uploaded_file.name}")
        
        # 처리 버튼
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            process_button = st.button(
                "🔒 개인정보 보호 처리 시작", 
                type="primary",
                use_container_width=True
            )
        
        if process_button:
            with st.spinner("처리 중입니다... 잠시만 기다려주세요."):
                try:
                    # PDF 읽기
                    pdf_bytes = uploaded_file.read()
                    
                    # 페이지 수 확인
                    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    num_pages = len(pdf_doc)
                    pdf_doc.close()
                    
                    if num_pages > 23:
                        st.error(f"❌ 페이지 수가 너무 많습니다. (현재: {num_pages}페이지, 최대: 23페이지)")
                        return
                    
                    st.success(f"✅ PDF 문서 로드 완료 (총 {num_pages}페이지)")
                    
                    # 개인정보 삭제 처리
                    with st.spinner("개인정보를 삭제하는 중..."):
                        redacted_pdf = redact_pdf(pdf_bytes)
                    
                    st.success("✅ 개인정보 보호 처리가 완료되었습니다!")
                    
                    # 다운로드 버튼
                    st.download_button(
                        label="📥 보호된 PDF 다운로드",
                        data=redacted_pdf,
                        file_name="private_protected_document.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.info("💡 다운로드한 파일을 열어 개인정보가 제대로 삭제되었는지 확인하세요.")
                    
                except Exception as e:
                    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                    st.exception(e)  # 상세 오류 표시
    
    # 사용 방법 안내
    with st.expander("ℹ️ 사용 방법"):
        st.markdown("""
        ### 📋 단계별 가이드
        
        1. **파일 선택**: 상단의 파일 업로드 버튼을 클릭하여 PDF를 선택합니다.
        2. **처리 시작**: "개인정보 보호 처리 시작" 버튼을 클릭합니다.
        3. **다운로드**: 처리 완료 후 "보호된 PDF 다운로드" 버튼을 클릭합니다.
        4. **확인**: 다운로드한 파일을 PDF 뷰어로 열어 확인합니다.
        
        ### ✅ 처리되는 정보
        
        | 항목 | 처리 방식 |
        |------|----------|
        | 학교명 | 텍스트 검색 후 덮기 |
        | 이름/주민번호/주소 | 좌표 기반 영역 삭제 |
        | 반/번호/담임 | 좌표 기반 영역 삭제 |
        | 사진 | 좌표 기반 영역 삭제 |
        | 페이지 하단 정보 | 좌표 기반 영역 삭제 |
        """)
    
    # 주의사항
    with st.expander("⚠️ 주의사항 및 제한사항"):
        st.markdown("""
        ### 🚨 필독 사항
        
        - ✔️ **결과물 확인 필수**: 자동 처리이므로 반드시 최종 결과를 확인하세요.
        - ✔️ **PDF 형식**: 표준 PDF 형식만 지원됩니다.
        - ✔️ **페이지 제한**: 최대 23페이지까지 처리 가능합니다.
        - ✔️ **원본 보관**: 처리 전 원본 파일은 별도 보관하세요.
        - ✔️ **보안**: 업로드된 파일은 서버에 저장되지 않습니다.
        
        ### 🔧 문제 발생 시
        
        - PDF 구조가 특이한 경우 일부 정보가 남을 수 있습니다.
        - 스캔된 이미지 PDF는 지원하지 않습니다.
        - 문제 발생 시 원본 파일의 구조를 확인해주세요.
        """)
    
    # 푸터
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "🔒 개인정보 보호 도구 v2.0 | "
        "PyMuPDF & Streamlit"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
