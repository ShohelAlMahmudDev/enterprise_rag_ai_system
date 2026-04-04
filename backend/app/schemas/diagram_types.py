from enum import Enum
from typing import Iterable


class DiagramType(str, Enum):
    STATE_MACHINE = "state_machine"
    FLOWCHART = "flowchart"
    SEQUENCE = "sequence"
    ARCHITECTURE = "architecture"
    NETWORK = "network"
    TABLE_SCREENSHOT = "table_screenshot"
    UI_SCREENSHOT = "ui_screenshot"
    GENERIC_IMAGE = "generic_image"

    @classmethod
    def from_value(cls, value: str | None) -> "DiagramType":
        if value is None:
            return cls.GENERIC_IMAGE

        normalized = cls._normalize(value)
        if not normalized:
            return cls.GENERIC_IMAGE

        for item in cls:
            if normalized == item.value:
                return item

        return cls._alias_map().get(normalized, cls.GENERIC_IMAGE)

    @property
    def is_structured_diagram(self) -> bool:
        return self in {
            self.STATE_MACHINE,
            self.FLOWCHART,
            self.SEQUENCE,
            self.ARCHITECTURE,
            self.NETWORK,
            self.TABLE_SCREENSHOT,
        }

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = value.strip().lower()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized

    @classmethod
    def _alias_map(cls) -> dict[str, "DiagramType"]:
        return {
            "state_diagram": cls.STATE_MACHINE,
            "state_machine_diagram": cls.STATE_MACHINE,
            "statechart": cls.STATE_MACHINE,
            "fsm": cls.STATE_MACHINE,
            "finite_state_machine": cls.STATE_MACHINE,
            "flow_chart": cls.FLOWCHART,
            "process_flow": cls.FLOWCHART,
            "process_flowchart": cls.FLOWCHART,
            "workflow": cls.FLOWCHART,
            "workflow_diagram": cls.FLOWCHART,
            "decision_flow": cls.FLOWCHART,
            "sequence_diagram": cls.SEQUENCE,
            "message_sequence_chart": cls.SEQUENCE,
            "msc": cls.SEQUENCE,
            "interaction_diagram": cls.SEQUENCE,
            "architecture_diagram": cls.ARCHITECTURE,
            "system_architecture": cls.ARCHITECTURE,
            "component_diagram": cls.ARCHITECTURE,
            "deployment_diagram": cls.ARCHITECTURE,
            "solution_architecture": cls.ARCHITECTURE,
            "technical_architecture": cls.ARCHITECTURE,
            "network_diagram": cls.NETWORK,
            "topology": cls.NETWORK,
            "network_topology": cls.NETWORK,
            "connectivity_diagram": cls.NETWORK,
            "communication_diagram": cls.NETWORK,
            "table": cls.TABLE_SCREENSHOT,
            "table_image": cls.TABLE_SCREENSHOT,
            "spreadsheet_screenshot": cls.TABLE_SCREENSHOT,
            "grid": cls.TABLE_SCREENSHOT,
            "matrix": cls.TABLE_SCREENSHOT,
            "ui": cls.UI_SCREENSHOT,
            "ui_image": cls.UI_SCREENSHOT,
            "user_interface": cls.UI_SCREENSHOT,
            "screen": cls.UI_SCREENSHOT,
            "screenshot": cls.UI_SCREENSHOT,
            "app_screenshot": cls.UI_SCREENSHOT,
            "dashboard": cls.UI_SCREENSHOT,
            "image": cls.GENERIC_IMAGE,
            "generic": cls.GENERIC_IMAGE,
            "unknown": cls.GENERIC_IMAGE,
            "other": cls.GENERIC_IMAGE,
        }


def normalize_diagram_types(values: Iterable[str | None]) -> list[DiagramType]:
    return [DiagramType.from_value(value) for value in values]