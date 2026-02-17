from dataclasses import dataclass


@dataclass
class SinkResult:
    sink: str
    status: str
    message: str