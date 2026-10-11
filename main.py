from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
from pythainlp.util import normalize as thai_normalize
from pythainlp.corpus import thai_words
import uvicorn
import re
import os

app = FastAPI(title="e-GovDoc Python Backend Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👑 หัวใจสำคัญ: โหลดพจนานุกรมภาษาไทยมาตรฐาน (Library-based, ปลอดฮาร์ดโค้ด 100%)
THAI_DICT = set(thai_words())

def extract_and_clean_pdf(file_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        
        # 1. สกัดข้อความแบบอนุรักษ์โครงสร้าง (รักษา \n ไว้เป๊ะๆ เพื่อไม่ให้ข้อความไหลชนกัน)
        for page in doc:
            full_text += page.get_text("text") + "\n"
        
        # 2. แก้ไขช่องว่างทางกายภาพที่ผิดปกติจาก PDF (เช่น ส าคัญ -> สำคัญ)
        full_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำา])', r'\1ำ', full_text)
        
        # 3. 🧠 Smart Dictionary Auto-Correction (แก้ ดาเนิน -> ดำเนิน โดยไม่ฮาร์ดโค้ด)
        # หาพิกัดของพยัญชนะ [ก-ฮ] ที่ตามด้วย 'า' ทั้งหมดในเอกสาร
        indices = [m.start() for m in re.finditer(r'(?<!เ)[ก-ฮ]า', full_text)]
        text_list = list(full_text)
        
        for idx in indices:
            a_idx = idx + 1  # ตำแหน่งของสระ 'า'
            
            # สร้าง Window สแกนหาคำที่เป็นไปได้รอบๆ จุดนั้น (ความยาว 2 ถึง 15 ตัวอักษร)
            for length in range(15, 1, -1):
                end_idx = idx + length
                if end_idx <= len(text_list):
                    original_chunk = "".join(text_list[idx:end_idx])
                    cand_chunk = original_chunk.replace('า', 'ำ', 1)
                    
                    # ตรรกะอัจฉริยะ: ถ้าเปลี่ยนเป็น ำ แล้วเป็นคำที่ถูกต้องในดิกชันนารี 
                    # และคำเดิมที่ใช้ า ไม่มีความหมาย -> ถือว่าเป็น Typo จาก PDF แน่นอน! ฟันธงแก้ทันที!
                    if cand_chunk in THAI_DICT and original_chunk not in THAI_DICT:
                        text_list[a_idx] = 'ำ'
                        break  # แก้ไขสำเร็จ ข้ามไปจุดต่อไป
                        
        corrected_text = "".join(text_list)
        
        # 4. ทำความสะอาด Unicode ขั้นสุดท้ายด้วย PyThaiNLP
        normalized_text = thai_normalize(corrected_text)
        
        # 5. จัดระเบียบตัดช่องว่างหัวท้ายบรรทัด แต่ยังคงรักษาย่อหน้า \n ไว้ตามต้นฉบับ 100%
        final_lines = [line.strip() for line in normalized_text.splitlines()]
        return "\n".join(l for l in final_lines if l)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถอ่านไฟล์ PDF ได้: {str(e)}")

@app.get("/")
def root():
    return {"status": "ok", "message": "e-GovDoc Python Backend is running smoothly!"}

@app.post("/api/extract-pdf")
async def extract_pdf_endpoint(file: UploadFile = File(...)):
    file_bytes = await file.read()
    extracted_text = extract_and_clean_pdf(file_bytes)
    return {"success": True, "text": extracted_text}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
