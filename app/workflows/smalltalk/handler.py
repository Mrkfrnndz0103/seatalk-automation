import re

from app.workflows.base import WorkflowContext, WorkflowResult


class SmallTalkWorkflow:
    _GREETING_RE = re.compile(r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b")
    _HOW_ARE_YOU_RE = re.compile(r"\b(how are you|how r u|how're you)\b")
    _THANKS_RE = re.compile(r"\b(thanks|thank you|ty)\b")
    _BYE_RE = re.compile(r"\b(bye|goodbye|see you|cya)\b")
    _HELP_RE = re.compile(r"\b(help|what can you do|commands?)\b")

    def handle(self, context: WorkflowContext) -> WorkflowResult:
        text = context.text.strip()
        if not text:
            return WorkflowResult(handled=False)

        lowered = re.sub(r"\s+", " ", text.lower())

        # Keep slash commands on the command-routing path.
        if lowered.startswith("/"):
            return WorkflowResult(handled=False)

        if self._HOW_ARE_YOU_RE.search(lowered):
            return WorkflowResult(
                handled=True,
                response_text=(
                    "I'm doing well, thanks for asking. "
                    "I can help with /stuckup, /backlogs, /shortlanded, and /lh_request."
                ),
            )
        if self._GREETING_RE.search(lowered):
            return WorkflowResult(
                handled=True,
                response_text=(
                    "Hi! Nice to hear from you. "
                    "What do you want to work on today?"
                ),
            )
        if self._THANKS_RE.search(lowered):
            return WorkflowResult(
                handled=True,
                response_text="You're welcome. If you need a command, start with /stuckup help.",
            )
        if self._BYE_RE.search(lowered):
            return WorkflowResult(
                handled=True,
                response_text="See you. Message me anytime if you need help.",
            )
        if self._HELP_RE.search(lowered):
            return WorkflowResult(
                handled=True,
                response_text=(
                    "I can help with these workflows: /stuckup, /backlogs, /shortlanded, and /lh_request. "
                    "Try /stuckup help for setup details."
                ),
            )

        return WorkflowResult(
            handled=True,
            response_text=(
                "I hear you. I can help with /stuckup, /backlogs, /shortlanded, and /lh_request. "
                "Tell me which one you need."
            ),
        )
