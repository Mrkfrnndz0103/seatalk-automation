from app.workflows.base import WorkflowContext, WorkflowResult


class LHRequestWorkflow:
    commands = ("/lh_request", "lh_request", "/lh", "lh request")

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip().lower()
        if any(text.startswith(cmd) for cmd in self.commands):
            return WorkflowResult(
                handled=True,
                response_text="LH Request workflow is scaffolded but not implemented yet.",
            )
        return WorkflowResult(handled=False)