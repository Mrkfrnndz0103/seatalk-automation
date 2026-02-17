from app.workflows.base import WorkflowContext, WorkflowResult


class BacklogsWorkflow:
    commands = ("/backlogs", "backlogs")

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip().lower()
        if any(text.startswith(cmd) for cmd in self.commands):
            return WorkflowResult(
                handled=True,
                response_text="Backlogs workflow is scaffolded but not implemented yet.",
            )
        return WorkflowResult(handled=False)