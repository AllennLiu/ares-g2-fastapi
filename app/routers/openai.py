#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.iteration import find
from library.schemas import ChatGptDB
from library.config import azure_openai
from library.helpers import websocket_catch
from library.cacher import RedisContextManager
from routers.session import backend, cookie, session_exist

from uuid import UUID
from json import loads, dumps
from datetime import datetime
from openai import AsyncAzureOpenAI
from asyncio import sleep as asleep
from functools import lru_cache, partial
from openai.types.chat import ChatCompletion
from fastapi.templating import Jinja2Templates
from typing import Any, Dict, List, Annotated, Coroutine
from dataclasses import asdict, dataclass, field, fields
from starlette.responses import JSONResponse, HTMLResponse
from fastapi import APIRouter, WebSocket, Request, Form, Query, Depends

FORM_ROLE = Form('user', description='The `role` of chat box')
FORM_CONTENT = Form(..., description='Chat message content')
FORM_TAB_NAME = Form('', description='Chat messages `tab name`')
FORM_DATE = Form(str(datetime.now().date()), description='Chat messages recording `date`')
QUERY_DATE = Query(str(datetime.now().date()), description='Chat messages recording `date`')
QUERY_COLUMN = Query('deleted', description='Chat messages `column` _(multiple separate with `,`)_')

router = APIRouter()

@dataclass
class ChatState:
    record_number : int = 0
    configs       : List[Dict[str, str]] = field(default_factory=lambda: [])

@dataclass
class ChatColumn:
    date   : str = ''
    column : Dict[str, Any] = field(default_factory=lambda: {})

@dataclass
class ChatRecord:
    user      : str  = ''
    assistant : str  = ''
    user_id   : str  = ''
    date      : str  = str(datetime.now().date())
    tab_name  : str  = ''
    timestamp : int  = round(datetime.now().timestamp())
    raw_data  : dict = field(default_factory=lambda: {})
    deleted   : bool = False

@dataclass
class Conversation:
    role    : str = 'system'
    content : str = 'You are a helpful assistant.'

    def __init__(self, **kwargs: Any) -> None:
        names = set([ f.name for f in fields(self) ])
        for k in kwargs:
            if k in names:
                setattr(self, k, kwargs[k])

async def openai_conn(*args: Any, **keywords: Any) -> Coroutine[Any, Any, ChatCompletion]:
    client = AsyncAzureOpenAI(
        azure_endpoint = azure_openai.azure_openai_endpoint,
        api_key        = str(azure_openai.azure_openai_api_key),
        api_version    = azure_openai.openai_api_version
    )
    return await client.chat.completions.create(*args, **keywords)

chat = partial(openai_conn, model=azure_openai.openai_api_model, frequency_penalty=0.5, presence_penalty=0.7)

def openai_chat_record(user: str, assistant: str, user_id: str, date: str, raw_data: dict) -> None:
    raw_data.pop('choices', None)
    with RedisContextManager() as r:
        queries = loads(r.hget(ChatGptDB.records, user_id) or '[]')
        entry = find(lambda q: q.get('date') == date and q.get('tab_name'), queries) or {}
        ts = round(datetime.now().timestamp())
        args = ( user, assistant, user_id, date, entry.get('tab_name', ''), ts, raw_data )
        data: List[Dict[str, Any]] = [ *queries, asdict(ChatRecord(*args)) ]
        r.hset(ChatGptDB.records, user_id, dumps(data).encode('utf-8'))

def openai_chat_get_records(user_id: str) -> List[dict]:
    with RedisContextManager() as r:
        return loads(r.hget(ChatGptDB.records, user_id) or '[]')

def openai_chat_set_records(user_id: str, records: List[dict]) -> None:
    with RedisContextManager() as r:
        r.hset(ChatGptDB.records, user_id, dumps(records).encode('utf-8'))

def openai_chat_configure(user_id: str, date: str, data: dict) -> List[dict]:
    """Configure each message entires with passing data then save it"""
    for q in (records := openai_chat_get_records(user_id)):
        if q.get('date') != date: continue
        q |= asdict(ChatRecord(**q | data))
    openai_chat_set_records(user_id, records)
    return records

@lru_cache
def openai_keep_conversation(user_id: str, date: str) -> List[Dict[str, str]]:
    conversations: List[Dict[str, str]] = [ asdict(Conversation()) ]
    for q in openai_chat_get_records(user_id):
        if q.get('date') != date: continue
        for role in [ 'user', 'assistant' ]:
            conversations.append(asdict(Conversation(role=role, content=q.get(role))))
    return conversations

