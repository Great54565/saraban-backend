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
        all_lines = []
        
        # 1. ดึงข้อความและพิกัดทุกบรรทัดทั่วทั้งเอกสาร
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict").get("blocks", [])
            for b in blocks:
                if b.get("type") == 0:  # Text block
                    for l in b.get("lines", []):
                        bbox = l.get("bbox")  # (x0, y0, x1, y1)
                        line_text = "".join([span.get("text", "") for span in l.get("spans", "")]).strip()
                        if line_text:
                            all_lines.append({
                                "page": page_num,
                                "y0": bbox[1],
                                "y1": bbox[3],
                                "x0": bbox[0],
                                "x1": bbox[2],
                                "text": line_text
                            })
        
        if not all_lines:
            return ""
        
        # 2. เรียงลำดับบรรทัดตามหน้า และพิกัดจากบนลงล่าง
        all_lines.sort(key=lambda item: (item["page"], item["y0"], item["x0"]))
        
        # 3. คำนวณความสูงมาตรฐานของบรรทัดเพื่อใช้เป็นเกณฑ์ตัดสินย่อหน้า
        heights = [l["y1"] - l["y0"] for l in all_lines if (l["y1"] - l["y0"]) > 0]
        avg_height = sum(heights) / len(heights) if heights else 14.0
        threshold_y = avg_height * 1.6  # หากช่องว่างมากกว่า 1.6 เท่า คือขึ้นย่อหน้าใหม่
        
        paragraphs = []
        current_para = []
        last_line = None
        
        for line in all_lines:
            if not current_para:
                current_para.append(line["text"])
                last_line = line
                continue
            
            # เงื่อนไขการตัดย่อหน้าใหม่
            is_new_page = line["page"] != last_line["page"]
            y_gap = line["y0"] - last_line["y1"]
            is_large_gap = y_gap > threshold_y
            
            # ตรวจสอบหัวข้อหรือรายการ (เช่น เรื่อง:, เรียน:, 1., 2., ฯลฯ) ให้ขึ้นบรรทัดใหม่เสมอ
            is_header_or_bullet = bool(re.match(r'^(เรื่อง\s*[:：]|เรียน\s*[:：]|ส่วนราชการ\s*[:：]|ที่\s*[:：]|\d+[\.\)]|[ก-ฮ][\.\)]|[-•])', line["text"]))
            
            if is_new_page or is_large_gap or is_header_or_bullet:
                paragraphs.append("".join(current_para))
                current_para = [line["text"]]
            else:
                # บรรทัดต่อเนื่องในย่อหน้าเดิม: เชื่อมต่อข้อความเข้าด้วยกันแบบยาวต่อเนื่องเหมือน Word
                prev_text = current_para[-1]
                curr_text = line["text"]
                
                # หากเป็นภาษาอังกฤษ/ตัวเลขติดกัน ให้เว้นวรรค หากเป็นภาษาไทยเชื่อมต่อกันโดยตรง
                if re.search(r'[a-zA-Z0-9]$', prev_text) and re.search(r'^[a-zA-Z0-9]', curr_text):
                    current_para.append(" " + curr_text)
                else:
                    current_para.append(curr_text)
            
            last_line = line
        
        if current_para:
            paragraphs.append("".join(current_para))
        
        full_text = "\n\n".join(paragraphs)
        
        # 4. ระบบจัดการสระอำอัตโนมัติ (พร้อมเกราะป้องกันสระเอา เ-า)
        cleaned_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำа])', r'\1ำ', full_text)
        cleaned_text = re.sub(r'(?<!เ)([ก-ฮ])\s+([ำ])', r'\1ำ', full_text)
        
        # 5. ทำความสะอาดมาตรฐาน
        normalized_text = thai_normalize(cleaned_text)
        final_paras = [re.sub(r'\s+', ' ', p).strip() for p in normalized_text.split("\n\n") if p.strip()]
        
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
