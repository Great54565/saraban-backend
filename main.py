from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF ตัวจริงที่อ่านตัวอักษรไทยได้แม่นยำ ไม่เพี้ยน
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
            # ดึงข้อมูลแบบ blocks ซึ่ง Word มักจะจัด 1 ย่อหน้า เป็น 1 Block เสมอ
            blocks = page.get_text("blocks")
            # เรียงลำดับพิกัดจากบนลงล่าง ซ้ายไปขวา
            blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
            
            for b in blocks:
                if b[6] == 0:  # Text block
                    block_text = b[4].strip()
                    if block_text:
                        # แทนที่การขึ้นบรรทัดใหม่ภายใน Block เดียวกัน ให้เป็นช่องว่าง เพื่อรวมย่อหน้าให้ยาวต่อเนื่องเหมือน Word
                        cleaned_block = re.sub(r'\r?\n', ' ', block_text)
                        # จัดระเบียบช่องว่างซ้ำซ้อน
                        cleaned_block = re.sub(r'[ \t]+', ' ', cleaned_block).strip()
                        if cleaned_block:
                            paragraphs.append(cleaned_block)
        
        # เชื่อมแต่ละย่อหน้าด้วยขึ้นบรรทัดใหม่
        full_text = "\n\n".join(paragraphs)
        
        # ทำความสะอาดมาตรฐานด้วย PyThaiNLP (รักษาคำว่า ตุลาคม, จำกัด ไว้ครบถ้วนสมบูรณ์)
        normalized_text = thai_normalize(full_text)
        
        return normalized_text
        
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
