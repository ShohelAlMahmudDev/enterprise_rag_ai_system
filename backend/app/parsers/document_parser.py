# from pathlib import Path

# from docx import Document as DocxDocument
# from openpyxl import load_workbook
# from pptx import Presentation
# from pypdf import PdfReader


# def parse_document(file_path: str) -> str:
#     path = Path(file_path)
#     ext = path.suffix.lower()

#     if ext == '.txt':
#         return path.read_text(encoding='utf-8', errors='ignore')
#     if ext == '.pdf':
#         return _parse_pdf(path)
#     if ext == '.docx':
#         return _parse_docx(path)
#     if ext == '.xlsx':
#         return _parse_xlsx(path)
#     if ext == '.pptx':
#         return _parse_pptx(path)
#     raise ValueError(f'Unsupported parser for extension: {ext}')


# def _parse_pdf(path: Path) -> str:
#     reader = PdfReader(str(path))
#     chunks: list[str] = []
#     for page in reader.pages:
#         chunks.append(page.extract_text() or '')
#     return '\n'.join(chunks)


# def _parse_docx(path: Path) -> str:
#     doc = DocxDocument(str(path))
#     return '\n'.join(p.text for p in doc.paragraphs)


# def _parse_xlsx(path: Path) -> str:
#     wb = load_workbook(str(path), data_only=True)
#     rows: list[str] = []
#     for ws in wb.worksheets:
#         rows.append(f'Sheet: {ws.title}')
#         for row in ws.iter_rows(values_only=True):
#             values = [str(v).strip() for v in row if v is not None and str(v).strip()]
#             if values:
#                 rows.append(' | '.join(values))
#     return '\n'.join(rows)


# def _parse_pptx(path: Path) -> str:
#     prs = Presentation(str(path))
#     slides: list[str] = []
#     for idx, slide in enumerate(prs.slides, start=1):
#         slides.append(f'Slide {idx}')
#         for shape in slide.shapes:
#             if hasattr(shape, 'text') and shape.text:
#                 slides.append(shape.text)
#     return '\n'.join(slides)


# from dataclasses import dataclass, field
# from pathlib import Path

# from docx import Document as DocxDocument
# from openpyxl import load_workbook
# from pptx import Presentation
# from pypdf import PdfReader


# @dataclass
# class ParsedSection:
#     text: str
#     metadata: dict = field(default_factory=dict)


# @dataclass
# class ParsedDocument:
#     text: str
#     sections: list[ParsedSection]
#     file_type: str


# def parse_document(file_path: str) -> ParsedDocument:
#     path = Path(file_path)
#     ext = path.suffix.lower()

#     if ext == ".txt":
#         return _parse_txt(path)
#     if ext == ".pdf":
#         return _parse_pdf(path)
#     if ext == ".docx":
#         return _parse_docx(path)
#     if ext == ".xlsx":
#         return _parse_xlsx(path)
#     if ext == ".pptx":
#         return _parse_pptx(path)

#     raise ValueError(f"Unsupported parser for extension: {ext}")


# def _normalize_text(text: str) -> str:
#     lines = [line.strip() for line in text.splitlines()]
#     filtered = [line for line in lines if line]
#     return "\n".join(filtered).strip()


# def _parse_txt(path: Path) -> ParsedDocument:
#     text = path.read_text(encoding="utf-8", errors="ignore")
#     text = _normalize_text(text)

#     return ParsedDocument(
#         text=text,
#         sections=[ParsedSection(text=text, metadata={"type": "text"})] if text else [],
#         file_type=".txt",
#     )


# def _parse_pdf(path: Path) -> ParsedDocument:
#     reader = PdfReader(str(path))
#     sections: list[ParsedSection] = []

#     for page_number, page in enumerate(reader.pages, start=1):
#         extracted = page.extract_text() or ""
#         cleaned = _normalize_text(extracted)

#         if cleaned:
#             page_text = f"Page {page_number}\n{cleaned}"
#             sections.append(
#                 ParsedSection(
#                     text=page_text,
#                     metadata={
#                         "type": "pdf_page",
#                         "page": page_number,
#                     },
#                 )
#             )

