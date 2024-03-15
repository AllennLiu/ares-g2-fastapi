#!/usr/bin/python3
# -*- coding: utf-8 -*-

from re import search
from uuid import UUID
from functools import wraps
from json import loads
from json.decoder import JSONDecodeError
from fastapi import HTTPException, Response, Query, Form, File
from typing import Any, Dict, Callable, Coroutine, Type, TypeVar, Union

try:
    from library.gitlabs import getProject, GITLAB_URL, Project, exceptions
except ModuleNotFoundError:
    from gitlabs import getProject, GITLAB_URL, Project, exceptions

QUERY_PAGE = Query(1, description='Search **Page**')
QUERY_SIZE = Query(10, description='Page **Size**')
QUERY_KEYW = Query('', description='Search **Keyword**')
QUERY_FORCE = Query(False, description='Set `Force` operation')
QUERY_SCRIPT = Query('SIT-Power-CycleTest', description='Require a `Script Name`')
QUERY_AUTHOR = Query(..., description='Require a `Author Name`')
QUERY_DATE_STRING = Query(..., description='Require a **`Date` String**', regex='^\d{4}\-\d{2}\-\d{2}$')
QUERY_MISSION_TYPE = Query('create', description='Require a `Mission Type`', regex='^create|update$')
QUERY_MISSION_ORDER = Query('next', description='Require a `Mission Order`', regex='^prev|next$')
QUERY_ARCHIVE = Query(
    f'{GITLAB_URL}/TA-Team/SIT-Power-CycleTest',
    description = 'Script `Archive Url` *(GitLab)*'
)
FORM_SCRIPT = Form('SIT-Power-CycleTest', description='Require a `Script Name`')
FORM_PAYLOADS = Form(..., description='Require a string of `JSON Array`')
FILE_SINGLE = File(None, description='File as **`Bytes`**')
FILE_MULTIPLE = File([], description='**Multiple** files as **`Bytes`**')

EXCEPT_T = TypeVar('EXCEPT_T')

def catch_exception(func: Callable[..., EXCEPT_T]) -> Callable[..., EXCEPT_T]:
    """捕捉接口或接口調用函數的例外，返回請求的 `http 422` 錯誤"""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Union[EXCEPT_T, HTTPException]:
        try:
            return func(*args, **kwargs)
        except Exception as err:
            print(str(err))
            raise HTTPException(status_code=422, detail=str(err)) from err
    return wrapper

GITLAB_A_T = TypeVar('GITLAB_A_T')

def catch_gitlab_router(func: Callable[..., GITLAB_A_T]
    ) -> Callable[..., Coroutine[Any, Any, GITLAB_A_T]]:
    """異步通過 GitLab API 請求發生例外，則返回例外的詳情與狀態碼"""
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> GITLAB_A_T:
        try:
            return await func(*args, **kwargs)
        except (exceptions.GitlabGetError, exceptions.GitlabHttpError) as e:
            msg = str(e).split(':')
            raise HTTPException(status_code=int(msg[0]), detail=msg[-1].strip()) from e
    return wrapper

def validate_uuid(uuid: str = '') -> bool:
    """驗證 UUID 格式並返回布林值"""
    try:
        return str(UUID(uuid, version=4)) != ''
    except ValueError:
        return False

def validate_email(address: str = '') -> str:
    """驗證郵件地址格式"""
    mail_regexp = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return search(mail_regexp, address)

def validate_json(raw: Union[str, bytes, bytearray]) -> bool:
    """驗證字符串是否為 JSON 格式並返回布林值"""
    try:
        return loads(raw) is not None
    except JSONDecodeError:
        return False

def validate_payloads(payloads: Union[str, bytes, bytearray], instance: type = list
    ) -> Union[dict, HTTPException]:
    """驗證請求接口 `Payloads` 格式是否為合法的 JSON 數據"""
    try:
        data = loads(payloads)
        assert isinstance(data, instance)
    except:
        raise HTTPException(status_code=422, detail='Invalid JSON Array')
    return data

def validate_gitlab_project(name: Union[str, int] = '', raise_e: bool = True
    ) -> Union[Project, HTTPException]:
    """依指定項目名稱查找 GitLab 項目，存在則返回 `Project` 實例"""
    args = { "id": name } if isinstance(name, int) else { "name": name }
    if not (project := getProject(**args)) and raise_e:
        raise HTTPException(status_code=404, detail='Project Not Found')
    return project

def json_parse(raw: Union[str, bytes, bytearray] = '{}') -> Union[dict, list]:
    """將傳入的字符串轉換為字典或數組"""
    if isinstance(raw, (dict, list)):
        return raw
    return loads(raw) if validate_json(raw) else eval(raw)

def raise_gitlab_list(instance: Any, key: str, all: bool = False) -> HTTPException:
    """因請求未找到指定的數據，可調用此函數引發 `404` 來提示可用的數據"""
    ids = [ e.id for e in instance.list(all=all) ]
    raise HTTPException(status_code=404, detail=f'{key} Not Found, Allowed List: {ids}')

def response_interpreter(resp: Type[Response], extra_headers: Dict[str, Any] = {}
    ) -> None:
    """拼接 `Headers` 至接口響應數據，前端會使用到"""
    resp.headers.update({
        "Cache-Control": "no-cache, no-store, must-revalidate, public, max-age=0",
        "Pragma"       : "no-cache",
        "Expires"      : "0",
        **extra_headers
    })
