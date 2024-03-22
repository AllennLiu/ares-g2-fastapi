#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.openldap import ADHandler
from library.params import validate_email

from jose import JWTError, jwt
from pydantic import BaseModel, validator
from starlette.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Annotated, Coroutine, Optional, Union
from fastapi import status, APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY: str = 'e7dcaf2c9aad1a9f68c7a53b8b7b3d106c91373d88c41ce9bdf7472b922065d9'
ALGORITHM: str = 'HS256'
ACCESS_TOKEN_EXPIRE_MINS: float = 1440.0

class Token(BaseModel):
    access_token : str
    token_type   : str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    user_mail       : Optional[str]  = ''
    given_name      : Optional[str]  = None
    first_name      : Optional[str]  = None
    full_name       : Optional[str]  = None
    user_id         : Optional[str]  = None
    user_cn         : Optional[str]  = None
    user_web_name   : Optional[str]  = None
    user_department : Optional[str]  = None
    user_title      : Optional[str]  = ''
    user_location   : Optional[str]  = ''

    @validator('user_mail', pre=True)
    def validate_mail(value, field):
        return value if validate_email(value) else None

oauth2_scheme: OAuth2PasswordBearer = OAuth2PasswordBearer(tokenUrl='/user/auth')

router = APIRouter()

def create_access_token(
    data: Dict[str, Union[str, dict]], expires_delta: Union[timedelta, None] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire: datetime = datetime.now(timezone.utc) + timedelta(minutes=720)
    to_encode |= { "exp": expire }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)] = Depends(oauth2_scheme)
) -> Coroutine[None, None, Union[Dict[str, Any], HTTPException]]:
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail      = 'Could not validate credentials',
        headers     = { "WWW-Authenticate": "Bearer" }
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ ALGORITHM ])
        username: str = payload.get('sub')
        if username is None: raise credentials_exception
        TokenData(username=username)
    except JWTError as jwt_err:
        raise credentials_exception from jwt_err
    user: dict = payload.get('user')
    if user is None: raise credentials_exception
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)] = Depends(get_current_user)
) -> Coroutine[None, None, User]:
    return current_user

DEPENDS_USER = Depends(get_current_active_user)

@router.post('/user/auth', response_model=Token, tags=['Authenticate'])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """
    Using double check that refer to rule of authorize
    is going to check as following order:
    The user could be authorized with Inventec AD.
    """
    with ADHandler(form_data.username, form_data.password) as c:
        if not c:
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = 'AD Unauthorized',
                headers     = { "WWW-Authenticate": "Bearer" },
            )
        msad_user_data: Dict[str, Any] = c.parser()

    # update JWT with specified data
    access_token_expires: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINS)
    access_token: str = create_access_token(
        data={ "sub": form_data.username, "user": msad_user_data },
        expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type='bearer')

@router.get('/user/private', response_model=User, tags=['Authenticate'])
async def user_private_info(
    current_user: Annotated[User, DEPENDS_USER] = DEPENDS_USER) -> JSONResponse:
    return current_user