#     full_text = "\n\n".join(section.text for section in sections)

#     return ParsedDocument(
#         text=full_text,
#         sections=sections,
#         file_type=".pdf",
#     )


# def _parse_docx(path: Path) -> ParsedDocument:
#     doc = DocxDocument(str(path))
#     sections: list[ParsedSection] = []

#     current_heading = "Document"
#     buffer: list[str] = []

#     def flush_buffer() -> None:
#         nonlocal buffer
#         cleaned = _normalize_text("\n".join(buffer))
#         if cleaned:
#             section_text = f"Section: {current_heading}\n{cleaned}"
#             sections.append(
#                 ParsedSection(
#                     text=section_text,
#                     metadata={
#                         "type": "docx_section",
#                         "heading": current_heading,
#                     },
#                 )
#             )
#         buffer = []

#     for paragraph in doc.paragraphs:
#         text = (paragraph.text or "").strip()
#         if not text:
#             continue

#         style_name = paragraph.style.name.lower() if paragraph.style and paragraph.style.name else ""

#         if "heading" in style_name:
#             flush_buffer()
#             current_heading = text
#         else:
#             buffer.append(text)

#     flush_buffer()

#     # Extract simple table content too
#     for table_index, table in enumerate(doc.tables, start=1):
#         rows: list[str] = []
#         for row in table.rows:
#             values = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
#             if values:
#                 rows.append(" | ".join(values))

#         cleaned_table = _normalize_text("\n".join(rows))
#         if cleaned_table:
#             sections.append(
#                 ParsedSection(
#                     text=f"Table {table_index}\n{cleaned_table}",
#                     metadata={
#                         "type": "docx_table",
#                         "table_index": table_index,
#                     },
#                 )
#             )

#     full_text = "\n\n".join(section.text for section in sections)

#     return ParsedDocument(
#         text=full_text,
#         sections=sections,
#         file_type=".docx",
#     )


# def _parse_xlsx(path: Path) -> ParsedDocument:
#     wb = load_workbook(str(path), data_only=True)
#     sections: list[ParsedSection] = []

#     for ws in wb.worksheets:
#         rows = list(ws.iter_rows(values_only=True))
#         if not rows:
#             continue

#         # Detect header row as first non-empty row
#         header: list[str] | None = None
#         data_rows: list[tuple] = []

#         for row in rows:
#             normalized = [str(v).strip() if v is not None else "" for v in row]
#             if any(normalized):
#                 if header is None:
#                     header = normalized
#                 else:
#                     data_rows.append(row)

#         if not header:
#             continue

#         # Sheet summary section
#         summary_lines = [f"Sheet: {ws.title}"]
#         summary_lines.append("Columns: " + ", ".join(col for col in header if col))
#         sections.append(
#             ParsedSection(
#                 text=_normalize_text("\n".join(summary_lines)),
#                 metadata={
#                     "type": "xlsx_sheet_summary",
#                     "sheet": ws.title,
#                 },
#             )
#         )

#         # Row-wise structured records
#         for row_index, row in enumerate(data_rows, start=2):
#             values = [str(v).strip() if v is not None else "" for v in row]
#             pairs = []

#             for col_name, value in zip(header, values):
#                 col_name = (col_name or "").strip()
#                 value = value.strip()
#                 if col_name and value:
#                     pairs.append(f"{col_name}: {value}")

#             if pairs:
#                 row_text = f"Sheet: {ws.title}\nRow: {row_index}\n" + "\n".join(pairs)
#                 sections.append(
#                     ParsedSection(
#                         text=_normalize_text(row_text),
#                         metadata={
#                             "type": "xlsx_row",
#                             "sheet": ws.title,
#                             "row": row_index,
#                         },
#                     )
#                 )

#     full_text = "\n\n".join(section.text for section in sections)

#     return ParsedDocument(
#         text=full_text,
#         sections=sections,
#         file_type=".xlsx",
#     )


# def _parse_pptx(path: Path) -> ParsedDocument:
#     prs = Presentation(str(path))
#     sections: list[ParsedSection] = []

