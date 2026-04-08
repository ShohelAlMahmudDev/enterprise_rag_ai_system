import json
import re
from pathlib import Path
from typing import Any

from app.config import settings


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().split()).lower()


class StructuredIndexService:
    """
    Persistent structured key-value index for technical tables/specs.

    Supports:
    - numbered mappings: 26 = Request geo position information
    - key:value rows
    - xlsx/docx row metadata
    - attribute-oriented extraction
    """

    ATTRIBUTE_LINE_PATTERN = re.compile(r'^\["([^"]+)"\]')
    NUMBER_MAPPING_PATTERN = re.compile(r"^\s*(\d+)\s*=\s*(.+?)\s*$")
    KEY_VALUE_PATTERN = re.compile(r"^\s*([^:\n]{1,100})\s*:\s*(.+?)\s*$")

    def __init__(self, index_path: str | None = None) -> None:
        self.index_path = Path(index_path or settings.STRUCTURED_INDEX_PATH)
        self.records: list[dict[str, Any]] = []
        self._load()

    def add_records_from_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return

        new_records: list[dict[str, Any]] = []
        for chunk in chunks:
            new_records.extend(self._extract_records_from_chunk(chunk))

        if new_records:
            self.records.extend(new_records)
            self._save()

    def remove_by_version(self, version_id: str) -> None:
        if not version_id:
            return

        self.records = [record for record in self.records if str(record.get("version_id")) != str(version_id)]
        self._save()

    def search(
        self,
        question: str,
        *,
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query = _normalize(question)
        if not query:
            return []

        q_numbers = re.findall(r"\b\d+\b", query)
        q_terms = set(re.findall(r"[\w.-]{2,}", query))

        scored: list[tuple[float, dict[str, Any]]] = []
        for record in self.records:
            if filters and not self._matches_filters(record, filters):
                continue
            if not record.get("active", True):
                continue

            score = self._score_record(record, q_terms, q_numbers)
            if score <= 0.0:
                continue

            enriched = dict(record)
            enriched["structured_score"] = round(score, 6)
            enriched["source"] = "structured"
            scored.append((score, enriched))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:k]]

    def _extract_records_from_chunk(self, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        text = str(chunk.get("text") or chunk.get("chunk") or "").strip()
        if not text:
            return []

        metadata = dict(chunk.get("metadata") or {})
        section_type = str(metadata.get("type") or "")
        logical_name = str(metadata.get("logical_name") or metadata.get("source_file") or "")
        page = metadata.get("page")
        row = metadata.get("row")
        sheet = metadata.get("sheet") or metadata.get("sheet_name")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        records: list[dict[str, Any]] = []
        current_attribute: str | None = None
        context_object = self._infer_context_object(lines, metadata, logical_name)

        for line in lines:
            attr_match = self.ATTRIBUTE_LINE_PATTERN.match(line)
            if attr_match:
                current_attribute = attr_match.group(1).strip()
                continue

            mapping_match = self.NUMBER_MAPPING_PATTERN.match(line)
            if mapping_match:
                code = mapping_match.group(1).strip()
                meaning = mapping_match.group(2).strip()
                records.append(
                    self._build_record(
                        chunk=chunk,
                        metadata=metadata,
                        record_type="mapping",
                        object_name=context_object,
                        attribute_name=current_attribute,
                        code=code,
                        value=meaning,
                        row_text=line,
                        page=page,
                        row=row,
                        sheet=sheet,
                    )
                )
                continue

            kv_match = self.KEY_VALUE_PATTERN.match(line)
            if kv_match:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                records.append(
                    self._build_record(
                        chunk=chunk,
                        metadata=metadata,
                        record_type="key_value",
                        object_name=context_object,
                        attribute_name=key,
                        code=None,
                        value=value,
                        row_text=line,
                        page=page,
                        row=row,
                        sheet=sheet,
                    )
                )

        if section_type == "xlsx_row":
            row_columns = self._extract_columns_from_xlsx_row(text)
            if row_columns:
                records.append(
                    self._build_record(
                        chunk=chunk,
                        metadata=metadata,
                        record_type="row_columns",
                        object_name=context_object,
                        attribute_name=None,
                        code=None,
                        value=None,
                        row_text=text,
                        page=page,
                        row=row,
                        sheet=sheet,
                        columns=row_columns,
                    )
                )

        if section_type == "docx_table":
            columns = self._extract_columns_from_pipe_row(text)
            if columns:
                records.append(
                    self._build_record(
                        chunk=chunk,
                        metadata=metadata,
                        record_type="table_row",
                        object_name=context_object,
                        attribute_name=None,
                        code=None,
                        value=None,
                        row_text=text,
                        page=page,
                        row=row,
                        sheet=sheet,
                        columns=columns,
                    )
                )

        return records

    def _build_record(
        self,
        *,
        chunk: dict[str, Any],
        metadata: dict[str, Any],
        record_type: str,
        object_name: str | None,
        attribute_name: str | None,
        code: str | None,
        value: str | None,
        row_text: str,
        page: Any,
        row: Any,
        sheet: Any,
        columns: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "record_type": record_type,
            "object_name": object_name,
            "attribute_name": attribute_name,
            "code": code,
            "value": value,
            "row_text": row_text,
            "columns": columns or {},
            "text": str(chunk.get("text") or chunk.get("chunk") or ""),
            "chunk_id": metadata.get("chunk_id") or chunk.get("chunk_id"),
            "document_id": metadata.get("document_id") or chunk.get("document_id"),
            "version_id": metadata.get("version_id") or chunk.get("version_id"),
            "logical_name": metadata.get("logical_name") or chunk.get("logical_name"),
            "filename": metadata.get("filename") or metadata.get("source_file") or chunk.get("filename"),
            "file_type": metadata.get("file_type") or chunk.get("file_type"),
            "type": metadata.get("type") or chunk.get("type"),
            "page": page,
            "row": row,
            "sheet": sheet,
            "active": metadata.get("active", True),
        }

    def _score_record(self, record: dict[str, Any], q_terms: set[str], q_numbers: list[str]) -> float:
        score = 0.0

        haystack_parts = [
            record.get("object_name") or "",
            record.get("attribute_name") or "",
            record.get("code") or "",
            record.get("value") or "",
            record.get("row_text") or "",
        ]
        columns = record.get("columns") or {}
        haystack_parts.extend([f"{k} {v}" for k, v in columns.items()])

        haystack = _normalize(" ".join(haystack_parts))

        for term in q_terms:
            if term in haystack:
                score += 0.12

        for num in q_numbers:
            if record.get("code") == num:
                score += 0.50
            elif re.search(rf"\b{re.escape(num)}\b", haystack):
                score += 0.20

            if re.search(rf"\b{re.escape(num)}\s*=", record.get("row_text") or ""):
                score += 0.25

        if "action" in q_terms and _normalize(record.get("attribute_name")) == "action":
            score += 0.20
        if "status" in q_terms and _normalize(record.get("attribute_name")) == "status":
            score += 0.20
        if "messagehandle" in q_terms and _normalize(record.get("attribute_name")) == "messagehandle":
            score += 0.25

        return score

    def _infer_context_object(
        self,
        lines: list[str],
        metadata: dict[str, Any],
        logical_name: str,
    ) -> str:
        for line in lines[:5]:
            if line.lower().startswith("page "):
                continue
            if line.startswith('["'):
                continue
            if len(line.split()) <= 6:
                return line.strip()
        return logical_name or "Document"

    def _extract_columns_from_xlsx_row(self, text: str) -> dict[str, str]:
        columns: dict[str, str] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value and key.lower() not in {"sheet", "row"}:
                columns[key] = value
        return columns

    def _extract_columns_from_pipe_row(self, text: str) -> dict[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return {}
        if "|" not in lines[-1]:
            return {}
        parts = [part.strip() for part in lines[-1].split("|") if part.strip()]
        return {f"col_{idx+1}": value for idx, value in enumerate(parts)}

    def _matches_filters(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if str(record.get(key)) != str(expected):
                return False
        return True

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(self.records, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        if not self.index_path.exists():
            self.records = []
            return
        self.records = list(json.loads(self.index_path.read_text(encoding="utf-8")))