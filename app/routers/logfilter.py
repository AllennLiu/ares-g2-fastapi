#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.config import ARES_ENDPOINT
from library.moment import datetime_data
from library.cacher import RedisContextManager
from library.mailer import FastMail, EmailManager
from library.schemas import LogFilterDB, FilterMap
from library.readme import search_readme, readme_update_version
from library.iteration import sortby_key, diff_array, pagination
from library.helpers import version_increment
from library.gitlabs import (getProject, getReadme, commit_message_template,check_pipeline_running_status,
    Project)
from library.params import (json_parse, validate_payloads, validate_gitlab_project, catch_gitlab_router,
    QUERY_PAGE, QUERY_SIZE, QUERY_KEYW)

from re import sub
from json import loads, dumps
from itertools import product
from dataclasses import asdict
from pydantic import validator, BaseModel
from starlette.responses import JSONResponse
from typing import Any, Dict, List, Annotated, Optional, Type, Union
from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks

QUERY_TYPE = Query(default='logfilter', description='List `Type`', regex='^logfilter|powercycle$')
QUERY_SCRIPT_ID = Query(12, description='A **number** of `Project ID`')
QUERY_FILE_PATH = Query('README.md', description='The **file** `Name/Path`')
QUERY_TOJSONIFY = Query(default=False, description='Convert it as `JSON`?')
QUERY_PROJECT_REF = Query(default='master', description='The **project** `Reference` *(branch)*')

router = APIRouter()
postman = EmailManager()

class FilterBase(BaseModel):
    project_id : Optional[int]  = 17
    file_path  : Optional[str]  = 'README.md'
    content    : Optional[str]  = ''
    ref        : Optional[str]  = 'master'

class FilterBody(FilterBase):
    author     : str
    content    : Optional[Dict[str, Any]] = {}
    comment    : Optional[str]  = ''
    type       : Optional[str]  = 'logfilter'

    @validator('type')
    def validate_type(value, field):
        types = [ 'logfilter', 'powercycle' ]
        if value not in types:
            raise ValueError(f'filter type must in {types}')
        return value

def logfilter_diff_logfilter(old: Dict[str, Any], new: Dict[str, Any]
    ) -> Dict[str, Dict[str, Union[List[str], Dict[str, List[str]]]]]:
    """從 JSON 文件讀取出來的鍵為 `black_ls/white_ls` 需轉成
    公用的 `black/white`"""
    result: Dict[str, Dict[str, Union[List[str], Dict[str, List[str]]]]] = {}
    for compo, _type in product(new, [ 'black', 'white' ]):
        if compo not in result: result[compo] = { _type: [] }
        if (s := f'{_type}_ls') in new[compo]:
            result[compo][_type] = diff_array(old[compo][s], new[compo][s])
    return result

def logfilter_diff_powercycle(old: Dict[str, Any], new: Dict[str, Any]
    ) -> Dict[str, Dict[str, Dict[str, Union[List[str], Dict[str, List[str]]]]]]:
    """從 JSON 文件讀取出來的鍵為 `black_list/white_list` 需轉成
    公用的 `black/white`，並且需去掉不必要的 `escape_char` 鍵"""
    for e in [ old, new ]: e.pop('escape_char', None)
    result = { k: {} for k in new }
    for cust in new:
        for compo, _type in product(new[cust], [ 'black', 'white' ]):
            result[cust][compo] = (
                { **result[cust][compo], _type: [] } if compo in result[cust] else { _type: [] }
            )
            if (s := f'{_type}_list') in new[cust][compo]:
                result[cust][compo][_type] = diff_array(old[cust][compo][s], new[cust][compo][s])
    return result

