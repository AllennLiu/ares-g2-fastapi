#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.config import settings
from library.cacher import RedisBackend

from uuid import UUID, uuid4
from pydantic import BaseModel
from datetime import timedelta
from typing import Coroutine, Union
from starlette.datastructures import Secret
from starlette.responses import JSONResponse
from fastapi import APIRouter, Response, HTTPException, Depends
from fastapi_sessions.session_verifier import SessionVerifier
from fastapi_sessions.frontends.implementations import SessionCookie, CookieParameters

SECRET_KEY: Secret = settings.app_config('JWT_SECRET_KEY', cast=Secret)
SESSION_EXPIRES: timedelta = timedelta(minutes=60)

class SessionData(BaseModel):
    data: dict = {}

router = APIRouter()

cookie = SessionCookie(
    cookie_name   = 'fastapi-cookie',
    identifier    = 'general_verifier',
    auto_error    = True,
    secret_key    = str(SECRET_KEY),
    cookie_params = CookieParameters(expires=SESSION_EXPIRES)
)
backend = RedisBackend[UUID, SessionData]()

class BasicVerifier(SessionVerifier[UUID, SessionData]):
    def __init__(
        self,
        *,
        identifier: str,
        auto_error: bool,
        backend: RedisBackend[UUID, SessionData],
        auth_http_exception: HTTPException,
    ) -> None:
        self._identifier = identifier
        self._auto_error = auto_error
        self._backend = backend
        self._auth_http_exception = auth_http_exception

    @property
    def identifier(self):
        return self._identifier

    @property
    def backend(self):
        return self._backend

    @property
    def auto_error(self):
        return self._auto_error

    @property
    def auth_http_exception(self):
        return self._auth_http_exception

    def verify_session(self, model: SessionData) -> bool:
        """If the session exists, it is valid, custom to provide
        the mechanism of user authentication, in the meantime to
        store the user authenticated data in session data.
        """
        return True

auth_exception = HTTPException(
    status_code=403, detail='Please create the session before this API requests'
)
verifier = BasicVerifier(
    identifier          = 'general_verifier',
    auto_error          = True,
    backend             = backend,
    auth_http_exception = auth_exception
)

async def session_exist(
    session_id: UUID
) -> Coroutine[None, None, Union[SessionData, HTTPException]]:
    if not (session_data := await backend.read(session_id)): raise auth_exception
    return SessionData(**session_data)

@router.get('/api/v1/session', dependencies=[Depends(cookie)], tags=['Session'])
async def session_info(session_data: SessionData = Depends(verifier)) -> JSONResponse:
    return JSONResponse(status_code=200, content=dict(session_data))

@router.post('/api/v1/session',  tags=['Session'])
async def session_create(response: Response):
    await backend.create(session := uuid4(), SessionData(), expires=SESSION_EXPIRES.seconds)
    cookie.attach_to_response(response, session)
    return 'session created'

@router.delete('/api/v1/session', tags=['Session'])
async def session_delete(
    response: Response, session_id: UUID = Depends(cookie)) -> JSONResponse:
    await session_exist(session_id)
    await backend.delete(session_id)
    cookie.delete_from_response(response)
    return JSONResponse(status_code=200, content={ "message": "session deleted" })
