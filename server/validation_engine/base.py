from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TestResult:
    test_id: str
    status: str  # PASS, FAIL, WARNING, SKIP
    target_device: str
    command_executed: str
    raw_output: str
    pass_criteria: str
    delta_summary: Optional[str] = None
    error_message: Optional[str] = None

class ValidationTest(ABC):
    def __init__(self, device: Any, test_id: str, layer: str):
        self.device = device
        self.test_id = test_id
        self.layer = layer

    @abstractmethod
    def run(self) -> TestResult:
        pass

    def parse_metrics(self, output: str) -> Dict[str, Any]:
        """Default metric parser, can be overridden by subclasses."""
        return {"raw": output}
