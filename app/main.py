import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.events import CallbackEnvelope, CallbackEvent, EVENT_VERIFICATION, MESSAGE_FROM_BOT_SUBSCRIBER
from app.seatalk.client import SeaTalkClient
from app.seatalk.signature import is_valid_signature
from app.workflows.base import WorkflowContext
from app.workflows.router import WorkflowRouter

logger = logging.getLogger(__name__)
settings = get_settings()
seatalk_client = SeaTalkClient(settings)
workflow_router = WorkflowRouter(settings)

app = FastAPI(title="SeaTalk Workflow Automation Server", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/callbacks/seatalk")
async def seatalk_callback(request: Request, signature: str | None = Header(default=None)):
    body = await request.body()

    if settings.seatalk_verify_signature:
        if not is_valid_signature(settings.seatalk_signing_secret, body, signature):
            raise HTTPException(status_code=401, detail="invalid callback signature")

    try:
        payload = CallbackEnvelope.model_validate_json(body)
    except Exception as exc:
        logger.exception("invalid callback payload")
        raise HTTPException(status_code=400, detail="invalid payload") from exc

    if payload.event_type == EVENT_VERIFICATION:
        event = _normalize_event(payload.event)
        challenge = event.seatalk_challenge or ""
        return JSONResponse({"seatalk_challenge": challenge})

    if payload.event_type == MESSAGE_FROM_BOT_SUBSCRIBER:
        await _handle_message_from_bot_subscriber(payload)
        return JSONResponse({"code": 0})

    # Ack unsupported events to avoid retries.
    return JSONResponse({"code": 0, "message": f"ignored event_type={payload.event_type}"})


async def _handle_message_from_bot_subscriber(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    if not event.employee_code:
        logger.warning("employee_code missing in callback event_id=%s", payload.event_id)
        return

    message = event.message
    if not message or message.tag != "text" or not message.text or not message.text.content:
        logger.info("ignored non-text message event_id=%s", payload.event_id)
        return

    context = WorkflowContext(
        employee_code=event.employee_code,
        seatalk_id=event.seatalk_id,
        thread_id=message.thread_id,
        text=message.text.content,
    )
    result = workflow_router.route(context)

    if result.response_text:
        await seatalk_client.send_text_message(
            employee_code=event.employee_code,
            content=result.response_text,
            thread_id=message.thread_id,
        )


def _normalize_event(event: CallbackEvent | dict | None) -> CallbackEvent:
    if isinstance(event, CallbackEvent):
        return event
    if isinstance(event, dict):
        return CallbackEvent.model_validate(event)
    return CallbackEvent()