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
        paragraphs = []
        # เปิดไฟล์ PDF ด้วย pdfplumber เพื่อเข้าถึงพิกัดระดับคำ (Word-level Bounding Boxes)
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # ดึงข้อมูลทุกคำพร้อมพิกัด (x0, top, x1, bottom, text)
                words = page.extract_words(keep_blank_chars=False, x_tolerance=3, y_tolerance=3)
                if not words:
                    # กรณีหน้าว่างหรือเป็นภาพ ให้ดึงข้อความดิบสำรอง
                    fallback_text = page.extract_text() or ""
                    if fallback_text.strip():
                        paragraphs.append(fallback_text.strip())
                    continue
                
                # จัดกลุ่มคำที่มีพิกัดแนวตั้ง (top) ใกล้เคียงกันให้อยู่ในบรรทัดเดียวกัน
                lines = []
                current_line = []
                current_top = None
                
                for w in words:
                    if current_top is None:
                        current_top = w['top']
                        current_line.append(w)
                    elif abs(w['top'] - current_top) < 5:  # ระยะห่างแนวตั้งภายในบรรทัดเดียวกัน (< 5 พิกเซล)
                        current_line.append(w)
                    else:
                        # เรียงคำในบรรทัดจากซ้ายไปขวาตามแกน x0
                        current_line.sort(key=lambda x: x['x0'])
                        lines.append(current_line)
                        current_line = [w]
                        current_top = w['top']
                
                if current_line:
                    current_line.sort(key=lambda x: x['x0'])
                    lines.append(current_line)
                
                # แปลงแต่ละบรรทัดออกมาเป็นข้อความพร้อมเก็บพิกัดขอบบน/ขอบล่าง
                line_objects = []
                for line in lines:
                    line_str = "".join([w['text'] for w in line]).strip()
                    if line_str:
                        line_objects.append({
                            "text": line_str,
                            "top": line[0]['top'],
                            "bottom": line[0]['bottom']
                        })
                
                if not line_objects:
                    continue
                
                # วิเคราะห์ระยะห่างแนวตั้ง (Vertical Gap) เพื่อรวมบรรทัดเป็นย่อหน้าแบบ Word
                curr_para = [line_objects[0]["text"]]
                
                for i in range(1, len(line_objects)):
                    prev = line_objects[i-1]
                    curr = line_objects[i]
                    
                    v_gap = curr["top"] - prev["bottom"]
                    line_height = prev["bottom"] - prev["top"]
                    if line_height <= 0:
                        line_height = 14.0
                    
                    # ตรวจสอบว่าเป็นหัวข้อหรือรายการข้อใหม่หรือไม่ (ห้ามนำมารวมกับบรรทัดก่อนหน้าเด็ดขาด)
                    is_header_or_bullet = bool(re.match(r'^(\d+[\.\)]|[ก-ฮ][\.\)]|เรื่อง\s*[:：]|เรียน\s*[:：]|ส่วนราชการ\s*[:：]|บันทึกข้อความ)', curr["text"]))
                    
                    # เงื่อนไข: ถ้าระยะห่างแคบ (เป็นห่อคำในย่อหน้าเดียวกัน) และไม่ใช่หัวข้อใหม่ -> สมานคำเข้าด้วยกัน
                    if v_gap < (line_height * 1.8) and not is_header_or_bullet:
                        prev_t = curr_para[-1]
                        curr_t = curr["text"]
                        
                        # เช็คว่าเป็นภาษาไทยทั้งคู่หรือไม่ ถ้าใช่ให้เชื่อมติดกันอย่างไร้รอยต่อ
                        is_thai_left = bool(re.search(r'[\u0E00-\u0E7F]$', prev_t))
                        is_thai_right = bool(re.search(r'^[\u0E00-\u0E7F]', curr_t))
                        
                        if is_thai_left and is_thai_right:
                            curr_para[-1] = prev_t + curr_t
                        else:
                            curr_para[-1] = prev_t + " " + curr_t
                    else:
                        # หากระยะห่างกว้างหรือขึ้นหัวข้อใหม่ ให้ตัดเป็นย่อหน้าใหม่
                        paragraphs.append("".join(curr_para))
                        curr_para = [curr["text"]]
                
                if curr_para:
                    paragraphs.append("".join(curr_para))
        
        full_text = "\n\n".join(paragraphs)
        
        # 👑 ล็อกกฎสระอำเด็ดขาด 100% ตามที่ตกลงกันไว้ (พยัญชนะ + ช่องว่าง + สระอา -> สระอำ)
        full_text = re.sub(r'([ก-ฮ])\s+([า])', r'\1ำ', full_text)
        
        # ทำความสะอาดมาตรฐานด้วย Unicode Normalization ของ PyThaiNLP
        normalized_text = thai_normalize(full_text)
        
        # จัดระเบียบช่องว่างและย่อหน้าให้สะอาดเรียบร้อย
        final_paras = [re.sub(r' {2,}', ' ', p).strip() for p in normalized_text.split("\n\n") if p.strip()]
        
        return "\n\n".join(final_paras)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถอ่านไฟล์ PDF ได้: {str(e)}")

@app.get("/")
def root():
    return {"status": "ok", "message": "e-GovDoc Python Backend (pdfplumber) is running smoothly!"}

@app.post("/api/extract-pdf")
async def extract_pdf_endpoint(file: UploadFile = File(...)):
    file_bytes = await file.read()
    extracted_text = extract_and_clean_pdf(file_bytes)
    return {"success": True, "text": extracted_text}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
