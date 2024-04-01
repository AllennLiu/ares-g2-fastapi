#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.moment import datetime_data
from library.mongodb import ConnectMongo
from library.cacher import RedisContextManager
from library.gitlabs import getReadme, Project
from library.iteration import sortby_key, pagination
from library.readme import readme_decorator, get_ver_by_readme
from library.params import (json_parse, validate_gitlab_project,
    QUERY_SCRIPT, QUERY_PAGE, QUERY_SIZE, QUERY_KEYW)
from library.schemas import (Analyzer, AutomationDB, RedisDB, MissionDB,
    Maintainer, FilterMap, ScriptConfig, QUATERS)

from re import search
from io import BytesIO
from json import dumps
from os import PathLike
from time import strftime
from pydantic import BaseModel
from os.path import join, splitext
from zipfile import ZipFile, ZIP_DEFLATED
from dataclasses import dataclass, asdict
from fastapi import APIRouter, HTTPException, Path
from typing import Any, Dict, List, Annotated, Optional, Type, Union
from starlette.responses import JSONResponse, HTMLResponse, StreamingResponse

PATH_NAME = Path(..., description='Require a `Script Name`')
PATH_COMMIT_SHA = Path(..., description='Require a `Commit SHA` *(GitLab)*')

router = APIRouter()

@dataclass
class DownloadCounter:
    name      : str = ''
    count     : int = 1
    timestamp : str = strftime('%s')
    datetime  : str = strftime('%Y-%m-%d %T')
    year      : str = strftime('%Y')
    season    : str = QUATERS[strftime('%m')]

@dataclass
class DownloadContent:
    path    : Union[str, PathLike] = ''
    content : bytes = None

class ScriptItem(BaseModel):
    items: Optional[List[str]] = []

class ScriptVariable(BaseModel):
    script_name : str
    variables   : Optional[List[str]] = []

class ScriptConfigure(Maintainer):
    script_name : str
    settings    : Optional[List[dict]] = []

def scripts_query(name: str = MissionDB.gitlab, key: str = '') -> Dict[str, Any]:
    """各接口通用來依照 ``key`` 或 ``name`` 獲取 `Redis` 數據庫的數據"""
    with RedisContextManager() as r:
        data = r.hget(name, key)
    if not data:
        raise HTTPException(status_code=404, detail='Script Not Found')
    return json_parse(data)

def scripts_list_append(name: str, key: str, items: List[str]) -> None:
    with RedisContextManager() as r:
        data = list({ *scripts_query(name, key), *items })
        r.hset(name, key, dumps(data))

def scripts_download_counter(script_name: str) -> None:
    """保存當前時間(季度) 下載信息至 `Mongodb`，用以計算腳本下載次數"""
    datetimes = strftime('%Y-%m-%d %T %s').split()
    year = datetimes[0].split('-')[0]
    season = QUATERS.get(datetimes[0].split('-')[1])
    data = asdict(DownloadCounter(**{
        "name"     : script_name,
        "timestamp": datetimes[-1],
        "datetime" : ' '.join(datetimes[:2]),
        "year"     : year,
        "season"   : season
    }))
    with ConnectMongo(database='flask') as m:
        m.insertCollection(f'scripts_counter_{year}_{season}', data, uuid=True)

def scripts_update_filter_list(project: Type[Project]) -> Union[DownloadContent, None]:
    """檢查是否為黑白名單項目，如果是則返回 :class:`~DownloadContent`
    下載對象 (黑白名單文件與 `binary` 二進制內容)"""
    map_dict = { e["id"]: e["path"] for e in asdict(FilterMap()).values() }
    if project.id not in map_dict: return
    file_path = map_dict.get(project.id)
    raw_content = project.files.raw(file_path=file_path, ref='master')
    return DownloadContent(path=file_path, content=raw_content)

