from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
from pythainlp.util import normalize as thai_normalize
import uvicorn
import re
import io
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
        full_text_list = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # ดึงข้อความด้วย pdfplumber โดยรักษา Layout และช่องว่างระหว่างคำ (Spacebar) ต้นฉบับไว้ครบถ้วน
                text = page.extract_text(layout=False)
                if text:
                    full_text_list.append(text)
        
        full_text = "\n".join(full_text_list)
        
        # 👑 ใช้ PyThaiNLP normalize มาตรฐานสากลเท่านั้น (ยกเลิก Regex แปลงสระอำทั้งหมด เพื่อปกป้องคำว่า ตุลาคม, เวลา, ฯลฯ)
        normalized_text = thai_normalize(full_text)
        
        # จัดระเบียบบรรทัด โดยคง Spacebar และโครงสร้างเดิมไว้ ไม่ให้คำติดกันหรือเพี้ยน
        lines = normalized_text.splitlines()
        cleaned_lines = []
        for line in lines:
            # ทำความสะอาดเฉพาะช่องว่างส่วนเกิน แต่ไม่แตะต้องตัวอักษรหรือคำศัพท์ของผู้ใช้
            cleaned_line = re.sub(r'[ \t]+', ' ', line).strip()
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
                
        return "\n".join(cleaned_lines)
        
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
