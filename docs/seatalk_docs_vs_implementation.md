# SeaTalk docs vs implementation

This report compares `docs/openplatform` (API and event_type `.txt` files) with the current app implementation.

---

## 1. Server API Event Callback (callback behavior)

| Doc requirement | Applied |
|-----------------|--------|
| Callback URL verification: return `seatalk_challenge` in body, HTTP 200, within 5s | Yes - [app/main.py](app/main.py) `EVENT_VERIFICATION` branch |
| Respond HTTP 200 within 5 seconds | Yes - all branches return `JSONResponse` |
| Verify sender: SHA-256(body + signing_secret), base16 lower, compare to `Signature` header | Yes - [app/seatalk/signature.py](app/seatalk/signature.py) |

---

## 2. Event types (from `docs/openplatform/event_types/*.txt`)

| Event doc | `event_type` value | Applied in app |
|-----------|--------------------|----------------|
| Message Received From Bot User | `message_from_bot_subscriber` | Yes - handled in [app/main.py](app/main.py); text messages processed and replied via workflow + `send_text_message` |
| Bot Added To Group Chat | `bot_added_to_group_chat` | Yes - explicit handler in [app/main.py](app/main.py) (logging + ack) |
| User Enter Chatroom With Bot | `user_enter_chatroom_with_bot` | Yes - explicit handler in [app/main.py](app/main.py) (welcome/help message + ack) |
| New Mentioned Message From Group Chat | `new_mentioned_message_received_from_group_chat` | Yes - explicit handler in [app/main.py](app/main.py) (logging + ack) |
| Interactive Message | `interactive_message_click` | Yes - explicit handler in [app/main.py](app/main.py) (logging + ack) |
| New Message Received from Thread | `new_message_received_from_thread` | Yes - explicit handler in [app/main.py](app/main.py) (logging + ack) |

Note: `bot_removed_from_group_chat` appears in callback sample code but no dedicated event doc was provided under `docs/openplatform/event_types`.

---

## 3. Server APIs (from `docs/openplatform/api/*.txt`)

| API doc | Endpoint / purpose | Applied in app |
|---------|--------------------|----------------|
| Get App Access Token | `POST /auth/app_access_token` | Yes - [app/seatalk/client.py](app/seatalk/client.py) `_refresh_token()`, `get_token()` |
| Send Message to a Bot User | `POST /messaging/v2/single_chat` (text, etc.) | Yes - [app/seatalk/client.py](app/seatalk/client.py) `send_text_message()` (text with optional `thread_id`, `usable_platform`) |
| Send Message to Group Chat | `POST /messaging/v2/group_chat` | No - not implemented in client |
| Get Message by Message ID | `GET /messaging/v2/get_message_by_message_id` | No - not implemented |
| Set Typing Status in Group Chat | `POST /messaging/v2/group_chat_typing` | No - not implemented |
| Set Typing Status in Private Chat | `POST /messaging/v2/single_chat_typing` | No - not implemented |
| Get Thread by Thread ID in Private Chat | `GET /messaging/v2/single_chat/get_thread_by_thread_id` | No - not implemented |

Reference-only docs (no direct application in code): API Documentation Guide, Overview of Server APIs, OpenAPI Pagination Standard, SeaTalk Model Context Protocol Server.

---

## 4. Summary

- Applied: callback verification + signature, app token API, bot-user message API, and explicit handlers for all six event docs under `docs/openplatform/event_types`.
- Not applied: group-chat send API and other optional messaging APIs listed above.

If you want next, I can add `Send Message to Group Chat` so mention/thread events can produce in-group replies instead of log-only handling.