def scripts_archive_rename(project: Type[Project], binary: bytes, file: str) -> BytesIO:
    """通過讀取到的壓縮包 `binary` 修改裡面的目錄名稱並重新打包，最終返回
    其內存 `Buffer Read`\n\n
    如發現項目含有黑白名單文件，則替換該文件為當前 ``master`` 分支的內容\n
    (用來確保每次黑白名單都是最新的，防止用戶使用舊版本日誌分析問題)
    """
    buffer_read = BytesIO()
    with ZipFile(BytesIO(binary)) as src:
        with ZipFile(buffer_read, 'w', ZIP_DEFLATED) as dst:
            for e in src.filelist:
                root = e.filename.split('/')[0]
                path = e.filename.replace(root, splitext(file)[0])
                if _override := scripts_update_filter_list(project):
                    if join(splitext(file)[0], _override.path) == path:
                        dst.writestr(path, _override.content)
                        continue
                dst.writestr(path, src.read(e.filename))
    buffer_read.seek(0)
    return buffer_read

def scripts_download_stream(
    project: Type[Project], file: str, sha: str = 'master') -> StreamingResponse:
    """紀錄下載次數重新命名壓縮包內目錄名稱，最後返回 `http stream`"""
    scripts_download_counter(project.name)
    binary = project.repository_archive(format='zip', sha=sha)
    buffer = scripts_archive_rename(project, binary, file)
    resp = StreamingResponse(buffer, media_type='application/zip')
    resp.headers["Content-Disposition"] = f"attachment; filename={file}; filename*=utf-8''{file}"
    return resp

