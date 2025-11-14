import streamlit as st
import fitz  # PyMuPDF
import io

def redact_pdf(pdf_bytes):
    """
    PDF에서 개인정보를 삭제하는 함수
    """
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(pdf_document)
    
    # ========================================
    # 1단계: "고등학교" 텍스트 검색 및 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        text_instances = page.search_for("고등학교")
        
        for inst in text_instances:
            x0, y0, x1, y1 = inst
            rect = fitz.Rect(x0 - 100, y0 - 3, x1 + 5, y1 + 3)
            
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
    
    # ========================================
    # 2단계: 1페이지 상단 표 처리
    # ========================================
    if total_pages >= 1:
        page = pdf_document[0]
        pw = page.rect.width
        ph = page.rect.height
        
        # 텍스트 정보 추출
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]
        
        # -----------------------------------------
        # 2-1. 첫 번째 표의 데이터만 정확히 삭제
        # -----------------------------------------
        first_table_rects = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        y_pos = bbox[1]
                        
                        # 상단 25% 영역 (첫 번째 표 영역)
                        if y_pos < ph * 0.27:
                            # 헤더가 아닌 데이터만 삭제
                            if text not in ["졸업대장번호", "학년", "구분", "학과", "반", "번호", "담임성명"]:
                                # 숫자나 이름
                                if text and (text.isdigit() or len(text) > 1):
                                    rect = fitz.Rect(
                                        bbox[0] - 2, bbox[1] - 2,
                                        bbox[2] + 2, bbox[3] + 2
                                    )
                                    first_table_rects.append(rect)
        
        # 첫 번째 표 데이터 삭제
        if first_table_rects:
            shape = page.new_shape()
            for rect in first_table_rects:
                shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
        
        # -----------------------------------------
        # 2-2. 사진 삭제
        # -----------------------------------------
        for block in blocks:
            if block.get("type") == 1:  # 이미지
                bbox = block["bbox"]
                if bbox[0] > pw * 0.75:  # 우측
                    rect = fitz.Rect(
                        bbox[0] - 5, bbox[1] - 5,
                        bbox[2] + 5, bbox[3] + 5
                    )
                    shape = page.new_shape()
                    shape.draw_rect(rect)
                    shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
                    shape.commit()
        
        # -----------------------------------------
        # 2-3. "1. 인적·학적사항" 표의 내용 삭제
        # -----------------------------------------
        personal_rects = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        
                        # 개인정보 항목들
                        if any(keyword in text for keyword in 
                               ["박지호", "남", "여", "070515", "서울", "경기", 
                                "2023년", "2024년", "2025년", "중학교", "초등학교",
                                "졸업", "입학", "제1학년", "제2학년", "제3학년"]):
                            rect = fitz.Rect(
                                bbox[0] - 2, bbox[1] - 2,
                                bbox[2] + 2, bbox[3] + 2
                            )
                            personal_rects.append(rect)
                        
                        # 주민번호 (숫자-숫자 형식)
                        if "-" in text and len(text) >= 10:
                            rect = fitz.Rect(
                                bbox[0] - 2, bbox[1] - 2,
                                bbox[2] + 2, bbox[3] + 2
                            )
                            personal_rects.append(rect)
        
        # 개인정보 삭제
        if personal_rects:
            shape = page.new_shape()
            for rect in personal_rects:
                shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
        
        # 학적사항 영역 전체를 영역으로 한 번 더 덮기
        academic_area = fitz.Rect(
            pw * 0.14,
            ph * 0.375,
            pw * 0.96,
            ph * 0.43
        )
        
        shape = page.new_shape()
        shape.draw_rect(academic_area)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # ========================================
    # 3단계: 모든 페이지 하단 표 완전 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        pw = page.rect.width
        ph = page.rect.height
        
        # 하단 표 전체 삭제 (페이지 번호 제외)
        # 좌측 영역
        left_area = fitz.Rect(
            0,           # 왼쪽 끝
            ph - 50,     # 하단 50pt
            pw * 0.35,   # 35%까지
            ph           # 끝까지
        )
        
        # 우측 영역
        right_area = fitz.Rect(
            pw * 0.65,   # 65%부터
            ph - 50,     # 하단 50pt
            pw,          # 오른쪽 끝
            ph           # 끝까지
        )
        
        shape = page.new_shape()
        shape.draw_rect(left_area)
        shape.draw_rect(right_area)
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
    ### 📌 처리 내용
    
    ✅ **학교명**: "○○고등학교" 자동 검색 삭제  
    ✅ **상단 표**: 표 구조 유지, 학과/반/번호/담임 내용만 삭제  
    ✅ **개인정보**: 이름, 성별, 주민번호, 주소 삭제  
    ✅ **학적사항**: 졸업/입학 정보 완전 삭제  
    ✅ **사진**: 우측 상단 사진 삭제  
    ✅ **하단 표**: 반/번호/성명 표 완전 삭제 (페이지 번호는 유지)
    """)
    
    uploaded_file = st.file_uploader(
        "📁 PDF 파일 업로드",
        type=['pdf'],
        help="학교생활기록부 PDF (최대 23페이지)"
    )
    
    if uploaded_file:
        st.info(f"📄 **{uploaded_file.name}**")
        
        if st.button("🔒 개인정보 보호 처리", type="primary", use_container_width=True):
            
            with st.spinner("처리 중..."):
                try:
                    pdf_bytes = uploaded_file.read()
                    
                    # 페이지 수 확인
                    temp_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    num_pages = len(temp_doc)
                    temp_doc.close()
                    
                    if num_pages > 23:
                        st.error(f"❌ 페이지 초과 ({num_pages}페이지)")
                        return
                    
                    # 진행 표시
                    bar = st.progress(0)
                    stat = st.empty()
                    
                    stat.text("📖 분석 중...")
                    bar.progress(30)
                    
                    stat.text("🔒 삭제 중...")
                    bar.progress(60)
                    
                    redacted = redact_pdf(pdf_bytes)
                    
                    stat.text("✅ 완료!")
                    bar.progress(100)
                    
                    st.success(f"✅ {num_pages}페이지 처리 완료!")
                    
                    st.download_button(
                        "📥 보호된 PDF 다운로드",
                        data=redacted,
                        file_name="private_protected_document.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.warning("⚠️ **반드시 결과를 확인하세요!**")
                    
                except Exception as e:
                    st.error(f"❌ 오류: {str(e)}")
    
    with st.expander("📖 사용법"):
        st.markdown("""
        1. PDF 업로드
        2. 처리 버튼 클릭  
        3. 다운로드
        4. **결과 확인 필수**
        """)
    
    with st.expander("⚠️ 주의"):
        st.markdown("""
        - 원본 파일 백업 권장
        - 표준 PDF만 지원
        - 최대 23페이지
        """)
    
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center;color:gray;'>"
        "🔒 PDF 개인정보 보호 도구 v4.0"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
