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
        paragraphs = []
        
        for page in doc:
            # ดึงโครงสร้างข้อความแบบละเอียด (Dict blocks) เพื่อรวมบรรทัดในย่อหน้าเดียวกัน
            text_page = page.get_text("dict")
            for block in text_page.get("blocks", []):
                if block.get("type") == 0:  # Text block (ย่อหน้า/บล็อกข้อความ)
                    paragraph_lines = []
                    for line in block.get("lines", []):
                        line_str = "".join([span.get("text", "") for span in line.get("spans", "")]).strip()
                        if line_str:
                            paragraph_lines.append(line_str)
                    
                    if paragraph_lines:
                        # รวมบรรทัดที่ห่ออยู่ในย่อหน้าเดียวกันให้เป็นข้อความยาวต่อเนื่องเหมือน Word
                        joined_line = ""
                        for i, l in enumerate(paragraph_lines):
                            if i == 0:
                                joined_line += l
                            else:
                                # หากเป็นภาษาอังกฤษ/ตัวเลข ให้เว้นวรรค หากเป็นภาษาไทยเชื่อมต่อกันตามธรรมชาติ
                                if re.search(r'[a-zA-Z0-9]$', joined_line) and re.search(r'^[a-zA-Z0-9]', l):
                                    joined_line += " " + l
                                else:
                                    joined_line += l
                        paragraphs.append(joined_line)
        
        # เชื่อมแต่ละย่อหน้าด้วยขึ้นบรรทัดใหม่
        full_text = "\n\n".join(paragraphs)
        
        # ระบบจัดการสระอำอัตโนมัติ (พร้อมเกราะป้องกันสระเอา เ-า)
        cleaned_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำา])', r'\1ำ', full_text)
        
        # ทำความสะอาดมาตรฐานด้วย PyThaiNLP และ Unicode NFC
        normalized_text = thai_normalize(cleaned_text)
        
        # จัดระเบียบช่องว่างส่วนเกิน
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
