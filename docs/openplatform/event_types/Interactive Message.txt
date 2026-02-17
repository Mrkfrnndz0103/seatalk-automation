Event: Interactive Message Click
Event Description
This event is triggered when a callback button on an interactive message card is clicked by a user.

Event Parameter
Header

Parameter

Type

Description

Content-Type

string

Request header format

Signature

unit64

A signature to ensure that the request is sent by SeaTalk

Body

Parameter

Type

Description

event_id

string

The ID of the event

event_type

string

The type of the event. It will be "interactive_message_click" in this case

timestamp

unit64

The time when this event happened

app_id

string

The ID of the app to receive the event notification

event

object

Event-specific information

∟message_id

string

The ID of the interactive message card

∟employee_code

string

The employee_code of the user

∟email

string

The email of the user

∟value

string

The callback value of the button clicked

∟seatalk_id

string

The seatalk_id of the user (Will be supported soon)

∟group_id

string

Effective from 11 June 2024.

The ID of the group chat where this event happened. Empty if it is a 1-1 chat.

∟thread_id

string

Effective from 11 June 2024.

The thread ID. Provided if the interactive message is part of a thread.

Request Body Sample

{
    "event_id":"1234567",
    "event_type":"interactive_message_click",
    "timestamp":1611220944,
    "app_id":"abcdefghiklmn",
    "event":{
        "message_id":"abcdefghiklmn",
        "employee_code":"e_12345678",
        "email":"sample@seatalk.biz",
        "value":"collected",
        "seatalk_id":"1419488144",
        "group_id":"qwertyui",
        "thread_id":"afbbvufake"
    }
}
