from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF สำหรับสกัดข้อความ PDF ขั้นสูง
from pythainlp.util import normalize as thai_normalize
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

def extract_and_clean_pdf(file_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        paragraphs = []
        
        for page in doc:
            # 1. ดึงข้อความทีละ Block (PyMuPDF จะตรวจจับโครงสร้าง "ย่อหน้า" ให้อัตโนมัติ)
            blocks = page.get_text("blocks")
            # เรียงบล็อกตามพิกัด (บนลงล่าง ซ้ายไปขวา)
            blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
            
            for b in blocks:
                if b[6] == 0:  # Type 0 คือ Text Block (ข้อความปกติ)
                    block_text = b[4].strip()
                    if block_text:
                        # 2. ฟิวชันคำไทยที่ถูกหั่นครึ่ง (เช่น มุ่ง\nเน้น -> มุ่งเน้น)
                        # วนลูปกำจัด \n ที่คั่นระหว่างพยัญชนะไทย เพื่อสมานคำที่ถูกตัดบรรทัด
                        prev = ""
                        while prev != block_text:
                            prev = block_text
                            block_text = re.sub(r'([\u0E00-\u0E7F])\r?\n([\u0E00-\u0E7F])', r'\1\2', block_text)
                        
                        # 3. เคลียร์ \n ที่ยังเหลืออยู่ในย่อหน้า เปลี่ยนเป็นช่องว่าง (เพื่อให้ไหลต่อเนื่องแบบ Word)
                        block_text = re.sub(r'\r?\n', ' ', block_text)
                        
                        paragraphs.append(block_text)
        
        # 4. ประกอบบล็อกทั้งหมดกลับเป็นย่อหน้า คั่นด้วยการขึ้นบรรทัดใหม่
        full_text = "\n\n".join(paragraphs)
        
        # 5. แก้ปัญหาสระอำกระจัดกระจายระดับ Unicode (ไม่ต้องพึ่งพจนานุกรม)
        # ลบช่องว่างที่คั่นระหว่างพยัญชนะ กับ นิคหิต(วงกลม ํ) หรือ สระอา/สระอำ
        full_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำา\u0E4D])', r'\1\2', full_text)
        
        # 6. พลังของ PyThaiNLP: หลอมรวม นิคหิต + สระอา ให้กลายเป็น "สระอำ" อัตโนมัติตามหลักภาษา
        normalized_text = thai_normalize(full_text)
        
        # 7. จัดระเบียบช่องว่างที่ซ้ำซ้อนให้เหลือเคาะเดียว
        final_paras = [re.sub(r' {2,}', ' ', p).strip() for p in normalized_text.split("\n\n") if p.strip()]
        
        return "\n\n".join(final_paras)
        
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