def logfilter_diff_filter(_type: str, old: Dict[str, Any], new: Dict[str, Any]
    ) -> Dict[str, Any]:
    """Difference black/white list between old and new, and
    then creating the data which is different for recording
    history and mail notification.

    可使用接口 `/api/v1/logfilter/diff` 進行數據較驗
    - ``SIT-LogFilter``腳本
        - origin: d358d252b36752af8c5dad0bce60eba5145289b8
        - latest: a3948448065ed6ed67d3454ed55e01f9e1c2604a
    - ``SIT-Power-CycleTest``腳本
        - origin: 90f8bb7c68358bd70b913ab0f4b743c9ce60ac59
        - latest: c9d0f2fc230dab27d22f68a90aca6c0ca4e98b8c

    Args
    -------
    - _type: (str) : 比較腳本類型
    - old  : (list): 來源文件中獲取的 `JSON` 數據
    - new  : (list): 最新文件中獲取的 `JSON` 數據

    Attention
    -------
        指定類型為 ``powercycle`` 需先將鍵 `escape_char` 刪除
        後才能比較差異

    Returns
    -------
        dict: 返回經差異比較後的字典
    """
    return (
        logfilter_diff_logfilter(old, new) if _type == 'logfilter'
        else logfilter_diff_powercycle(old, new)
    )

def logfilter_diff_data_convert(data: Dict[str, Union[dict, List[str]]], _type: str
    ) -> Dict[str, Any]:
    """除了 ``SIT-Power-CycleTest`` 黑白名單數據結構較不同，需將其
    轉換為與其它相同格式的數據"""
    return (
        { f'{i}-{j}': data[i][j] for i in data for j in data[i] }
        if _type == 'powercycle' else data
    )

def logfilter_diff_filter_email(data: Dict[str, Any]) -> Dict[str, Any]:
    """Refactoring differences data that groupby black/white list,
    This is for Email notification."""
    latest = logfilter_diff_data_convert(data.get('differences'), data.get('type'))
    refactor: Dict[str, Dict[str, Dict[str, List[str]]]] = { "black": {}, "white": {} }
    # makes main key is black/white, sub key is the type of list
    # using :class:`~itertools.product` to get all combinations
    for compo, _type, diff in product(latest, refactor, [ 'add', 'del' ]):
        if _type not in latest[compo]: continue
        if not isinstance(latest[compo][_type], dict): continue
        if not latest[compo][_type][diff]: continue
        if compo not in refactor[_type]:
            refactor[_type][compo] = {}
        refactor[_type][compo] |= { diff: latest[compo][_type][diff] }
    return refactor

async def logfilter_update_eamil(request: Type[Request], data: Dict[str, Any]
    ) -> Dict[str, Union[str, int]]:
    msg = EmailManager.schema(
        f'Black/White List Update - {data.get("project_name")} [v{data.get("latest_version")}]',
        EmailManager.group_receiver().recipients,
        EmailManager.group_receiver().cc,
        postman.get_header_by_priority('P1')
    )
    diff = { **data, "differences": logfilter_diff_filter_email(data) }
    msg = EmailManager.render(msg, 'logfilter-update.html', {
        "request"      : request,
        "ares_endpoint": ARES_ENDPOINT,
        "data"         : diff
    })
    mail = FastMail(postman.configure(request.base_url))
    try:
        await mail.send_message(msg)
        return { "message": "success", "status_code": 200 }
    except Exception as err:
        return { "message": str(err), "status_code": 422 }

async def logfilter_update_background(
    request: Type[Request], project: Type[Project], body: FilterBody) -> None:
    date = datetime_data()
    readme = getReadme(project)
    version = search_readme(readme, '## Version')
    origin_version = sub(r'[^(\d+\.){2}\d+]', '', version)
    latest_version = version_increment(origin_version)
    readme_updated = readme_update_version(readme, f'`Rev: {latest_version}`')
    commit_message = commit_message_template(project, latest_version, [
        f'1.Updated black/white list by {body.author} in ARES G2.',
        f'2.Comment: {body.comment}\n'
    ])
    raw_content = project.files.raw(file_path=body.file_path, ref=body.ref)
    content_origin = loads(raw_content.decode())
    content_update = body.content
    project.commits.create({
        "branch"        : body.ref,
        "commit_message": commit_message,
        "actions"       : [
            {
                "action"   : "update",
                "file_path": "README.md",
                "content"  : readme_updated
            },
            {
                "action"   : "update",
                "file_path": body.file_path,
                "content"  : dumps(body.content, indent=4)
            }
        ]
    })
    diff = logfilter_diff_filter(body.type, content_origin, content_update)
    history = {
        "type"          : body.type,
        "author"        : body.author,
        "readme"        : readme_updated,
        "content"       : content_update,
        "comment"       : body.comment,
        "project_id"    : body.project_id,
        "project_name"  : project.name,
        "project_url"   : project.web_url,
        "origin_version": origin_version,
        "latest_version": latest_version,
        "commit_message": commit_message,
        "datetime"      : date.get('dt'),
        "timestamp"     : date.get('ts'),
        "differences"   : diff
    }
    stringify = str(history) if body.type == 'logfilter' else dumps(history)
    with RedisContextManager() as r:
        r.hset(asdict(LogFilterDB()).get(body.type), latest_version, stringify)
    await logfilter_update_eamil(request, history)

