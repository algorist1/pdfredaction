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
    # 텍스트 검색 기반 삭제 규칙
    # ========================================
    # 모든 페이지에서 특정 문구 검색 및 덮기
    search_text = "고등학교"  # 검색할 텍스트
    
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        
        # 1~2페이지(수상경력), 5~6페이지(봉사활동), 모든 페이지 하단에서 학교명 삭제
        if page_num in [0, 1, 4, 5] or True:  # 실제로는 모든 페이지 처리
            # 텍스트 검색
            text_instances = page.search_for(search_text)
            
            for inst in text_instances:
                # 검색된 텍스트 영역의 좌표
                x0, y0, x1, y1 = inst
                
                # 학교명 앞뒤로 약간의 여백을 포함하여 덮기
                # "대성고등학교", "○○고등학교" 등 다양한 형태 처리
                padding = 50  # 좌우 여백 (학교명 전체를 덮기 위해)
                
                # 흰색 사각형으로 덮기
                rect = fitz.Rect(x0 - padding, y0 - 2, x1 + padding, y1 + 2)
                
                # 페이지 하단 영역인지 확인 (y 좌표가 페이지 높이의 90% 이상)
                page_height = page.rect.height
                if y0 > page_height * 0.9:
                    # 하단 영역이면 더 넓게 덮기 (반, 번호, 성명 포함)
                    rect = fitz.Rect(50, y0 - 10, page.rect.width - 50, y1 + 10)
                
                # 흰색 사각형 그리기
                shape = page.new_shape()
                shape.draw_rect(rect)
                shape.finish(color=(1, 1, 1), fill=(1, 1, 1))  # 흰색 채우기
                shape.commit()
    
    # ========================================
    # 좌표 기반 영역 삭제 규칙
    # ========================================
    
    # 1페이지: 상단 첫 번째 표 (반, 번호, 담임성명, 사진)
    if total_pages >= 1:
        page = pdf_document[0]
        page_width = page.rect.width
        page_height = page.rect.height
        
        # 첫 번째 표의 데이터 영역 (표 테두리는 유지)
        # 실제 좌표는 PDF 구조에 따라 조정 필요
        first_table_areas = [
            fitz.Rect(page_width * 0.15, page_height * 0.08, 
                     page_width * 0.35, page_height * 0.12),  # 반/번호
            fitz.Rect(page_width * 0.35, page_height * 0.08,
                     page_width * 0.60, page_height * 0.12),  # 담임성명
            fitz.Rect(page_width * 0.85, page_height * 0.06,
                     page_width * 0.97, page_height * 0.13),  # 사진
        ]
        
        shape = page.new_shape()
        for rect in first_table_areas:
            shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
        
        # 두 번째 표: 1. 인적·학적사항
        personal_info_areas = [
            # 성명, 성별, 주민등록번호 행
            fitz.Rect(page_width * 0.15, page_height * 0.165,
                     page_width * 0.95, page_height * 0.195),
            # 주소 행
            fitz.Rect(page_width * 0.15, page_height * 0.195,
                     page_width * 0.95, page_height * 0.225),
            # 학적사항 영역
            fitz.Rect(page_width * 0.15, page_height * 0.23,
                     page_width * 0.95, page_height * 0.27),
            # 특기사항 영역
            fitz.Rect(page_width * 0.15, page_height * 0.28,
                     page_width * 0.95, page_height * 0.35),
        ]
        
        shape = page.new_shape()
        for rect in personal_info_areas:
            shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # 모든 페이지 하단: 반, 번호, 성명 표 전체 삭제 (페이지 번호 제외)
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        
        # 하단 표 영역 (페이지 번호는 중앙에 있으므로 좌우로 나눠서 처리)
        # 좌측 영역
        left_rect = fitz.Rect(0, page_height * 0.95, 
                             page_width * 0.35, page_height)
        # 우측 영역  
        right_rect = fitz.Rect(page_width * 0.65, page_height * 0.95,
                              page_width, page_height)
        
        shape = page.new_shape()
        shape.draw_rect(left_rect)
        shape.draw_rect(right_rect)
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
    - 학교명 (표 내부 및 하단)
    - 이름, 주민등록번호, 주소
    - 반, 번호, 담임 교사명, 사진
    
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
        if st.button("🔒 개인정보 보호 처리 시작", type="primary"):
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
                    redacted_pdf = redact_pdf(pdf_bytes)
                    
                    st.success("✅ 개인정보 보호 처리가 완료되었습니다!")
                    
                    # 다운로드 버튼
                    st.download_button(
                        label="📥 보호된 PDF 다운로드",
                        data=redacted_pdf,
                        file_name="private_protected_document.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                    
                    st.info("💡 다운로드한 파일을 열어 개인정보가 제대로 삭제되었는지 확인하세요.")
                    
                except Exception as e:
                    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                    st.error("파일 형식이나 내용을 확인해주세요.")
    
    # 사용 방법 안내
    with st.expander("ℹ️ 사용 방법"):
        st.markdown("""
        1. **PDF 파일 업로드**: 위의 파일 선택 버튼을 클릭하여 PDF를 업로드합니다.
        2. **처리 시작**: "개인정보 보호 처리 시작" 버튼을 클릭합니다.
        3. **다운로드**: 처리가 완료되면 "보호된 PDF 다운로드" 버튼이 나타납니다.
        4. **확인**: 다운로드한 파일을 열어 개인정보가 제대로 삭제되었는지 확인합니다.
        
        **처리되는 정보:**
        - ✅ 학교명 (텍스트 검색 방식)
        - ✅ 개인 신상정보 (이름, 주민번호, 주소 등)
        - ✅ 학급 정보 (반, 번호, 담임)
        - ✅ 사진
        """)
    
    # 주의사항
    with st.expander("⚠️ 주의사항"):
        st.markdown("""
        - 이 도구는 자동화된 처리를 수행하므로, 반드시 결과물을 직접 확인하세요.
        - PDF 구조가 예상과 다를 경우 일부 정보가 누락될 수 있습니다.
        - 처리 전 원본 파일은 별도로 백업하는 것을 권장합니다.
        - 민감한 개인정보가 포함된 문서는 안전하게 관리하세요.
        """)


if __name__ == "__main__":
    main()