@router.get('/api/v1/scripts/get', tags=['Scripts'])
async def get_data_by_script_project(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    resp = { "script": scripts_query(key=script_name) }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/scripts/list', tags=['Scripts'])
async def listed_data_by_script_project(
    page   : Annotated[int, QUERY_PAGE] = QUERY_PAGE,
    size   : Annotated[int, QUERY_SIZE] = QUERY_SIZE,
    keyword: Annotated[str, QUERY_KEYW] = QUERY_KEYW) -> JSONResponse:
    with RedisContextManager(decode_responses=True) as r:
        keys = r.hkeys(name := MissionDB.gitlab)
        items = [ json_parse(r.hget(name, k)) for k in keys ]
    scripts = sortby_key(items, 'modified_date', True)
    resp = pagination(keyword, 'script_name', page, size, scripts)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/scripts/download/list', tags=['Scripts'])
async def listed_download_by_script(
    page   : Annotated[int, QUERY_PAGE] = QUERY_PAGE,
    size   : Annotated[int, QUERY_SIZE] = QUERY_SIZE,
    keyword: Annotated[str, QUERY_KEYW] = QUERY_KEYW,
    name   : Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    items = scripts_query(RedisDB.downloads, name)
    resp = pagination(keyword, 'version', page, size, items)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/scripts/download/{name}/{sha}',
            tags=['Scripts'], response_class=StreamingResponse)
def download_script_by_commit(
    name: Annotated[str, PATH_NAME] = PATH_NAME,
    sha : Annotated[str, PATH_COMMIT_SHA] = PATH_COMMIT_SHA) -> StreamingResponse:
    version = get_ver_by_readme(by_project=(project := validate_gitlab_project(name)), ref=sha)
    return scripts_download_stream(project, f'{name}-v{version}.zip', sha)

@router.get('/api/v1/scripts/download/redirect',
            tags=['Scripts'], response_class=StreamingResponse)
def provide_download(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> StreamingResponse:
    project = validate_gitlab_project(script_name)
    return scripts_download_stream(project, f'{script_name}-latest.zip')

@router.get('/api/v1/scripts/readme/info', tags=['Scripts'])
def get_readme_by_script_project(
    project_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> HTMLResponse:
    content = getReadme(validate_gitlab_project(project_name), ref='master')
    return HTMLResponse(status_code=200, content=content)

@router.get('/api/v1/scripts/readme/decorate', tags=['Scripts'])
async def decorate_readme_by_script_project(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    data = scripts_query(key=script_name)
    resp = { "html": readme_decorator(data.get('readme')) }
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/scripts/variable/modify', tags=['Scripts'])
async def modify_variable_of_script(body: ScriptVariable) -> JSONResponse:
    data = scripts_query(key=body.script_name)
    data["variables"] = sorted(set(filter(str.strip, body.variables)))
    with RedisContextManager() as r:
        r.hset(MissionDB.gitlab, body.script_name, str(data))
    resp = { "variables" : data["variables"] }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/scripts/automation/definitions',
            tags=['Scripts'], response_class=HTMLResponse)
async def script_automation_definitions(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> HTMLResponse:
    template = 'export ARES_AUTO_JOB_%s="%s"'
    data = scripts_query(AutomationDB.settings, script_name)
    path = str(data.get('counter_path')).strip()
    counter = path if not path or search('^\/', path) else f'${{EXE_PATH}}/{path}'
    data |= { "counter_path": counter }
    content = '\n'.join(
        template % ( k.upper(), ','.join(data[k]) if isinstance(data[k], list) else data[k] )
        for k in data if k not in Maintainer().dict()
    )
    return HTMLResponse(status_code=200, content=f'{content}\n')

@router.get('/api/v1/scripts/automation/settings', tags=['Scripts'])
async def get_script_automation_setting(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    query = scripts_query(AutomationDB.settings, script_name)
    extra = Maintainer(**query).dict()
    array = [ { "key": k, "value": query[k] } for k in query if k not in extra ]
    resp = { "settings": array, "models": list(ScriptConfig().dict()) }
    return JSONResponse(status_code=200, content=resp | extra)

@router.put('/api/v1/scripts/automation/settings', tags=['Scripts'])
async def modify_script_automation_setting(c: ScriptConfigure) -> JSONResponse:
    origin = scripts_query(AutomationDB.settings, c.script_name)
    resp = {
        **ScriptConfig(**origin).dict(),
        **{ e.get('key'): e.get('value') for e in c.settings },
        "maintainer": c.maintainer, "last_update": datetime_data()["dt"]
    }
    with RedisContextManager() as r:
        r.hset(AutomationDB.settings, c.script_name, dumps(resp))
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/scripts/log/analysis', tags=['Scripts'])
async def get_script_log_analysis_data(
    script_name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    data = Analyzer(**scripts_query(AutomationDB.analysis, script_name))
    return JSONResponse(status_code=200, content={ "analysis": data.dict() })

@router.put('/api/v1/scripts/log/analysis', tags=['Scripts'])
async def modify_script_log_analysis_data(analyzer: Analyzer) -> JSONResponse:
    origin = scripts_query(AutomationDB.analysis, analyzer.script_name)
    resp = { **origin, **analyzer.dict(), "last_update": datetime_data()["dt"] }
    with RedisContextManager() as r:
        r.hset(AutomationDB.analysis, analyzer.script_name, dumps(resp))
    return JSONResponse(status_code=200, content={ "analysis": resp })

@router.get('/api/v1/scripts/log/types', tags=['Scripts'])
async def listed_script_log_types() -> JSONResponse:
    resp = { "list": scripts_query(RedisDB.logtypes, 'logtypes') }
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/scripts/log/types', tags=['Scripts'])
async def update_script_log_types(logtypes: ScriptItem) -> JSONResponse:
    scripts_list_append(RedisDB.logtypes, 'logtypes', logtypes.items)
    return JSONResponse(status_code=200, content={ "message": "Successfully" })

@router.get('/api/v1/scripts/coverage/platforms', tags=['Scripts'])
async def listed_coverage_platforms() -> JSONResponse:
    resp = { "platforms": scripts_query(RedisDB.platforms, 'platforms') }
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/scripts/coverage/platforms', tags=['Scripts'])
async def update_coverage_platforms(platforms: ScriptItem) -> JSONResponse:
    scripts_list_append(RedisDB.platforms, 'platforms', platforms.items)
    return JSONResponse(status_code=200, content={ "message": "Successfully" })
