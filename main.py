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
            
            # 학교명 전체를 덮기 위해 왼쪽으로 확장
            rect = fitz.Rect(x0 - 100, y0 - 3, x1 + 5, y1 + 3)
            
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
            shape.commit()
    
    # ========================================
    # 2단계: 1페이지 개인정보 영역 삭제
    # ========================================
    if total_pages >= 1:
        page = pdf_document[0]
        
        # 페이지 텍스트 추출하여 좌표 찾기
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]
        
        # 삭제할 영역들을 저장
        rects_to_redact = []
        
        # -----------------------------------------
        # 2-1. 상단 표에서 개인정보 찾기
        # -----------------------------------------
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        
                        # 학년/학과/반/번호 표에서 숫자 데이터 삭제
                        if text.isdigit() and len(text) <= 2:
                            # y 좌표가 페이지 상단 20% 이내인 경우
                            if bbox[1] < page.rect.height * 0.25:
                                rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2, 
                                               bbox[2] + 2, bbox[3] + 2)
                                rects_to_redact.append(rect)
                        
                        # 담임 성명 삭제
                        if "이혜원" in text or "김정훈" in text or "노지호" in text:
                            rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                           bbox[2] + 2, bbox[3] + 2)
                            rects_to_redact.append(rect)
        
        # -----------------------------------------
        # 2-2. "1. 인적" 섹션의 개인정보 삭제
        # -----------------------------------------
        found_personal_section = False
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    
                    # "1. 인적" 섹션 시작 확인
                    if "1. 인적" in line_text or "학생정보" in line_text:
                        found_personal_section = True
                    
                    # 개인정보가 있는 섹션에서 삭제
                    if found_personal_section:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            bbox = span["bbox"]
                            
                            # 이름
                            if "박지호" in text:
                                rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                               bbox[2] + 2, bbox[3] + 2)
                                rects_to_redact.append(rect)
                            
                            # 성별
                            if text == "남" or text == "여":
                                rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                               bbox[2] + 2, bbox[3] + 2)
                                rects_to_redact.append(rect)
                            
                            # 주민등록번호 (숫자-숫자 형식)
                            if "-" in text and any(c.isdigit() for c in text):
                                if len(text) > 10:  # 주민번호 길이
                                    rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                                   bbox[2] + 2, bbox[3] + 2)
                                    rects_to_redact.append(rect)
                            
                            # 주소 (서울, 경기 등이 포함된 긴 텍스트)
                            if ("서울" in text or "경기" in text) and len(text) > 10:
                                rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                               bbox[2] + 2, bbox[3] + 2)
                                rects_to_redact.append(rect)
                            
                            # 학교명 (졸업/입학 정보)
                            if "진관중학교" in text or "진관초" in text:
                                rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                               bbox[2] + 2, bbox[3] + 2)
                                rects_to_redact.append(rect)
                    
                    # "2. 출결" 섹션이 나오면 개인정보 섹션 종료
                    if "2. 출결" in line_text:
                        found_personal_section = False
        
        # -----------------------------------------
        # 2-3. 사진 영역 삭제
        # -----------------------------------------
        # 이미지 블록 찾기
        for block in blocks:
            if block["type"] == 1:  # 이미지 블록
                bbox = block["bbox"]
                # 페이지 우측 상단의 사진
                if bbox[0] > page.rect.width * 0.75:
                    rect = fitz.Rect(bbox[0] - 5, bbox[1] - 5,
                                   bbox[2] + 5, bbox[3] + 5)
                    rects_to_redact.append(rect)
        
        # 모든 영역 삭제 실행
        shape = page.new_shape()
        for rect in rects_to_redact:
            shape.draw_rect(rect)
        shape.finish(color=(1, 1, 1), fill=(1, 1, 1))
        shape.commit()
    
    # ========================================
    # 3단계: 모든 페이지 하단의 "반 ○ 번호 ○ 성명 ○○○" 삭제
    # ========================================
    for page_num in range(total_pages):
        page = pdf_document[page_num]
        page_height = page.rect.height
        page_width = page.rect.width
        
        # 텍스트 추출
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]
        
        # 하단 10% 영역에서 "반", "번호", "성명" 찾기
        bottom_rects = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        
                        # 하단 영역인지 확인 (페이지 높이의 90% 이상)
                        if bbox[1] > page_height * 0.90:
                            # "반", "번호", "성명" 및 그 뒤의 값들
                            if (text in ["반", "번호", "성명"] or 
                                text.isdigit() or
                                any(c.isalpha() for c in text)):  # 이름
                                
                                # 페이지 번호는 제외 (중앙 20% 영역)
                                if not (page_width * 0.40 < bbox[0] < page_width * 0.60):
                                    rect = fitz.Rect(bbox[0] - 2, bbox[1] - 2,
                                                   bbox[2] + 2, bbox[3] + 2)
                                    bottom_rects.append(rect)
        
        # 하단 영역 삭제
        if bottom_rects:
            shape = page.new_shape()
            for rect in bottom_rects:
                shape.draw_rect(rect)
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
    
    ✅ **학교명**: "○○고등학교" 텍스트 검색하여 삭제  
    ✅ **개인정보**: 이름, 성별, 주민등록번호, 주소  
    ✅ **학급정보**: 학년, 반, 번호, 담임 성명  
    ✅ **사진**: 우측 상단 학생 사진  
    ✅ **하단정보**: 모든 페이지 하단의 반/번호/성명 (페이지 번호는 보존)
    """)
    
    uploaded_file = st.file_uploader(
        "📁 PDF 파일을 업로드하세요",
        type=['pdf'],
        help="학교생활기록부 PDF (최대 23페이지)"
    )
    
    if uploaded_file is not None:
        st.info(f"📄 **{uploaded_file.name}** 업로드 완료")
        
        if st.button("🔒 개인정보 보호 처리 시작", type="primary", use_container_width=True):
            
            with st.spinner("🔄 처리 중입니다..."):
                try:
                    pdf_bytes = uploaded_file.read()
                    
                    # 페이지 수 확인
                    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    num_pages = len(pdf_doc)
                    pdf_doc.close()
                    
                    if num_pages > 23:
                        st.error(f"❌ 페이지 수 초과 (현재: {num_pages}페이지, 최대: 23페이지)")
                        return
                    
                    st.success(f"✅ PDF 로드 완료 ({num_pages}페이지)")
                    
                    # 처리 실행
                    redacted_pdf = redact_pdf(pdf_bytes)
                    
                    st.success("✅ 개인정보 보호 처리 완료!")
                    
                    # 다운로드 버튼
                    st.download_button(
                        label="📥 보호된 PDF 다운로드",
                        data=redacted_pdf,
                        file_name="private_protected_document.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.info("💡 **확인 필수**: 다운로드한 파일을 열어 모든 개인정보가 삭제되었는지 확인하세요.")
                    
                except Exception as e:
                    st.error(f"❌ 오류 발생: {str(e)}")
                    with st.expander("🔍 상세 오류 정보"):
                        st.exception(e)
    
    with st.expander("ℹ️ 사용 방법"):
        st.markdown("""
        1. 📤 PDF 파일 업로드
        2. 🔒 "처리 시작" 버튼 클릭
        3. 📥 처리된 PDF 다운로드
        4. ✔️ 결과 확인
        """)
    
    with st.expander("⚠️ 주의사항"):
        st.markdown("""
        - 반드시 결과물을 확인하세요
        - 원본 파일은 별도 보관하세요
        - 표준 PDF 형식만 지원됩니다
        - 스캔된 이미지는 지원하지 않습니다
        """)


if __name__ == "__main__":
    main()
