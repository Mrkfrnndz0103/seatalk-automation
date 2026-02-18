from app.config import Settings
from app.workflows.base import WorkflowContext, WorkflowResult


class StuckupWorkflow:
    commands = ("/stuckup", "stuckup")

    def __init__(self, settings: Settings) -> None:
        pass

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip()
        lowered = text.lower()
        if not any(lowered.startswith(cmd) for cmd in self.commands):
            return WorkflowResult(handled=False)

        remainder = text.split(" ", 1)[1].strip() if " " in text else ""
        if not remainder or remainder.lower() in {"help", "-h", "--help"}:
            return WorkflowResult(handled=True, response_text=self._help_text())

        return WorkflowResult(
            handled=True,
            response_text=(
                "I can't run a manual stuckup sync from chat right now.\n"
                "I run stuckup sync automatically in the background.\n"
                "Type `/stuckup help` if you want the setup details."
            ),
        )

    def _help_text(self) -> str:
        return (
            "I handle stuckup sync automatically.\n"
            "Manual `/stuckup sync` is currently turned off.\n"
            "I can run on a schedule, on reference-row changes, or both.\n"
            "The behavior is controlled by your STUCKUP settings in `.env`.\n"
            "You can type `/stuckup help` anytime to see this guide again."
        )
