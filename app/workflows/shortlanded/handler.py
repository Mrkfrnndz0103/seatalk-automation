from app.workflows.base import WorkflowContext, WorkflowResult


class ShortlandedWorkflow:
    commands = ("/shortlanded", "shortlanded")

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip().lower()
        if any(text.startswith(cmd) for cmd in self.commands):
            return WorkflowResult(
                handled=True,
                response_text="I can't run the shortlanded workflow yet. It's still being built.",
            )
        return WorkflowResult(handled=False)
