import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.events import (
    BOT_ADDED_TO_GROUP_CHAT,
    EVENT_VERIFICATION,
    INTERACTIVE_MESSAGE_CLICK,
    MESSAGE_FROM_BOT_SUBSCRIBER,
    NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT,
    NEW_MESSAGE_RECEIVED_FROM_THREAD,
    USER_ENTER_CHATROOM_WITH_BOT,
    CallbackEnvelope,
    CallbackEvent,
)
from app.seatalk.client import SeaTalkClient
from app.seatalk.signature import is_valid_signature
from app.workflows.base import WorkflowContext
from app.workflows.router import WorkflowRouter
from app.workflows.stuckup.monitor import StuckupMonitor

logger = logging.getLogger(__name__)
settings = get_settings()
seatalk_client = SeaTalkClient(settings)
workflow_router = WorkflowRouter(settings)
stuckup_monitor = StuckupMonitor(settings)

app = FastAPI(title="SeaTalk Workflow Automation Server", version="0.1.0")


@app.on_event("startup")
async def startup_event() -> None:
    stuckup_monitor.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await stuckup_monitor.stop()


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

    if payload.event_type == USER_ENTER_CHATROOM_WITH_BOT:
        await _handle_user_enter_chatroom_with_bot(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == INTERACTIVE_MESSAGE_CLICK:
        _handle_interactive_message_click(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == BOT_ADDED_TO_GROUP_CHAT:
        _handle_bot_added_to_group_chat(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
        _handle_new_mentioned_message_received_from_group_chat(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == NEW_MESSAGE_RECEIVED_FROM_THREAD:
        _handle_new_message_received_from_thread(payload)
        return JSONResponse({"code": 0})

    # Ack unsupported events to avoid retries.
    return JSONResponse({"code": 0, "message": f"ignored event_type={payload.event_type}"})


async def _handle_message_from_bot_subscriber(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    if not event.employee_code:
        logger.warning("employee_code missing in callback event_id=%s", payload.event_id)
        return

    message = event.message
    text_content = _extract_text_content(message)
    if not message or message.tag != "text" or not text_content:
        logger.info("ignored non-text message event_id=%s", payload.event_id)
        return

    context = WorkflowContext(
        employee_code=event.employee_code,
        seatalk_id=event.seatalk_id,
        thread_id=message.thread_id,
        text=text_content,
    )
    result = workflow_router.route(context)

    if result.response_text:
        await seatalk_client.send_text_message(
            employee_code=event.employee_code,
            content=result.response_text,
            thread_id=message.thread_id,
        )


async def _handle_user_enter_chatroom_with_bot(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    if not event.employee_code:
        logger.warning("employee_code missing for user_enter_chatroom_with_bot event_id=%s", payload.event_id)
        return

    await seatalk_client.send_text_message(
        employee_code=event.employee_code,
        content=(
            "Bot is online.\n"
            "Stuckup workflow is auto-triggered when source sheet reference row changes."
        ),
    )


def _handle_interactive_message_click(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    logger.info(
        "interactive_message_click: event_id=%s employee_code=%s message_id=%s value=%s group_id=%s thread_id=%s",
        payload.event_id,
        event.employee_code,
        event.message_id,
        event.value,
        event.group_id,
        event.thread_id,
    )


def _handle_bot_added_to_group_chat(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    logger.info("bot_added_to_group_chat: event_id=%s payload=%s", payload.event_id, event.model_dump())


def _handle_new_mentioned_message_received_from_group_chat(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    message = event.message
    logger.info(
        "new_mentioned_message_received_from_group_chat: event_id=%s group_id=%s message_id=%s thread_id=%s",
        payload.event_id,
        event.group_id,
        message.message_id if message else None,
        message.thread_id if message else None,
    )


def _handle_new_message_received_from_thread(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    message = event.message
    logger.info(
        "new_message_received_from_thread: event_id=%s group_id=%s message_id=%s thread_id=%s",
        payload.event_id,
        event.group_id,
        message.message_id if message else None,
        message.thread_id if message else None,
    )


def _normalize_event(event: CallbackEvent | dict | None) -> CallbackEvent:
    if isinstance(event, CallbackEvent):
        return event
    if isinstance(event, dict):
        return CallbackEvent.model_validate(event)
    return CallbackEvent()


def _extract_text_content(message) -> str:
    if not message or not message.text:
        return ""
    return (message.text.content or message.text.plain_text or "").strip()
