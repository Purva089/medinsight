import asyncio
from app.services.pdf_extractor import PDFExtractor

async def main():
    e = PDFExtractor()
    text = b"WBC Count 5.5 x10^3/uL Normal (4.0-11.0)\nRBC Count 4.2 x10^6/uL Normal (3.8-5.3)\n" * 10
    res = await e.extract(text, "rep1", "pat1")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())