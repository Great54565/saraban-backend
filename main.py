from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF สำหรับสกัดโครงสร้างพิกัด PDF ระดับสากล
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
            # วิธีมาตรฐานสากล: ดึงโครงสร้าง Block และ Line เพื่อวิเคราะห์ Layout
            blocks = page.get_text("dict").get("blocks", [])
            for b in blocks:
                if b.get("type") == 0:  # Text block (บล็อกข้อความปกติ)
                    para_lines = []
                    for l in b.get("lines", []):
                        line_text = "".join([span.get("text", "") for span in l.get("spans", "")]).strip()
                        if line_text:
                            para_lines.append(line_text)
                    
                    if para_lines:
                        # อัลกอริทึมรวมบรรทัดสากล (Text Reflow): เชื่อมข้อความในบล็อกเดียวกันให้อยู่ในบรรทัดยาวต่อเนื่อง
                        joined_line = ""
                        for i, l in enumerate(para_lines):
                            if i == 0:
                                joined_line += l
                            else:
                                # หากรอยต่อเป็นภาษาอังกฤษหรือตัวเลขให้เว้นวรรค หากเป็นภาษาไทยให้เชื่อมติดกันอย่างไร้รอยต่อ
                                if re.search(r'[a-zA-Z0-9]$', joined_line) and re.search(r'^[a-zA-Z0-9]', l):
                                    joined_line += " " + l
                                else:
                                    joined_line += l
                        paragraphs.append(joined_line)
        
        # ประกอบบล็อกทั้งหมดเข้าด้วยกัน
        full_text = "\n\n".join(paragraphs)
        
        # 👑 กฎสระอำเด็ดขาด 100%: เห็นพยัญชนะ ตามด้วยช่องว่าง และสระอา -> ตีเป็นสระอำทันทีโดยไม่ต้องคิดเยอะ
        full_text = re.sub(r'([ก-ฮ])\s+([า])', r'\1ำ', full_text)
        
        # ทำความสะอาดมาตรฐานด้วย Unicode Normalization ของ PyThaiNLP
        normalized_text = thai_normalize(full_text)
        
        # จัดระเบียบช่องว่างและโครงสร้างย่อหน้าให้สะอาดเรียบร้อย
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
