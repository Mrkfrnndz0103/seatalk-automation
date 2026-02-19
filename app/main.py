import logging
from contextlib import asynccontextmanager

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

@asynccontextmanager
async def lifespan(_: FastAPI):
    stuckup_monitor.start()
    try:
        yield
    finally:
        await stuckup_monitor.stop()


app = FastAPI(
    title="SeaTalk Workflow Automation Server",
    version="0.1.0",
    lifespan=lifespan,
)


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/uptime-ping", methods=["GET", "HEAD"])
async def uptime_ping() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/stuckup/status")
async def stuckup_status() -> dict:
    return stuckup_monitor.get_status()


@app.post("/callbacks/seatalk")
async def seatalk_callback(request: Request, signature: str | None = Header(default=None)):
    body = await request.body()

    if settings.seatalk_verify_signature:
        signing_secrets = settings.seatalk_callback_signing_secrets
        if signing_secrets:
            if not any(is_valid_signature(secret, body, signature) for secret in signing_secrets):
                raise HTTPException(status_code=401, detail="invalid callback signature")
        elif not is_valid_signature("", body, signature):
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
        await _handle_bot_added_to_group_chat(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
        await _handle_new_mentioned_message_received_from_group_chat(payload)
        return JSONResponse({"code": 0})

    if payload.event_type == NEW_MESSAGE_RECEIVED_FROM_THREAD:
        await _handle_new_message_received_from_thread(payload)
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
            "Hello! 👋 How can I assist you today?"
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


async def _handle_bot_added_to_group_chat(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    group_id = _group_id_from_event(event)
    logger.info("bot_added_to_group_chat: event_id=%s payload=%s", payload.event_id, event.model_dump())
    if not group_id:
        logger.warning("group_id missing for bot_added_to_group_chat event_id=%s", payload.event_id)
        return

    await seatalk_client.send_group_text_message(
        group_id=group_id,
        content=(
            "Hi everyone, thanks for adding me. "
            "I can help with /stuckup, /backlogs, /shortlanded, and /lh_request. "
            "Mention me in a thread or send a message here."
        ),
    )


async def _handle_new_mentioned_message_received_from_group_chat(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    message = event.message
    text_content = _extract_text_content(message)
    logger.info(
        "new_mentioned_message_received_from_group_chat: event_id=%s group_id=%s message_id=%s thread_id=%s",
        payload.event_id,
        event.group_id,
        message.message_id if message else None,
        message.thread_id if message else None,
    )
    if not message or message.tag != "text" or not text_content:
        return
    if not event.group_id:
        logger.warning("group_id missing in mentioned-group callback event_id=%s", payload.event_id)
        return

    context = WorkflowContext(
        employee_code=_actor_employee_code(event),
        seatalk_id=event.seatalk_id or (message.sender.seatalk_id if message and message.sender else None),
        thread_id=message.thread_id,
        text=text_content,
    )
    result = workflow_router.route(context)
    if result.response_text:
        await seatalk_client.send_group_text_message(
            group_id=event.group_id,
            content=result.response_text,
            thread_id=message.thread_id,
        )


async def _handle_new_message_received_from_thread(payload: CallbackEnvelope) -> None:
    event = _normalize_event(payload.event)
    message = event.message
    text_content = _extract_text_content(message)
    logger.info(
        "new_message_received_from_thread: event_id=%s group_id=%s message_id=%s thread_id=%s",
        payload.event_id,
        event.group_id,
        message.message_id if message else None,
        message.thread_id if message else None,
    )
    if not message or message.tag != "text" or not text_content:
        return
    if not event.group_id:
        logger.warning("group_id missing in thread-message callback event_id=%s", payload.event_id)
        return

    context = WorkflowContext(
        employee_code=_actor_employee_code(event),
        seatalk_id=event.seatalk_id or (message.sender.seatalk_id if message and message.sender else None),
        thread_id=message.thread_id,
        text=text_content,
    )
    result = workflow_router.route(context)
    if result.response_text:
        await seatalk_client.send_group_text_message(
            group_id=event.group_id,
            content=result.response_text,
            thread_id=message.thread_id,
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


def _actor_employee_code(event: CallbackEvent) -> str:
    message = event.message
    sender = message.sender if message else None

    if event.employee_code:
        return event.employee_code
    if sender and sender.employee_code:
        return sender.employee_code
    if event.seatalk_id:
        return f"seatalk_{event.seatalk_id}"
    if sender and sender.seatalk_id:
        return f"seatalk_{sender.seatalk_id}"
    return "unknown_actor"


def _group_id_from_event(event: CallbackEvent) -> str:
    if event.group_id:
        return event.group_id
    if event.group and event.group.group_id:
        return event.group.group_id
    return ""
