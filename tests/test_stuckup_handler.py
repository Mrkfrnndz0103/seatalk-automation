from app.config import Settings
from app.workflows.base import WorkflowContext
from app.workflows.stuckup.handler import StuckupWorkflow


def _settings() -> Settings:
    return Settings(
        SEATALK_APP_ID="x",
        SEATALK_APP_SECRET="y",
    )


def test_stuckup_help_message() -> None:
    workflow = StuckupWorkflow(_settings())
    result = workflow.handle(
        WorkflowContext(
            employee_code="e_1",
            seatalk_id="s_1",
            thread_id=None,
            text="/stuckup help",
        )
    )
    assert result.handled
    assert result.response_text is not None
    assert "Manual `/stuckup sync` is disabled." in result.response_text


def test_stuckup_manual_sync_disabled() -> None:
    workflow = StuckupWorkflow(_settings())
    result = workflow.handle(
        WorkflowContext(
            employee_code="e_1",
            seatalk_id="s_1",
            thread_id=None,
            text="/stuckup sync",
        )
    )
    assert result.handled
    assert result.response_text is not None
    assert "Manual stuckup trigger is disabled." in result.response_text