@router.get('/api/v1/logfilter/file/content', tags=['Log Filter'])
@catch_gitlab_router
async def get_script_file_content(
    project_id: Annotated[int, QUERY_SCRIPT_ID] = QUERY_SCRIPT_ID,
    file_path : Annotated[str, QUERY_FILE_PATH] = QUERY_FILE_PATH,
    ref       : Annotated[str, QUERY_PROJECT_REF] = QUERY_PROJECT_REF,
    to_json   : Annotated[bool, QUERY_TOJSONIFY] = QUERY_TOJSONIFY) -> JSONResponse:
    project = validate_gitlab_project(project_id)
    raw_content = project.files.raw(file_path=file_path, ref=ref)
    content = validate_payloads(raw_content, dict) if to_json else raw_content.decode()
    resp = { "content": content, "name": project.name }
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/logfilter/file/content', tags=['Log Filter'])
@catch_gitlab_router
async def modify_content_of_script_file(body: FilterBase) -> JSONResponse:
    project = validate_gitlab_project(body.project_id)
    f = project.files.get(file_path=body.file_path, ref=body.ref)
    f.content = body.content
    f.save(branch=body.ref, commit_message='File Updated with FastAPI')
    return JSONResponse(status_code=200, content={ "content": body.content })

@router.get('/api/v1/logfilter/history/get', tags=['Log Filter'])
async def get_history_of_logfilter(
    page   : Annotated[int, QUERY_PAGE] = QUERY_PAGE,
    size   : Annotated[int, QUERY_SIZE] = QUERY_SIZE,
    keyword: Annotated[str, QUERY_KEYW] = QUERY_KEYW,
    type   : Annotated[str, QUERY_TYPE] = QUERY_TYPE) -> JSONResponse:
    with RedisContextManager(decode_responses=True) as r:
        keys = r.hkeys(name := asdict(LogFilterDB()).get(type))
        histories = sortby_key(
            [ json_parse(r.hget(name, k)) for k in keys ], key='datetime', reverse=True)
    resp = pagination(keyword, 'latest_version', page, size, histories)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/logfilter/diff', tags=['Log Filter'])
@catch_gitlab_router
async def get_logfilter_difference(
    origin: Annotated[str, QUERY_PROJECT_REF] = QUERY_PROJECT_REF,
    latest: Annotated[str, QUERY_PROJECT_REF] = QUERY_PROJECT_REF,
    type  : Annotated[str, QUERY_TYPE] = QUERY_TYPE) -> JSONResponse:
    map_dict = asdict(FilterMap()).get(type)
    project = getProject(map_dict["id"])
    raw_content = project.files.raw(file_path=map_dict["path"], ref=origin)
    content_origin = loads(raw_content.decode())
    raw_content = project.files.raw(file_path=map_dict["path"], ref=latest)
    content_update = loads(raw_content.decode())
    diff = logfilter_diff_filter(type, content_origin, content_update)
    resp = logfilter_diff_filter_email({ "differences": diff, "type": type })
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/logfilter/update', tags=['Log Filter'])
async def update_logfilter_list(
    bg_tasks: BackgroundTasks, request: Request, body: FilterBody) -> JSONResponse:
    project = validate_gitlab_project(body.project_id)
    valid, status = check_pipeline_running_status(project)
    if not valid:
        raise HTTPException(status_code=417, detail=status)
    bg_tasks.add_task(logfilter_update_background, request, project, body)
    resp = { "result": { **body.dict(), "project": project._attrs } }
    return JSONResponse(status_code=200, content=resp)
