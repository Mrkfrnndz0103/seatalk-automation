from app.config import Settings
from app.workflows.base import WorkflowContext
from app.workflows.router import WorkflowRouter


def _settings() -> Settings:
    return Settings(
        SEATALK_APP_ID="x",
        SEATALK_APP_SECRET="y",
    )


def test_plain_hello_returns_conversational_reply() -> None:
    router = WorkflowRouter(_settings())
    result = router.route(
        WorkflowContext(
            employee_code="e_1",
            seatalk_id="s_1",
            thread_id=None,
            text="hello",
        )
    )
    assert result.handled
    assert result.response_text is not None
    assert "Hi!" in result.response_text


def test_unknown_slash_command_keeps_command_fallback() -> None:
    router = WorkflowRouter(_settings())
    result = router.route(
        WorkflowContext(
            employee_code="e_1",
            seatalk_id="s_1",
            thread_id=None,
            text="/hello",
        )
    )
    assert not result.handled
    assert result.response_text is not None
    assert "I didn't catch that command." in result.response_text


def test_stuckup_command_still_routes_normally() -> None:
    router = WorkflowRouter(_settings())
    result = router.route(
        WorkflowContext(
            employee_code="e_1",
            seatalk_id="s_1",
            thread_id=None,
            text="/stuckup help",
        )
    )
    assert result.handled
    assert result.response_text is not None
    assert "Manual `/stuckup sync` is currently turned off." in result.response_text
