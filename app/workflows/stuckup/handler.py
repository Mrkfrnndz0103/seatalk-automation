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
                "Manual stuckup trigger is disabled.\n"
                "Stuckup auto-sync runs when source sheet reference row changes.\n"
                "Use `/stuckup help` for config details."
            ),
        )

    def _help_text(self) -> str:
        return (
            "Stuckup commands:\n"
            "`/stuckup help` - Show workflow settings.\n"
            "Manual `/stuckup sync` is disabled.\n"
            "Auto-sync trigger: change detected on source sheet reference row (`STUCKUP_REFERENCE_ROW`, default 2).\n"
            "Poll interval: `STUCKUP_POLL_INTERVAL_SECONDS`.\n"
            "Filter statuses: `STUCKUP_FILTER_STATUS_VALUES`.\n"
            "Export columns: `STUCKUP_EXPORT_COLUMNS`."
        )
