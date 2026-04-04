from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from app.schemas.diagram_types import DiagramType


class DiagramNode(BaseModel):
    """
    Represents a node-like element in a diagram.

    Examples:
    - state in a state machine
    - process step in a flowchart
    - component in an architecture diagram
    - device/system in a network diagram
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=200, description="Stable local node identifier.")
    label: str = Field(..., min_length=1, max_length=1000, description="Human-readable node label.")
    type: str = Field(..., min_length=1, max_length=100, description="Node type, e.g. state, process, component.")
    description: Optional[str] = Field(default=None, max_length=5000, description="Optional node description.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional node-specific metadata.")

    @field_validator("id", "label", "type")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty.")
        return value


class DiagramEdge(BaseModel):
    """
    Represents a directed or logical relationship between two nodes.

    Examples:
    - transition between states
    - message between participants
    - connection between components
    - branch between flowchart steps
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(..., min_length=1, max_length=200, description="Source node id.")
    target: str = Field(..., min_length=1, max_length=200, description="Target node id.")
    label: Optional[str] = Field(default=None, max_length=1000, description="Relationship label.")
    condition: Optional[str] = Field(default=None, max_length=2000, description="Optional condition or trigger.")
    direction: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional direction indicator, e.g. uni, bi, request, response.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional edge-specific metadata.")

    @field_validator("source", "target")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Edge endpoint cannot be empty.")
        return value


class DiagramMessage(BaseModel):
    """
    Represents an ordered message in a sequence or interaction diagram.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order: int = Field(..., ge=1, description="1-based message order.")
    sender: str = Field(..., min_length=1, max_length=500, description="Message sender.")
    receiver: str = Field(..., min_length=1, max_length=500, description="Message receiver.")
    label: str = Field(..., min_length=1, max_length=2000, description="Message text/label.")
    condition: Optional[str] = Field(default=None, max_length=2000, description="Optional guard/condition.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional message metadata.")

    @field_validator("sender", "receiver", "label")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty.")
        return value


class DiagramStep(BaseModel):
    """
    Represents a process step for flowcharts, procedures, or pipelines.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order: int = Field(..., ge=1, description="1-based step order.")
    label: str = Field(..., min_length=1, max_length=2000, description="Step label.")
    step_type: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional step type, e.g. process, decision, terminal.",
    )
    description: Optional[str] = Field(default=None, max_length=5000, description="Optional step description.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional step metadata.")

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Step label cannot be empty.")
        return value


