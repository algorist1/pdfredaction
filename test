import pytesseract

   # 확인된 경로 지정
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

   try:
       version = pytesseract.get_tesseract_version()
       print(f"✅ Tesseract 정상 작동! 버전: {version}")
   except Exception as e:
       print(f"❌ 오류 발생: {e}")
