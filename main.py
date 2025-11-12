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
            def inset_rect(x0, y0, x1, y1, dx_ratio=0.004, dy_ratio=0.004):
                dx = pw * dx_ratio
                dy = ph * dy_ratio
                return fitz.Rect(x0 + dx, y0 + dy, x1 - dx, y1 - dy)

            # --- 1페이지 특정 영역 마스킹 ---
            if page_num == 0:
                # 1) 상단 첫 번째 표: 사진 칸
                photo_cell = fitz.Rect(
                    pw * 0.028, ph * 0.038,
                    pw * 0.208, ph * 0.162
                )
                photo_rect = inset_rect(photo_cell.x0, photo_cell.y0, photo_cell.x1, photo_cell.y1,
                                        dx_ratio=0.010, dy_ratio=0.010)
                page.add_redact_annot(photo_rect, fill=(1, 1, 1))

                # 2) 반/번호/담임성명 내용 영역 (표 테두리는 유지)
                table_right_block = fitz.Rect(
                    pw * 0.52, ph * 0.052,
                    pw * 0.985, ph * 0.150
                )
                table_content_rect = inset_rect(table_right_block.x0, table_right_block.y0,
                                                table_right_block.x1, table_right_block.y1,
                                                dx_ratio=0.010, dy_ratio=0.012)
                page.add_redact_annot(table_content_rect, fill=(1, 1, 1))

                # 3) 인적·학적사항 표 내부 내용만 마스킹
                student_info_line = fitz.Rect(
                    pw * 0.125, ph * 0.162,
                    pw * 0.985, ph * 0.193
                )
                student_info_rect = inset_rect(student_info_line.x0, student_info_line.y0,
                                               student_info_line.x1, student_info_line.y1,
                                               dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(student_info_rect, fill=(1, 1, 1))

                address_line = fitz.Rect(
                    pw * 0.090, ph * 0.198,
                    pw * 0.985, ph * 0.228
                )
                address_rect = inset_rect(address_line.x0, address_line.y0,
                                          address_line.x1, address_line.y1,
                                          dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(address_rect, fill=(1, 1, 1))

                academic_block = fitz.Rect(
                    pw * 0.125, ph * 0.232,
                    pw * 0.985, ph * 0.268
                )
                academic_rect = inset_rect(academic_block.x0, academic_block.y0,
                                           academic_block.x1, academic_block.y1,
                                           dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(academic_rect, fill=(1, 1, 1))

                notes_block = fitz.Rect(
                    pw * 0.125, ph * 0.274,
                    pw * 0.985, ph * 0.335
                )
                notes_rect = inset_rect(notes_block.x0, notes_block.y0,
                                        notes_block.x1, notes_block.y1,
                                        dx_ratio=0.006, dy_ratio=0.006)
                page.add_redact_annot(notes_rect, fill=(1, 1, 1))

            # --- "(고등학교)" 키워드 검색 및 마스킹 ---
            search_texts = ["대성고등학교", "상명대학교사범대학부속여자고등학교", "(", "고등학교"] 
            for text in search_texts:
                try:
                    for inst in page.search_for(text):
                        page.add_redact_annot(inst, fill=(1, 1, 1))
                except Exception:
                    # 검색 실패 시에도 앱이 멈추지 않도록
                    pass

            # --- 모든 페이지 맨 하단의 개인정보 마스킹 ---
            header_thin = fitz.Rect(0, 0, pw, ph * 0.015)
            page.add_redact_annot(header_thin, fill=(1, 1, 1))

            footer_slash = fitz.Rect(
                pw * 0.010, ph * 0.978,
                pw * 0.055, ph * 0.994
            )
            page.add_redact_annot(footer_slash, fill=(1, 1, 1))

            footer_block = fitz.Rect(
                pw * 0.60, ph * 0.977,
                pw * 0.995, ph * 0.996
            )
            footer_bottom_rect = inset_rect(footer_block.x0, footer_block.y0,
                                            footer_block.x1, footer_block.y1,
                                            dx_ratio=0.006, dy_ratio=0.003)
            page.add_redact_annot(footer_bottom_rect, fill=(1, 1, 1))

            footer_hairline = fitz.Rect(
                pw * 0.58, ph * 0.996,
                pw * 0.995, ph * 1.000
            )
            footer_bottom_hairline_rect = inset_rect(footer_hairline.x0, footer_hairline.y0,
                                                     footer_hairline.x1, footer_hairline.y1,
                                                     dx_ratio=0.004, dy_ratio=0.000)
            page.add_redact_annot(footer_bottom_hairline_rect, fill=(1, 1, 1))

            page.apply_redactions()

        # 결과 반환
        output_bytes = doc.tobytes()
        doc.close()
        return output_bytes

    except Exception as e:
        st.error(f"PDF 처리 중 오류가 발생했습니다: {e}")
        return None


# --- Streamlit UI ---

st.set_page_config(page_title="PDF 개인정보 보호 앱", page_icon="🔒")

st.title("🔒 PDF 민감정보 마스킹 앱")
st.write("학교생활기록부 PDF를 업로드하면, 사진·성명·주소 등 민감정보만 흰색으로 마스킹합니다.")
st.write("*(최대 23페이지까지 처리됩니다)*")

uploaded_file = st.file_uploader("PDF 파일 업로드 (23페이지 이내)", type=["pdf"])

if uploaded_file is not None:
    input_pdf_bytes = uploaded_file.getvalue()
    st.write("📄 파일 업로드 완료. 민감정보 처리 중...")

    with st.spinner('민감정보 마스킹 작업 진행 중...'):
        redacted_pdf_bytes = redact_sensitive_info(input_pdf_bytes)

    if redacted_pdf_bytes:
        st.success("✅ 민감정보 처리가 완료되었습니다.")
        filename = uploaded_file.name.replace(".pdf", "_masked.pdf")
        st.download_button("처리된 PDF 다운로드", data=redacted_pdf_bytes,
                           file_name=filename, mime="application/pdf")
    else:
        st.error("❌ 파일 처리 중 오류가 발생했습니다.")