class DiagramExtraction(BaseModel):
    """
    Structured extraction result for a diagram-like image/page/slide.

    This model is intentionally flexible:
    - some fields are relevant only for certain diagram types
    - empty collections are allowed
    - raw source text and summary are preserved for retrieval
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    diagram_type: DiagramType = Field(..., description="Normalized diagram category.")
    title: Optional[str] = Field(default=None, max_length=1000, description="Extracted diagram title.")
    summary: Optional[str] = Field(default=None, max_length=10000, description="Short structured summary.")

    # Graph-like content
    nodes: list[DiagramNode] = Field(default_factory=list, description="Extracted nodes.")
    edges: list[DiagramEdge] = Field(default_factory=list, description="Extracted edges.")

    # Sequence-specific
    participants: list[str] = Field(default_factory=list, description="Sequence/interaction participants.")
    messages: list[DiagramMessage] = Field(default_factory=list, description="Ordered sequence messages.")

    # Flow/process-specific
    steps: list[DiagramStep] = Field(default_factory=list, description="Ordered process steps.")
    decisions: list[str] = Field(default_factory=list, description="Extracted decision labels or conditions.")

    # Architecture/network-specific
    components: list[str] = Field(default_factory=list, description="Architecture or network components.")
    interfaces: list[str] = Field(default_factory=list, description="Named interfaces or connectors.")
    protocols: list[str] = Field(default_factory=list, description="Detected protocols or technologies.")

    # Generic retrieval helpers
    keywords: list[str] = Field(default_factory=list, description="Normalized keywords.")
    raw_text: Optional[str] = Field(default=None, max_length=20000, description="OCR/vision-derived raw text.")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Best-effort confidence score from 0.0 to 1.0.",
    )

    # Optional source/debug info
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional extraction metadata.")

    @field_validator("participants", "decisions", "components", "interfaces", "protocols", "keywords")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = value.strip()
            if not normalized:
                continue

            dedupe_key = normalized.casefold()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            cleaned.append(normalized)

        return cleaned

    @model_validator(mode="after")
    def validate_references(self) -> "DiagramExtraction":
        """
        Validate internal edge references when nodes are present.
        """
        if self.nodes and self.edges:
            node_ids = {node.id for node in self.nodes}
            for edge in self.edges:
                if edge.source not in node_ids:
                    raise ValueError(f"Edge source '{edge.source}' does not match any node id.")
                if edge.target not in node_ids:
                    raise ValueError(f"Edge target '{edge.target}' does not match any node id.")
        return self

    @property
    def has_structured_content(self) -> bool:
        return any(
            [
                bool(self.nodes),
                bool(self.edges),
                bool(self.participants),
                bool(self.messages),
                bool(self.steps),
                bool(self.decisions),
                bool(self.components),
                bool(self.interfaces),
                bool(self.protocols),
            ]
        )

    @property
    def is_meaningful(self) -> bool:
        return bool(
            self.summary
            or self.raw_text
            or self.has_structured_content
            or self.title
            or self.keywords
        )

    def to_retrieval_text(self) -> str:
        """
        Convert structured extraction into retrieval-friendly normalized text.

        This text is intended for embeddings and downstream semantic search.
        """
        lines: list[str] = [f"Diagram type: {self.diagram_type.value}"]

        if self.title:
            lines.append(f"Title: {self.title}")

        if self.summary:
            lines.append(f"Summary: {self.summary}")

        if self.nodes:
            node_labels = ", ".join(node.label for node in self.nodes if node.label)
            if node_labels:
                lines.append(f"Nodes: {node_labels}")

        if self.edges:
            lines.append("Relationships:")
            for edge in self.edges:
                relation = f"- {edge.source} -> {edge.target}"
                if edge.label:
                    relation += f": {edge.label}"
                if edge.condition:
                    relation += f" [condition: {edge.condition}]"
                lines.append(relation)

        if self.participants:
            lines.append(f"Participants: {', '.join(self.participants)}")

        if self.messages:
            lines.append("Messages:")
            for message in sorted(self.messages, key=lambda x: x.order):
                line = f"- {message.order}. {message.sender} -> {message.receiver}: {message.label}"
                if message.condition:
                    line += f" [condition: {message.condition}]"
                lines.append(line)

        if self.steps:
            lines.append("Steps:")
            for step in sorted(self.steps, key=lambda x: x.order):
                line = f"- {step.order}. {step.label}"
                if step.step_type:
                    line += f" ({step.step_type})"
                lines.append(line)

        if self.decisions:
            lines.append(f"Decisions: {', '.join(self.decisions)}")

        if self.components:
            lines.append(f"Components: {', '.join(self.components)}")

        if self.interfaces:
            lines.append(f"Interfaces: {', '.join(self.interfaces)}")

        if self.protocols:
            lines.append(f"Protocols: {', '.join(self.protocols)}")

        if self.keywords:
            lines.append(f"Keywords: {', '.join(self.keywords)}")

        if self.raw_text:
            lines.append(f"Raw text: {self.raw_text}")

        if self.confidence is not None:
            lines.append(f"Confidence: {self.confidence:.2f}")

        return "\n".join(lines).strip()


class DiagramExtractionResult(BaseModel):
    """
    Wrapper model that can be used as the output of a classifier/extractor service.
    """

    model_config = ConfigDict(extra="forbid")

    extraction: DiagramExtraction
    warnings: list[str] = Field(default_factory=list)
    classifier_source: Optional[str] = Field(default=None, max_length=200)
    extractor_source: Optional[str] = Field(default=None, max_length=200)