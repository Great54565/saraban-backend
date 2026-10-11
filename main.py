from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF อ่านตัวอักษรไทยแม่นยำ ไม่เพี้ยน
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

def process_smart_structural_lines(raw_text: str) -> str:
    lines = raw_text.splitlines()
    processed_lines = []
    
    # 📌 กฎโครงสร้างหนังสือราชการ: หัวข้อสำคัญและรายการเหล่านี้ "ต้องขึ้นบรรทัดใหม่เสมอ (Hard Break)"
    hard_break_pattern = re.compile(
        r'^(บันทึกข้อความ|ส่วนราชการ\s*[:：]|ที่\s*[:：]|วันที่\s*[:：]|เรื่อง\s*[:：]|เรียน\s*[:：]|\d+[\.\)]|[๑-๙]+[\.\)]|[ก-ฮ][\.\)]|[-•*])'
    )

    current_para = ""

    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            if current_para:
                processed_lines.append(current_para)
                current_para = ""
            continue
        
        # ตรวจสอบว่าเป็นหัวข้อหรือรายการสำคัญตามระเบียบสารบรรณหรือไม่
        if hard_break_pattern.match(clean_line):
            if current_para:
                processed_lines.append(current_para)
                current_para = ""
            processed_lines.append(clean_line)
        else:
            # เนื้อความภายในย่อหน้าเดียวกัน (Soft Break): นำมาเชื่อมต่อกันเป็นประโยคยาวแบบ Word
            if not current_para:
                current_para = clean_line
            else:
                last_char = current_para[-1]
                first_char = clean_line[0]
                is_thai_left = bool(re.match(r'[\u0E00-\u0E7F]', last_char))
                is_thai_right = bool(re.match(r'[\u0E00-\u0E7F]', first_char))
                
                # ถ้าเป็นตัวอักษรไทยทั้งคู่ แปลว่าถูก PDF ตัดบรรทัดกลางคำ -> เชื่อมติดกันอย่างไร้รอยต่อ
                if is_thai_left and is_thai_right:
                    current_para += clean_line
                else:
                    current_para += " " + clean_line

    if current_para:
        processed_lines.append(current_para)

    return "\n".join(processed_lines)

def extract_and_clean_pdf(file_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_texts = []
        
        for page in doc:
            text = page.get_text("text")
            if text:
                page_texts.append(text)
        
        full_text = "\n".join(page_texts)
        
        # 1. จัดระเบียบย่อหน้าและบรรทัดด้วยระบบโครงสร้างสารบรรณ (Smart Structural Line Breaking)
        structured_text = process_smart_structural_lines(full_text)
        
        # 2. 👑 ล็อกกฎสระอำเด็ดขาด 100%: พยัญชนะ [ก-ฮ] + ช่องว่าง (\s+) + สระอา (า) -> สระอำ (ำ)
        structured_text = re.sub(r'([ก-ฮ])\s+([า])', r'\1ำ', structured_text)
        
        # 3. ทำความสะอาดมาตรฐานด้วย Unicode Normalization ของ PyThaiNLP
        normalized_text = thai_normalize(structured_text)
        
        # 4. จัดระเบียบช่องว่างย่อหน้าให้สะอาดเรียบร้อย
        lines = normalized_text.splitlines()
        final_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
        
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
