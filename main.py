from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF สำหรับวิเคราะห์พิกัดเรขาคณิต PDF
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
            # ดึงโครงสร้างแบบ dict เพื่อเข้าถึง blocks, lines และพิกัด (bbox) อย่างละเอียด
            blocks = page.get_text("dict").get("blocks", [])
            for b in blocks:
                if b.get("type") == 0:  # Text block
                    block_lines = []
                    for l in b.get("lines", []):
                        line_text = "".join([span.get("text", "") for span in l.get("spans", "")]).strip()
                        if line_text:
                            block_lines.append({
                                "text": line_text,
                                "y0": l.get("bbox")[1],
                                "y1": l.get("bbox")[3]
                            })
                    
                    if block_lines:
                        # อัลกอริทึมรวมบรรทัดอัจฉริยะ (Smart Line Reflow)
                        current_para_lines = [block_lines[0]["text"]]
                        
                        for i in range(1, len(block_lines)):
                            prev = block_lines[i-1]
                            curr = block_lines[i]
                            
                            # คำนวณระยะห่างแนวตั้ง (Vertical Gap) และความสูงบรรทัด (Line Height)
                            gap = curr["y0"] - prev["y1"]
                            line_height = prev["y1"] - prev["y0"]
                            if line_height <= 0:
                                line_height = 14.0
                            
                            # ตรวจสอบว่าเป็นหัวข้อหรือรายการขึ้นต้นใหม่หรือไม่
                            is_header_or_bullet = bool(re.match(r'^(บันทึกข้อความ|ส่วนราชการ|ที่\s*[:：]|เรื่อง\s*[:：]|เรียน\s*[:：]|\d+[\.\)]|[ก-ฮ][\.\)]|[-•])', curr["text"]))
                            
                            # เงื่อนไขรวมบรรทัด: ถ้าระยะห่างแคบ (ห่อคำในย่อหน้าเดียวกัน) และไม่ใช่หัวข้อใหม่
                            if gap < (line_height * 1.8) and not is_header_or_bullet:
                                prev_t = current_para_lines[-1]
                                curr_t = curr["text"]
                                # ถ้าฝั่งซ้ายเป็นอังกฤษ/ตัวเลขให้เว้นวรรค ถ้าเป็นไทยให้เชื่อมติดกัน
                                if re.search(r'[a-zA-Z0-9]$', prev_t) and re.search(r'^[a-zA-Z0-9]', curr_t):
                                    current_para_lines[-1] = prev_t + " " + curr_t
                                else:
                                    current_para_lines[-1] = prev_t + curr_t
                            else:
                                # หากระยะห่างกว้างหรือขึ้นหัวข้อใหม่ ให้ตัดเป็นบรรทัด/ย่อหน้าใหม่
                                paragraphs.append("".join(current_para_lines))
                                current_para_lines = [curr["text"]]
                        
                        if current_para_lines:
                            paragraphs.append("".join(current_para_lines))
        
        full_text = "\n\n".join(paragraphs)
        
        # 👑 ล็อกกฎสระอำตายตัว 100% ตามที่ตกลง (พยัญชนะ + ช่องว่าง + สระอา -> สระอำ)
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
