from app.config import Settings
from app.workflows.backlogs.handler import BacklogsWorkflow
from app.workflows.base import WorkflowContext, WorkflowResult
from app.workflows.lh_request.handler import LHRequestWorkflow
from app.workflows.shortlanded.handler import ShortlandedWorkflow
from app.workflows.stuckup.handler import StuckupWorkflow


class WorkflowRouter:
    def __init__(self, settings: Settings) -> None:
        self._workflows = [
            StuckupWorkflow(settings),
            BacklogsWorkflow(),
            ShortlandedWorkflow(),
            LHRequestWorkflow(),
        ]

    def route(self, context: WorkflowContext) -> WorkflowResult:
        for workflow in self._workflows:
            result = workflow.handle(context)
            if result.handled:
                return result

        return WorkflowResult(
            handled=False,
            response_text=(
                "I didn't catch that command.\n"
                "You can chat with me using `/stuckup`, `/backlogs`, `/shortlanded`, or `/lh_request`."
            ),
        )
