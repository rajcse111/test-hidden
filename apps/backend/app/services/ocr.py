import asyncio
import base64
import io

import pytesseract
from PIL import Image


class OcrService:
    async def extract_text(self, image_base64: str) -> str:
        raw = base64.b64decode(image_base64)
        return await asyncio.to_thread(self._run_ocr, raw)

    def _run_ocr(self, raw: bytes) -> str:
        image = Image.open(io.BytesIO(raw))
        return pytesseract.image_to_string(image).strip()
