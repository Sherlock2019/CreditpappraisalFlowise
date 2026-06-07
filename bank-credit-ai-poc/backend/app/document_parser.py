from pathlib import Path
from typing import TypedDict
from xml.etree import ElementTree
from zipfile import ZipFile

import fitz
import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover - dependency is included, but keep parser resilient.
    pdfplumber = None


class ParsedSection(TypedDict):
    text: str
    page_number: int | None


def parse_txt(path: str) -> list[ParsedSection]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return [{"text": text, "page_number": None}]


def parse_pdf_text(path: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                sections.append({"text": text, "page_number": index})
    return sections


def parse_pdf_tables(path: str) -> list[ParsedSection]:
    if pdfplumber is None:
        return []

    sections: list[ParsedSection] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table in tables:
                rows = [" | ".join(str(cell or "") for cell in row) for row in table]
                text = "\n".join(rows).strip()
                if text:
                    sections.append({"text": text, "page_number": page_number})
    return sections


def parse_excel(path: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    workbook = pd.read_excel(path, sheet_name=None)
    for sheet_name, frame in workbook.items():
        text = frame.fillna("").to_csv(index=False)
        sections.append({"text": f"Sheet: {sheet_name}\n{text}", "page_number": None})
    return sections


def parse_csv(path: str) -> list[ParsedSection]:
    frame = pd.read_csv(path)
    return [{"text": frame.fillna("").to_csv(index=False), "page_number": None}]


def parse_docx(path: str) -> list[ParsedSection]:
    paragraphs: list[str] = []
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(path) as archive:
        with archive.open("word/document.xml") as document_xml:
            root = ElementTree.parse(document_xml).getroot()
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
    return [{"text": "\n".join(paragraphs), "page_number": None}] if paragraphs else []


def parse_document(path: str) -> list[ParsedSection]:
    suffix = Path(path).suffix.lower()
    if suffix == ".txt":
        return parse_txt(path)
    if suffix == ".pdf":
        return parse_pdf_text(path) + parse_pdf_tables(path)
    if suffix == ".csv":
        return parse_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return parse_excel(path)
    if suffix == ".docx":
        return parse_docx(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_sections(sections: list[ParsedSection], chunk_size: int = 3000, overlap: int = 200) -> list[ParsedSection]:
    chunks: list[ParsedSection] = []
    for section in sections:
        text = " ".join(section["text"].split())
        if not text:
            continue

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append({"text": text[start:end], "page_number": section["page_number"]})
            if end == len(text):
                break
            start = max(0, end - overlap)
    return chunks
