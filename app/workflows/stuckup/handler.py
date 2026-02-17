from app.config import Settings
from app.workflows.base import WorkflowContext, WorkflowResult
from app.workflows.stuckup.service import StuckupService


class StuckupWorkflow:
    commands = ("/stuckup", "stuckup")

    def __init__(self, settings: Settings) -> None:
        self._service = StuckupService(settings)

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip()
        lowered = text.lower()
        if not any(lowered.startswith(cmd) for cmd in self.commands):
            return WorkflowResult(handled=False)

        remainder = text.split(" ", 1)[1].strip() if " " in text else ""
        if not remainder or remainder.lower() in {"help", "-h", "--help"}:
            return WorkflowResult(handled=True, response_text=self._help_text())

        action = remainder.split(" ", 1)[0].strip().lower()
        if action != "sync":
            return WorkflowResult(
                handled=True,
                response_text="Unknown stuckup action. Use `/stuckup sync` or `/stuckup help`.",
            )

        result = self._service.sync_source_sheet_to_supabase()
        return WorkflowResult(
            handled=True,
            response_text=(
                "Stuckup sync completed.\n"
                f"Status: {result.status}\n"
                f"Message: {result.message}\n"
                f"Source rows imported to Supabase: {result.source_rows}\n"
                f"Rows upserted in Supabase: {result.upserted_rows}\n"
                f"Rows exported to target Google Sheet: {result.exported_rows}\n"
                f"Columns exported to target Google Sheet: {result.exported_columns}"
            ),
        )

    def _help_text(self) -> str:
        return (
            "Stuckup commands:\n"
            "`/stuckup sync` - Source sheet (38 columns) -> Supabase -> Target sheet selected columns.\n"
            "Export ranges are controlled by `STUCKUP_EXPORT_RANGES` (default: B1:E,I1:J,M,Q1:U,Y1:AA,AH1:AK)."
        )
