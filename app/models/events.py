from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IncomingMessageText(BaseModel):
    content: str | None = None
    plain_text: str | None = None


class IncomingMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    message_id: str | None = None
    thread_id: str | None = None
    tag: str | None = None
    text: IncomingMessageText | None = None


class CallbackEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    seatalk_challenge: str | None = None
    seatalk_id: str | None = None
    employee_code: str | None = None
    email: str | None = None
    group_id: str | None = None
    value: str | None = None
    message_id: str | None = None
    thread_id: str | None = None
    message: IncomingMessage | None = None


class CallbackEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str | None = None
    event_type: str = Field(default="")
    timestamp: int | None = None
    app_id: str | None = None
    event: CallbackEvent | dict[str, Any] | None = None


EVENT_VERIFICATION = "event_verification"
USER_ENTER_CHATROOM_WITH_BOT = "user_enter_chatroom_with_bot"
MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"
NEW_MESSAGE_RECEIVED_FROM_THREAD = "new_message_received_from_thread"
