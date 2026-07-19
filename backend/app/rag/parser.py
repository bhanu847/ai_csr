from dataclasses import dataclass
from io import BytesIO

from docx import Document
from pypdf import PdfReader


@dataclass
class PageText:
    page: int | None
    text: str


def parse_pdf(data: bytes) -> list[PageText]:
    reader = PdfReader(BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(PageText(page=i, text=text))
    return pages


def parse_docx(data: bytes) -> list[PageText]:
    document = Document(BytesIO(data))
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    return [PageText(page=None, text=text)] if text.strip() else []


def parse_document(filename: str, data: bytes) -> list[PageText]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf(data)
    if lower.endswith(".docx"):
        return parse_docx(data)
    raise ValueError(f"Unsupported file type: {filename}")