#     for slide_index, slide in enumerate(prs.slides, start=1):
#         title = ""
#         body_parts: list[str] = []

#         if slide.shapes.title and slide.shapes.title.text:
#             title = slide.shapes.title.text.strip()

#         for shape in slide.shapes:
#             if hasattr(shape, "text"):
#                 text = (shape.text or "").strip()
#                 if text and text != title:
#                     body_parts.append(text)

#         notes_text = ""
#         try:
#             if slide.has_notes_slide and slide.notes_slide:
#                 note_parts: list[str] = []
#                 for shape in slide.notes_slide.shapes:
#                     if hasattr(shape, "text"):
#                         note_text = (shape.text or "").strip()
#                         if note_text:
#                             note_parts.append(note_text)
#                 notes_text = "\n".join(note_parts).strip()
#         except Exception:
#             notes_text = ""

#         parts = [f"Slide {slide_index}"]
#         if title:
#             parts.append(f"Title: {title}")
#         if body_parts:
#             parts.append("Content:")
#             parts.extend(body_parts)
#         if notes_text:
#             parts.append("Notes:")
#             parts.append(notes_text)

#         slide_text = _normalize_text("\n".join(parts))
#         if slide_text:
#             sections.append(
#                 ParsedSection(
#                     text=slide_text,
#                     metadata={
#                         "type": "pptx_slide",
#                         "slide": slide_index,
#                         "title": title or None,
#                     },
#                 )
#             )

#     full_text = "\n\n".join(section.text for section in sections)

#     return ParsedDocument(
#         text=full_text,
#         sections=sections,
#         file_type=".pptx",
#     )

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docx import Document as DocxDocument
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

from app.config import settings
from app.utils.ocr_utils import extract_ocr_text_from_pdf_page


@dataclass
class ParsedSection:
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    text: str
    sections: list[ParsedSection]
    file_type: str


def parse_document(file_path: str) -> ParsedDocument:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".txt":
        return _parse_txt(path)
    if ext == ".pdf":
        return _parse_pdf(path)
    if ext == ".docx":
        return _parse_docx(path)
    if ext == ".xlsx":
        return _parse_xlsx(path)
    if ext == ".pptx":
        return _parse_pptx(path)

    raise ValueError(f"Unsupported parser for extension: {ext}")


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    filtered = [line for line in lines if line]
    return "\n".join(filtered).strip()


