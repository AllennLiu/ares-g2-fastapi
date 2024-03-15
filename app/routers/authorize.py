#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.openldap import ADHandler
from library.params import validate_email

from jose import JWTError, jwt
from pydantic import BaseModel, validator
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Coroutine, Optional, Union
from fastapi import status, APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = 'e7dcaf2c9aad1a9f68c7a53b8b7b3d106c91373d88c41ce9bdf7472b922065d9'
ALGORITHM  = 'HS256'
ACCESS_TOKEN_EXPIRE_MINS = 1440

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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/user/auth')

router = APIRouter()

def create_access_token(
    data: Dict[str, Union[str, dict]], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=720)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def current_user(token: str = Depends(oauth2_scheme)
    ) -> Coroutine[None, None, Union[Dict[str, Any], HTTPException]]:
    try:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ ALGORITHM ])
            username: str = payload.get('sub')
            assert username is not None
            TokenData(username=username)
        except JWTError:
            assert False
        user = payload.get('user')
        assert user is not None
        return user
    except AssertionError as err:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = 'Could not validate credentials',
            headers     = { "WWW-Authenticate": "Bearer" },
        ) from err

async def current_active(
    current_user: User = Depends(current_user)) -> Coroutine[None, None, User]:
    return current_user

@router.post('/user/auth', response_model=Token, tags=['Authenticate'])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
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
        msad_user_data = c.parser()

    # update JWT with specified data
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINS)
    access_token = create_access_token(
        data={ "sub": form_data.username, "user": msad_user_data },
        expires_delta=access_token_expires
    )
    return { "access_token": access_token, "token_type": "bearer" }

@router.get('/user/private', response_model=User, tags=['Authenticate'])
async def user_private_info(user : User = Depends(current_active)):
    return user