@router.get('/openai/chatgpt', response_class=HTMLResponse, include_in_schema=False)
async def openai_chatgpt(request: Request) -> HTMLResponse:
    template = Jinja2Templates(directory='../templates/')
    return template.TemplateResponse('chatgpt.html', context={ "request": request })

@router.websocket('/openai/ws/chat/{user_id}/{date}')
@websocket_catch
async def chat_box(websocket: WebSocket, user_id: str, date: str) -> None:
    await websocket.accept()
    while True:
        content = await websocket.receive_text()
        streams = await chat(messages=[
            *openai_keep_conversation(user_id, date), { "role": "user", "content": content }
        ], stream=True)
        messages: List[str] = []
        async for chunk in streams:
            message = chunk.choices[0].delta.content or ''
            await websocket.send_json({ "content": message, "completion": False })
            messages.append(message)
        await websocket.send_json({ "content": None, "completion": True })
        openai_chat_record(
            content, ''.join(messages), user_id, date, chunk.model_dump(exclude_unset=True))
        await asleep(1)

@router.websocket('/openai/ws/chat/stat/{user_id}/{date}')
@websocket_catch
async def chat_stat_socket(websocket: WebSocket, user_id: str, date: str) -> None:
    await websocket.accept()
    while True:
        state: ChatState = ChatState()
        for q in openai_chat_get_records(user_id):
            if q.get('deleted'): continue
            config = { "date": q.get('date'), "tab_name": q.get('tab_name') }
            if config not in state.configs:
                state.configs.append(config)
            state.record_number += 2 if q.get('date') == date else 0
        await websocket.send_json(asdict(state))
        await asleep(10)

@router.post('/api/v1/openai/chat', tags=['OpenAI'])
async def create_chat(
    content   : Annotated[str, FORM_CONTENT] = FORM_CONTENT,
    role      : Annotated[str, FORM_ROLE] = FORM_ROLE,
    session_id: UUID = Depends(cookie)) -> JSONResponse:
    session_data = await session_exist(session_id)
    session_data.data["conversations"] = session_data.data.get('conversations', [asdict(Conversation())])
    session_data.data["conversations"].append(asdict(Conversation(role=role, content=content)))
    chat_completion = await chat(messages=session_data.data["conversations"])
    reply = dict(chat_completion.choices[0].message)
    session_data.data["conversations"].append(asdict(Conversation(**reply)))
    await backend.update(session_id, session_data)
    return JSONResponse(status_code=200, content=dict(session_data))

@router.get('/api/v1/openai/chat/column/{user_id}', tags=['OpenAI'])
async def get_chat_column(
    user_id: str, column: Annotated[str, QUERY_COLUMN] = QUERY_COLUMN) -> JSONResponse:
    columns: List[Dict[str, Any]] = []
    for q in openai_chat_get_records(user_id):
        chat_column = { e: q.get(e) for e in column.split(',') if e in q }
        if (data := asdict(ChatColumn(q.get('date'), chat_column))) in columns: continue
        if not data.get('column') or q.get('deleted'): continue
        columns.append(data)
    return JSONResponse(status_code=200, content=list(columns))

@router.get('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def get_chat_messages(
    user_id: str, date: Annotated[str, QUERY_DATE] = QUERY_DATE) -> JSONResponse:
    records = openai_chat_get_records(user_id)
    messages = [ q for q in records if q.get('date') == date and not q.get('deleted') ]
    return JSONResponse(status_code=200, content=messages)

@router.put('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def update_chat_messages(user_id: str) -> JSONResponse:
    for q in (records := openai_chat_get_records(user_id)):
        q |= asdict(ChatRecord(**q))
    openai_chat_set_records(user_id, records)
    return JSONResponse(status_code=200, content=records)

@router.delete('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def delete_chat_messages(
    user_id: str, date: Annotated[str, FORM_DATE] = FORM_DATE) -> JSONResponse:
    resp = openai_chat_configure(user_id, date, { "deleted": True })
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/openai/chat/rename/{user_id}', tags=['OpenAI'])
async def rename_chat_messages(
    user_id : str,
    date    : Annotated[str, FORM_DATE] = FORM_DATE,
    tab_name: Annotated[str, FORM_TAB_NAME] = FORM_TAB_NAME) -> JSONResponse:
    resp = openai_chat_configure(user_id, date, { "tab_name": tab_name or date })
    return JSONResponse(status_code=200, content=resp)
