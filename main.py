from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
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
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
            
            for b in blocks:
                if b[6] == 0:  # Text block
                    block_text = b[4].strip()
                    if block_text:
                        # 1. เชื่อมคำไทยที่ถูกตัดบรรทัดกลางประโยค (Soft Wrap) จากโครงสร้าง PDF
                        block_text = re.sub(r'([\u0E00-\u0E7F])\r?\n([\u0E00-\u0E7F])', r'\1\2', block_text)
                        
                        # 2. แปลงการขึ้นบรรทัดใหม่ที่เหลือในบล็อกให้เป็นช่องว่างเพื่อให้โครงสร้างไหลต่อเนื่อง
                        block_text = re.sub(r'\r?\n', ' ', block_text)
                        paragraphs.append(block_text)
        
        full_text = "\n\n".join(paragraphs)
        
        # 3. แก้ไขเฉพาะช่องว่างทางเทคนิคของฟอนต์ PDF (เช่น สระและวรรณยุกต์ถูกแยกช่องว่างออก)
        full_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำา\u0E4D])', r'\1\2', full_text)
        
        # 4. ทำความสะอาดมาตรฐานด้วย Unicode Normalization (ไม่มีการใช้พจนานุกรมแก้คำผิด)
        normalized_text = thai_normalize(full_text)
        
        # 5. จัดระเบียบช่องว่างส่วนเกิน
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
