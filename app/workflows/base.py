from dataclasses import dataclass


@dataclass
class WorkflowContext:
    employee_code: str
    seatalk_id: str | None
    thread_id: str | None
    text: str


@dataclass
class WorkflowResult:
    handled: bool
    response_text: str | None = None