#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.schemas import ChatGptDB
from library.config import azure_openai
from library.helpers import websocket_catch
from library.cacher import RedisContextManager

from json import loads, dumps
from datetime import datetime
from openai import AsyncAzureOpenAI
from asyncio import sleep as asleep
from functools import lru_cache, partial
from openai.types.chat import ChatCompletion
from fastapi.templating import Jinja2Templates
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Annotated, Coroutine
from starlette.responses import JSONResponse, HTMLResponse
from fastapi import APIRouter, WebSocket, Request, Form, Query

FORM_ROLE = Form('user', description='The `role` of chat box')
FORM_CONTENT = Form(..., description='Chat message content')
QUERY_DATE = Query(str(datetime.now().date()), description='Chat messages recording `date`')

router = APIRouter()

@dataclass
class ChatRecord:
    user      : str  = ''
    assistant : str  = ''
    user_id   : str  = ''
    date      : str  = str(datetime.now().date())
    timestamp : int  = round(datetime.now().timestamp())
    raw_data  : dict = field(default_factory=lambda: {})
    deleted   : bool = False

@dataclass
class Conversation:
    role    : str = 'system'
    content : str = 'You are a helpful assistant.'

async def openai_conn(*args: Any, **keywords: Any) -> Coroutine[Any, Any, ChatCompletion]:
    client = AsyncAzureOpenAI(
        azure_endpoint = azure_openai.azure_openai_endpoint,
        api_key        = azure_openai.azure_openai_api_key,
        api_version    = azure_openai.openai_api_version
    )
    return await client.chat.completions.create(*args, **keywords)

chat = partial(openai_conn, model=azure_openai.openai_api_model, frequency_penalty=0.5, presence_penalty=0.7)

def openai_chat_record(user: str, assistant: str, user_id: str, date: str, raw_data: dict) -> None:
    raw_data.pop('choices', None)
    args: tuple = ( user, assistant, user_id, date, round(datetime.now().timestamp()), raw_data )
    with RedisContextManager() as r:
        query = r.hget(ChatGptDB.records, user_id) or '[]'
        data: List[Dict[str, Any]] = [ *loads(query), asdict(ChatRecord(*args)) ]
        r.hset(ChatGptDB.records, user_id, dumps(data).encode('utf-8'))

def openai_chat_get_records(user_id: str) -> List[dict]:
    with RedisContextManager() as r:
        return loads(r.hget(ChatGptDB.records, user_id) or '[]')

def openai_chat_set_records(user_id: str, records: List[dict]) -> None:
    with RedisContextManager() as r:
        r.hset(ChatGptDB.records, user_id, dumps(records).encode('utf-8'))

@lru_cache
def openai_keep_conversation(user_id: str, date: str) -> List[Dict[str, str]]:
    conversations: List[Dict[str, str]] = [ asdict(Conversation()) ]
    for q in openai_chat_get_records(user_id):
        if q.get('date') != date: continue
        for role in [ 'user', 'assistant' ]:
            conversations.append(asdict(Conversation(role, q.get(role))))
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

@router.post('/api/v1/openai/chat', tags=['OpenAI'])
async def create_chat(
    content: Annotated[str, FORM_CONTENT] = FORM_CONTENT,
    role   : Annotated[str, FORM_ROLE] = FORM_ROLE) -> JSONResponse:
    chat_completion = await chat(messages = [{ "role": role, "content": content }])
    resp = dict(chat_completion.choices[0].message)
    # resp = chat_completion.model_dump(exclude_unset=True)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/openai/chat/dates/{user_id}', tags=['OpenAI'])
async def get_chat_dates(user_id: str) -> JSONResponse:
    dates = { q.get('date') for q in openai_chat_get_records(user_id) if not q.get('deleted') }
    return JSONResponse(status_code=200, content=list(dates))

@router.get('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def get_chat_messages(
    user_id: str, date: Annotated[str, QUERY_DATE] = QUERY_DATE) -> JSONResponse:
    records = openai_chat_get_records(user_id)
    messages = [ q for q in records if q.get('date') == date and not q.get('deleted') ]
    return JSONResponse(status_code=200, content=messages)

@router.put('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def update_chat_messages(user_id: str) -> JSONResponse:
    for q in (records := openai_chat_get_records(user_id)):
        q = asdict(ChatRecord(**q | { "deleted": q.get('deleted', False) }))
    openai_chat_set_records(user_id, records)
    return JSONResponse(status_code=200, content=records)

@router.delete('/api/v1/openai/chat/messages/{user_id}', tags=['OpenAI'])
async def delete_chat_messages(
    user_id: str, date: Annotated[str, QUERY_DATE] = QUERY_DATE) -> JSONResponse:
    for q in (records := openai_chat_get_records(user_id)):
        q = asdict(ChatRecord(
            **q | { "deleted": True if q.get('date') == date else q.get('deleted', False) }))
    openai_chat_set_records(user_id, records)
    return JSONResponse(status_code=200, content=records)
