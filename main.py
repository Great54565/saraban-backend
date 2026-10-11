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
            # ดึงโครงสร้างบล็อกข้อความทั้งหมดในหน้า
            blocks = page.get_text("blocks")
            # เรียงลำดับพิกัดจากบนลงล่าง ซ้ายไปขวา
            blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
            
            for b in blocks:
                if b[6] == 0:  # Text block
                    raw_text = b[4].strip()
                    if not raw_text:
                        continue
                    
                    # แยกบรรทัดภายในบล็อก
                    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                    if not lines:
                        continue
                    
                    # อัลกอริทึมสมานคำไทยที่ถูก PDF ตัดบรรทัดกลางอากาศอย่างไร้รอยต่อ
                    reflowed_lines = []
                    current_line = lines[0]
                    
                    for next_line in lines[1:]:
                        # ตรวจสอบว่าเป็นหัวข้อหรือขึ้นต้นข้อใหม่หรือไม่ (เช่น 1., เรื่อง:, เรียน:, ส่วนราชการ)
                        is_header_or_bullet = bool(re.match(r'^(\d+[\.\)]|[ก-ฮ][\.\)]|เรื่อง\s*[:：]|เรียน\s*[:：]|ส่วนราชการ\s*[:：]|บันทึกข้อความ)', next_line))
                        
                        if is_header_or_bullet:
                            reflowed_lines.append(current_line)
                            current_line = next_line
                        else:
                            last_char = current_line[-1] if current_line else ""
                            first_char = next_line[0] if next_line else ""
                            
                            # เช็คว่าเป็นตัวอักษรภาษาไทยทั้งคู่หรือไม่ (Unicode \u0E00-\u0E7F)
                            is_thai_left = bool(re.match(r'[\u0E00-\u0E7F]', last_char))
                            is_thai_right = bool(re.match(r'[\u0E00-\u0E7F]', first_char))
                            
                            if is_thai_left and is_thai_right:
                                # ถ้าเป็นไทยทั้งคู่ แปลว่าโดน PDF ตัดคำกลางอากาศ -> เชื่อมติดกันทันทีโดยไม่ใส่ช่องว่าง
                                current_line += next_line
                            else:
                                # ถ้ามีอังกฤษหรือตัวเลขปะปน ให้เว้นวรรคปกติ
                                current_line += " " + next_line
                                
                    reflowed_lines.append(current_line)
                    paragraphs.append("\n".join(reflowed_lines))
                    
        full_text = "\n\n".join(paragraphs)
        
        # 👑 ล็อกกฎสระอำเด็ดขาด 100% ตามที่ตกลง (พยัญชนะ + ช่องว่าง + สระอา -> สระอำ)
        full_text = re.sub(r'([ก-ฮ])\s+([า])', r'\1ำ', full_text)
        
        # ทำความสะอาดมาตรฐานด้วย PyThaiNLP
        normalized_text = thai_normalize(full_text)
        
        # จัดระเบียบช่องว่างย่อหน้าให้สะอาดเรียบร้อย
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
