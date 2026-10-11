from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF สำหรับสกัดข้อความ PDF
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
        full_text = ""
        for page in doc:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (round(b[1] / 5) * 5, b[0]))
            for b in blocks:
                block_text = b[4].strip()
                if block_text:
                    full_text += block_text + "\n"
        
        # 👑 ระบบอัตโนมัติ Python RegEx: แปลงพยัญชนะที่ตามด้วยช่องว่างและสระอา/สระอำ ให้เป็นสระอำ (ำ)
        # โดยมีเกราะป้องกัน (Negative Lookbehind) ไม่ให้ไปกระทบโครงสร้างสระเอา (เ-า)
        cleaned_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำา])', r'\1ำ', full_text)
        
        # ทำความสะอาดมาตรฐานด้วย PyThaiNLP และ Unicode NFC
        normalized_text = thai_normalize(cleaned_text)
        
        # จัดระเบียบช่องว่างส่วนเกินในแต่ละบรรทัดให้เรียบร้อย
        lines = normalized_text.splitlines()
        final_lines = [re.sub(r'\s+', ' ', line).strip() for line in lines if line.strip()]
        return "\n".join(final_lines)
        
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
