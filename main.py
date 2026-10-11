from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF สำหรับสกัดข้อความ PDF อย่างแม่นยำ
from pythainlp.util import normalize as thai_normalize
import uvicorn

app = FastAPI(title="e-GovDoc Python Backend Engine")

# อนุญาตให้หน้าเว็บเรียกใช้งาน API ได้ (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_and_clean_pdf(file_bytes: bytes) -> str:
    """สกัดข้อความจาก PDF ด้วย PyMuPDF และทำความสะอาดด้วย PyThaiNLP"""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        
        for page in doc:
            # ดึงข้อความเป็น Blocks เพื่อจัดเรียงลำดับบรรทัดและย่อหน้าอย่างถูกต้อง
            blocks = page.get_text("blocks")
            # เรียงลำดับตามพิกัดแนวตั้ง (y0) และแนวนอน (x0)
            blocks.sort(key=lambda b: (round(b[1] / 5) * 5, b[0]))
            
            for b in blocks:
                block_text = b[4].strip()
                if block_text:
                    full_text += block_text + "\n"
        
        # ใช้ PyThaiNLP ทำ Text Normalization จัดการสระและวรรณยุกต์อัตโนมัติ
        normalized_text = thai_normalize(full_text)
        return normalized_text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถอ่านไฟล์ PDF ได้: {str(e)}")

@app.post("/api/extract-pdf")
async def extract_pdf_endpoint(file: UploadFile = File(...)):
    file_bytes = await file.read()
    extracted_text = extract_and_clean_pdf(file_bytes)
    return {"success": True, "text": extracted_text}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)