def _parse_txt(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = _normalize_text(text)

    return ParsedDocument(
        text=text,
        sections=[ParsedSection(text=text, metadata={"type": "text"})] if text else [],
        file_type=".txt",
    )


def _parse_pdf(path: Path) -> ParsedDocument:
    reader = PdfReader(str(path))
    sections: list[ParsedSection] = []

    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        cleaned = _normalize_text(extracted)

        used_ocr = False

        if settings.OCR_ENABLED and len(cleaned) < settings.PDF_OCR_MIN_TEXT_LENGTH:
            try:
                ocr_text = extract_ocr_text_from_pdf_page(path, page_number)
                ocr_cleaned = _normalize_text(ocr_text)

                if len(ocr_cleaned) > len(cleaned):
                    cleaned = ocr_cleaned
                    used_ocr = True
            except Exception:
                used_ocr = False

        if cleaned:
            prefix = f"Page {page_number}"
            if used_ocr:
                prefix += " (OCR)"

            page_text = f"{prefix}\n{cleaned}"
            sections.append(
                ParsedSection(
                    text=page_text,
                    metadata={
                        "type": "pdf_page",
                        "page": page_number,
                        "ocr_used": used_ocr,
                    },
                )
            )

    full_text = "\n\n".join(section.text for section in sections)

    return ParsedDocument(
        text=full_text,
        sections=sections,
        file_type=".pdf",
    )


def _parse_docx(path: Path) -> ParsedDocument:
    doc = DocxDocument(str(path))
    sections: list[ParsedSection] = []

    current_heading = "Document"
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal buffer
        cleaned = _normalize_text("\n".join(buffer))
        if cleaned:
            section_text = f"Section: {current_heading}\n{cleaned}"
            sections.append(
                ParsedSection(
                    text=section_text,
                    metadata={
                        "type": "docx_section",
                        "heading": current_heading,
                    },
                )
            )
        buffer = []

    for paragraph in doc.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue

        style_name = paragraph.style.name.lower() if paragraph.style and paragraph.style.name else ""

        if "heading" in style_name:
            flush_buffer()
            current_heading = text
        else:
            buffer.append(text)

    flush_buffer()

    for table_index, table in enumerate(doc.tables, start=1):
        rows: list[str] = []
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if values:
                rows.append(" | ".join(values))

        cleaned_table = _normalize_text("\n".join(rows))
        if cleaned_table:
            sections.append(
                ParsedSection(
                    text=f"Table {table_index}\n{cleaned_table}",
                    metadata={
                        "type": "docx_table",
                        "table_index": table_index,
                    },
                )
            )

    full_text = "\n\n".join(section.text for section in sections)

    return ParsedDocument(
        text=full_text,
        sections=sections,
        file_type=".docx",
    )


def _parse_xlsx(path: Path) -> ParsedDocument:
    wb = load_workbook(str(path), data_only=True)
    sections: list[ParsedSection] = []

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        header: list[str] | None = None
        data_rows: list[tuple] = []

        for row in rows:
            normalized = [str(v).strip() if v is not None else "" for v in row]
            if any(normalized):
                if header is None:
                    header = normalized
                else:
                    data_rows.append(row)

        if not header:
            continue

        summary_lines = [f"Sheet: {ws.title}"]
        summary_lines.append("Columns: " + ", ".join(col for col in header if col))
        sections.append(
            ParsedSection(
                text=_normalize_text("\n".join(summary_lines)),
                metadata={
                    "type": "xlsx_sheet_summary",
                    "sheet": ws.title,
                },
            )
        )

        for row_index, row in enumerate(data_rows, start=2):
            values = [str(v).strip() if v is not None else "" for v in row]
            pairs = []

            for col_name, value in zip(header, values):
                col_name = (col_name or "").strip()
                value = value.strip()
                if col_name and value:
                    pairs.append(f"{col_name}: {value}")

            if pairs:
                row_text = f"Sheet: {ws.title}\nRow: {row_index}\n" + "\n".join(pairs)
                sections.append(
                    ParsedSection(
                        text=_normalize_text(row_text),
                        metadata={
                            "type": "xlsx_row",
                            "sheet": ws.title,
                            "row": row_index,
                        },
                    )
                )

    full_text = "\n\n".join(section.text for section in sections)

    return ParsedDocument(
        text=full_text,
        sections=sections,
        file_type=".xlsx",
    )


def _parse_pptx(path: Path) -> ParsedDocument:
    prs = Presentation(str(path))
    sections: list[ParsedSection] = []

    for slide_index, slide in enumerate(prs.slides, start=1):
        title = ""
        body_parts: list[str] = []

        if slide.shapes.title and slide.shapes.title.text:
            title = slide.shapes.title.text.strip()

        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = (shape.text or "").strip()
                if text and text != title:
                    body_parts.append(text)

        notes_text = ""
        try:
            if slide.has_notes_slide and slide.notes_slide:
                note_parts: list[str] = []
                for shape in slide.notes_slide.shapes:
                    if hasattr(shape, "text"):
                        note_text = (shape.text or "").strip()
                        if note_text:
                            note_parts.append(note_text)
                notes_text = "\n".join(note_parts).strip()
        except Exception:
            notes_text = ""

        parts = [f"Slide {slide_index}"]
        if title:
            parts.append(f"Title: {title}")
        if body_parts:
            parts.append("Content:")
            parts.extend(body_parts)
        if notes_text:
            parts.append("Notes:")
            parts.append(notes_text)

        slide_text = _normalize_text("\n".join(parts))
        if slide_text:
            sections.append(
                ParsedSection(
                    text=slide_text,
                    metadata={
                        "type": "pptx_slide",
                        "slide": slide_index,
                        "title": title or None,
                    },
                )
            )

    full_text = "\n\n".join(section.text for section in sections)

    return ParsedDocument(
        text=full_text,
        sections=sections,
        file_type=".pptx",
    )