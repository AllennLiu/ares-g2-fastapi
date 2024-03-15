#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.gitlabs import getReadme
from library.mailer import EmailManager
from library.moment import datetime_data
from library.config import url_to_ares, ARES_ENDPOINT
from library.readme import markdown, readme_release, MARKDOWN_EXTENSTIONS
from library.iteration import find, diff_array, sortby_key, pagination
from library.cacher import RedisContextManager, get_script_customers, get_customers_by_name
from library.helpers import safety_rmtree, version_increment
from library.schemas import (Schedules, Reschedule, TeRotate, Mission, AutomationDB, RedisDB, MissionDB, MissionInfo,
    MISSION_DEL_LIST)
from library.params import (json_parse, validate_gitlab_project, validate_payloads,
    QUERY_SCRIPT, QUERY_MISSION_TYPE, QUERY_FORCE, QUERY_MISSION_ORDER, QUERY_PAGE, QUERY_SIZE, QUERY_KEYW,
    FORM_SCRIPT, FORM_PAYLOADS, FILE_SINGLE)

from re import sub
from json import dumps
from uuid import uuid4
from os import makedirs
from copy import deepcopy
from pydantic import BaseModel
from aiofiles import open as aopen
from markdownify import markdownify
from starlette.responses import JSONResponse
from os.path import join, dirname, basename, isdir
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Annotated, Optional, Union, Iterable
from fastapi import APIRouter, HTTPException, Request, UploadFile, BackgroundTasks, Form

MOUNT_PATH_FILE_STORAGE = '/mnt/storage'
MOUNT_PATH_SRC_FILE_STORAGE = join(MOUNT_PATH_FILE_STORAGE, RedisDB.source)
FORM_LISTED = Form(False, description='Listing `Name`')

router = APIRouter()
postman = EmailManager()

@dataclass
class TagInfo:
    tag_name : str = '0.0.1'
    ref      : str = 'master'
    message  : str = 'release version 0.0.1'

@dataclass(init=False)
class HistoryInfo:
    script_version : str = '0.0.1'
    modified_date  : str = datetime_data()["dt"]
    history        : Dict[str, dict] = field(default_factory=lambda: {})

    def __init__(self, **kwargs: Any) -> None:
        names = set([ f.name for f in fields(self) ])
        for k in kwargs:
            if k in names:
                setattr(self, k, kwargs[k])

class HtmlContent(BaseModel):
    html: Optional[str] = '<p>None</p>'

class History(BaseModel):
    author   : str
    phase    : Optional[str] = 'create'
    progress : Optional[int] = 0
    comment  : Optional[str] = ''

class ChangeList(History):
    datetime : Optional[str] = datetime_data()["dt"]

class Coverage(BaseModel):
    project  : Optional[str] = ''
    platform : Optional[str] = ''

class TesterInfo(Coverage):
    name       : Optional[str] = ''
    customer   : Optional[str] = ''
    reports    : Optional[str] = ''
    validation : Optional[str] = 'False'
    result     : Optional[str] = ''
    datetime   : Optional[str] = ''

def mission_url_markup(request: Request = None, path: str = '') -> str:
    if not path:
        return ''
    route = request.base_url if request else f'{ARES_ENDPOINT}/'
    link = sub(r'^\/', '', sub(r'.*.\/mnt', 'mnt', path))
    return f'{route}api/v1/collection/download/{link}'

def mission_history_sort(data: Dict[str, Union[str, int]], reverse: bool = True
    ) -> List[Dict[str, Union[str, int]]]:
    items = [ { **data[k], "datetime": k } for k in data ]
    return sortby_key(items, 'datetime', reverse)

def mission_search_all(db_names: Iterable[str]) -> List[str]:
    missions = set()
    with RedisContextManager(decode_responses=True) as r:
        for name in db_names:
            missions |= set(r.hkeys(name))
    return list(missions)

def mission_query(name: str = '', key: str = '', msg: str = 'Mission'
    ) -> Union[Dict[str, Any], HTTPException]:
    with RedisContextManager() as r:
        if data := r.hget(name, key):
            return json_parse(data)
    raise HTTPException(status_code=404, detail=f'{msg} Not Found')

def mission_source_cache_clean(mission: MissionInfo) -> None:
    with RedisContextManager(decode_responses=True) as r:
        for name in r.scan_iter(f'source-file-{mission.script_name}-*'):
            data = json_parse(r.hget(name, 'cache'))
            if folder := data.get('location') and mission.source_uuid not in name:
                if uuid := basename(folder) and uuid != RedisDB.source:
                    safety_rmtree(folder)
            r.delete(name)

def mission_tedata_assign(mission: MissionInfo, order: str) -> Dict[str, dict]:
    is_develop = mission.status == 'development'
    to_valid = Mission.map(mission.status, order)["status"] == 'validation'
    return {
        e: TesterInfo(**{
            **mission.te_data.get(e, {}),
            **(
                { "validation": "False" }
                if is_develop and to_valid
                and mission.te_data[e].get('result') != 'pass' else {}
            ),
            "name": e
        }).dict()
        for e in mission.te_name.split(';') if e.strip()
    }

def mission_status_update(mission: MissionInfo, order: str) -> Dict[str, Any]:
    data_items = mission.te_data.values()
    verified = [ e for e in data_items if e.get('validation') == 'True' ]
    invalid = find(lambda x: x.get('result') == 'fail', verified)
    if mission.status != 'validation':
        status = Mission.map(mission.status, order)
        if mission.phase == 'assess-reject':
            status["phase"] = 'create-again'
        return status
    if len(verified) == len(data_items):
        return Mission.map(mission.status, 'prev' if invalid else 'next')
    latest = sortby_key(data_items, 'datetime', True)[0].get('result')
    result = [ e for e in verified if e.get('name') == mission.author ]
    phase = f'validation-{result[0].get("result") if result else latest}'
    return { **Mission.map('validation', 'wait'), "phase": phase }

def mission_create_prerequisite(
    mission: MissionInfo, mod: bool = False, status: Dict[str, Any] = {}) -> MissionInfo:
    date = datetime_data()
    mission.customers = get_customers_by_name(mission.script_name, get_script_customers())
    mission.coverages = { e: Coverage().dict() for e in mission.customers }
    mission.link = url_to_ares(mission.script_name)
    mission.modified_date = date.get('dt')
    history = { "author": mission.author, "comment": mission.description }
    if mod:
        status = { **Mission.map('create', 'next'), "phase": "create-again" }
        status["current"] = mission.dict().get(status.get('current', ''), '')
        status["comment"] = mission.comment
    mission.history[date["string"]] = History(**history | status).dict()
    return MissionInfo(**mission.dict() | status)

def mission_db_append(name: str, key: str, data: Dict[str, Any]) -> None:
    with RedisContextManager() as r:
        query = r.hget(name, key)
        stringify = str(data | json_parse(query or data))
        r.hset(name, key, stringify)

def mission_change_history_save(mission: MissionInfo) -> None:
    history = { mission.modified_date.replace('T', '-'): mission.dict() }
    mission_db_append(RedisDB.history, mission.script_name, history)
    changelist = []
    for k in mission.history:
        if 'create' in (raw := mission.history[k]).get('phase', ''):
            changelist.append(raw | { "datetime": k.replace(' ', 'T') })
    if changes := sortby_key(changelist, 'datetime', True):
        change = { mission.script_version: ChangeList(**changes[0]).dict() }
        mission_db_append(RedisDB.changelist, mission.script_name, change)

async def mission_file_save(file: UploadFile, parent: str, path: str) -> None:
    if not isdir(parent): makedirs(parent)
    async with aopen(path, 'wb') as f:
        content = await file.read()
        await f.write(content)

async def mission_upload_source_background(file: UploadFile, name: str,
    parent: str, path: str, query: Dict[str, str]) -> None:
    await mission_file_save(file, parent, path)
    with RedisContextManager() as r:
        key = f'source-file-{name}-{basename(parent)}'
        r.hset(key, 'cache', dumps({ "location": parent, "data": query }))
        r.expire(key, 3600)
        source_data = r.hget(RedisDB.source, name)
        data = json_parse(source_data or {}) | query
        r.hset(RedisDB.source, name, dumps(data))

async def mission_upload_report_background(file: UploadFile,
    data: Dict[str, Any], query: Dict[str, Any], db_name: str, path: str) -> None:
    await mission_file_save(file, dirname(path), path)
    query["te_data"][data["name"]] = TesterInfo(**data).dict()
    with RedisContextManager() as r:
        r.hset(db_name, data.get('script_name'), str(query))

def mission_delete_background(mission: MissionInfo, type: str, force: bool) -> None:
    version = version_increment(mission.script_version, True, False)
    mission_dir = join(MOUNT_PATH_FILE_STORAGE, asdict(MissionDB()).get(type), mission.script_name)
    safety_rmtree(mission_dir if type == 'create' or force else '')
    with RedisContextManager() as r:
        if query_source := r.hget(RedisDB.source, mission.script_name):
            regexp = '^api/v1/collection/download|\s'
            sources = json_parse(query_source)
            items = { k: dirname(sub(regexp, '', sources[k])) for k in sources if sources[k] }
            if type == 'create' or force:
                dirs = items.values()
                r.hdel(RedisDB.source, mission.script_name)
            elif type == 'update':
                dirs = [ items[k] for k in items if k == version ]
                data = { k: sources[k] for k in sources if k != version }
                r.hset(RedisDB.source, mission.script_name, dumps(data))
            _ = [ safety_rmtree(e) for e in dirs if basename(e) != RedisDB.source ]
    project = validate_gitlab_project(mission.script_name, False)
    if (type == 'create' or force) and project is not None:
        project.delete()

def mission_create_background(mission: MissionInfo) -> None:
    with RedisContextManager() as r:
        r.hset(MissionDB.create, mission.script_name, str(mission.dict()))
    mission_source_cache_clean(mission)

async def mission_reschedule_email(
    request: Request, sched: Reschedule, origin: Dict[str, Any]) -> None:
    subject = f'Script Mission Postpone - {sched.name} [Re-scheduled]'
    receiver = Mission.associates(MissionInfo(**origin), [ sched.submitter ])
    msg = EmailManager.schema(
        subject,
        EmailManager.mailize(receiver.recipients),
        EmailManager.mailize(receiver.cc)
    )
    msg = EmailManager.render(msg, 'mission-reschedule.html', {
        "request"      : request,
        "ares_endpoint": ARES_ENDPOINT,
        "subject"      : subject,
        "mission"      : sched.dict(),
        "old_schedules": Schedules(**origin["schedules"]).dict()
    })
    await EmailManager.safety_send(msg, postman.configure(request.base_url))

async def mission_rotate_email(
    request: Request, body: TeRotate, origin: Dict[str, Any]) -> None:
    subject = f'Script Mission Rotation - {body.name} [Tester-rotate]'
    origin_te_names = origin.get('te_name', '').split(';')
    diff = diff_array(origin_te_names, body.te_name.split(';'))
    extra = [ *origin.get('te_name', '').split(';'), body.submitter ]
    receiver = Mission.associates(MissionInfo(**origin), extra)
    msg = EmailManager.schema(
        subject,
        EmailManager.mailize(receiver.recipients),
        EmailManager.mailize(receiver.cc)
    )
    msg = EmailManager.render(msg, 'mission-rotate.html', {
        "request"      : request,
        "ares_endpoint": ARES_ENDPOINT,
        "subject"      : subject,
        "mission"      : body.dict(),
        "old_te_names" : diff.get('del')
    })
    await EmailManager.safety_send(msg, postman.configure(request.base_url))

async def mission_notify_email(
    request: Request, mission: MissionInfo, type: str = 'create') -> None:
    tag = mission.phase.split('-')[-1] if 'validation-' in mission.phase else mission.status
    title = f'{mission.script_name} [{tag.capitalize()}]'
    context = {
        "request"      : request,
        "ares_endpoint": ARES_ENDPOINT,
        "type"         : type.capitalize(),
        "subject"      : f'Script Mission {type.capitalize()} - {title}',
        "mission"      : mission.dict()
    }
    receiver = Mission.rec(mission)
    msg = EmailManager.schema(
        context.get('subject', ''),
        EmailManager.mailize(receiver.recipients),
        EmailManager.mailize(receiver.cc),
        postman.get_header_by_priority(mission.priority)
    )
    msg = EmailManager.render(msg, 'mission-notify.html', context)
    await EmailManager.safety_send(msg, postman.configure(request.base_url))

async def mission_release_email(
    request: Request, mission: MissionInfo, readme: str) -> None:
    sender = 'gitlab@ipt-gitlab.ies.inventec'
    subject = f'{mission.script_name} Released [v{mission.script_version}]'
    msg = EmailManager.schema(
        subject,
        EmailManager.group_receiver().recipients,
        EmailManager.group_receiver().cc,
        postman.get_header_by_priority('P1')
    )
    msg = EmailManager.render(msg, 'mission-release.html', {
        "request"      : request,
        "ares_endpoint": ARES_ENDPOINT,
        "readme"       : readme
    })
    config = postman.configure(request.base_url, sender)
    await EmailManager.safety_send(msg, config)

async def mission_release_background(
    request: Request, mission: MissionInfo, type: str) -> Union[None, bool]:
    if mission.status != 'release':
        return True
    mission.link = url_to_ares(mission.script_name, 'update')
    with RedisContextManager() as r:
        if type == 'create':
            stringify = str(mission.dict())
            r.hset(MissionDB.update, mission.script_name, stringify)
            r.hdel(MissionDB.create, mission.script_name)
        mission_change_history_save(mission)
    download = (f'{request.base_url}api/v1/scripts/download/redirect?' +
                f'script_name={mission.script_name}&' +
                f'archive_url={mission.repository}')
    version = mission.script_version
    project = validate_gitlab_project(mission.script_name)
    comment = mission.history[sorted(mission.history)[0]].get('comment', '')
    readme = readme_release(getReadme(project), download, comment.splitlines())
    _ = [ e.delete() for e in project.tags.list() if e.name == version ]
    message = f'release version {version}'
    project.tags.create(asdict(TagInfo(tag_name=version, message=message)))
    await mission_release_email(request, mission, readme)

@router.get('/api/v1/mission/customers', tags=['Mission'])
async def list_customer_by_mission() -> JSONResponse:
    return JSONResponse(status_code=200, content={ "list": get_script_customers() })

@router.get('/api/v1/mission/list', tags=['Mission'])
async def get_mission_list(
    page   : Annotated[int, QUERY_PAGE] = QUERY_PAGE,
    size   : Annotated[int, QUERY_SIZE] = QUERY_SIZE,
    keyword: Annotated[str, QUERY_KEYW] = QUERY_KEYW,
    type   : Annotated[str, QUERY_MISSION_TYPE] = QUERY_MISSION_TYPE) -> JSONResponse:
    items = []
    with RedisContextManager(decode_responses=True) as r:
        for k in r.hkeys(name := asdict(MissionDB()).get(type)):
            raw = json_parse(r.hget(name, k))
            is_create = type == 'create' and raw.get('status') != 'release'
            if is_create or type == 'update':
                items.append(raw)
    missions = sortby_key(items, 'modified_date', True)
    resp = pagination(keyword, 'script_name', page, size, missions)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/mission/get', tags=['Mission'])
async def get_mission_data(
    name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT,
    type: Annotated[str, QUERY_MISSION_TYPE] = QUERY_MISSION_TYPE) -> JSONResponse:
    mission = mission_query(asdict(MissionDB()).get(type), name)
    html = markdown(mission.get('description', ''), extensions=MARKDOWN_EXTENSTIONS)
    resp = { "mission": { **mission, "editor": html } }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/mission/changelist/get', tags=['Mission'])
async def get_changelist_by_mission(
    name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    query = mission_query(RedisDB.changelist, name, 'Changelist')
    with RedisContextManager() as r:
        sources = json_parse(r.hget(RedisDB.source, name) or {})
    items = [
        {
            **ChangeList(**query[k]).dict(),
            "tag"   : k,
            "source": mission_url_markup(path=sources.get(k, ''))
        }
        for k in query
    ]
    resp = { "list": sortby_key(items, 'datetime', True) }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/mission/history/list', tags=['Mission'])
async def list_history_by_mission(
    name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    query = mission_query(RedisDB.history, name, 'History')
    items = [
        {
            **asdict(HistoryInfo(**e)),
            "history": mission_history_sort(e.get('history', {}))
        }
        for e in query.values()
    ]
    resp = { "list": sortby_key(items, 'modified_date', True) }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/mission/history/get', tags=['Mission'])
async def get_history_by_mission(
    name: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT,
    type: Annotated[str, QUERY_MISSION_TYPE] = QUERY_MISSION_TYPE) -> JSONResponse:
    data = mission_query(asdict(MissionDB()).get(type), name)
    if not data.get('history'):
        raise HTTPException(status_code=404, detail='History Not Found')
    history_sorted = mission_history_sort(data["history"])
    resp = { **asdict(HistoryInfo(**data)), "history" : history_sorted }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/mission/get/source', tags=['Mission'])
async def get_source_by_mission(
    page   : Annotated[int, QUERY_PAGE] = QUERY_PAGE,
    size   : Annotated[int, QUERY_SIZE] = QUERY_SIZE,
    keyword: Annotated[str, QUERY_KEYW] = QUERY_KEYW,
    name   : Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    query = mission_query(RedisDB.source, name, 'Source')
    s = [ { "version": k, "link": mission_url_markup(path=query[k]) } for k in query ]
    resp = pagination(keyword, 'version', page, size, s)
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/mission/validate', tags=['Mission'])
async def validate_mission_name(
    name  : Annotated[str, FORM_SCRIPT] = FORM_SCRIPT,
    listed: Annotated[bool, FORM_LISTED] = FORM_LISTED) -> JSONResponse:
    resp = { "valid": name not in (ls := mission_search_all(asdict(MissionDB()).values())) }
    if listed: resp |= { "list": ls }
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/mission/markdownify', tags=['Mission'])
async def convert_html_to_markdown(h: HtmlContent) -> JSONResponse:
    return JSONResponse(status_code=200, content={ "md": markdownify(h.html) })

@router.post('/api/v1/mission/upload/source', tags=['Mission'])
async def upload_source_file(bg_task: BackgroundTasks,
    file    : Annotated[UploadFile, FILE_SINGLE] = FILE_SINGLE,
    payloads: Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS) -> JSONResponse:
    uuid = str(uuid4())
    data = validate_payloads(payloads, dict)
    release_version = version_increment(data.get('version', '0.0.1'), release=True)
    location = join(MOUNT_PATH_SRC_FILE_STORAGE, uuid)
    file_path = join(location, file.filename)
    query = { release_version: f'api/v1/collection/download{file_path}' }
    bg_task.add_task(
        mission_upload_source_background,
        file, data.get('name', ''), location, file_path, query
    )
    resp = { "result": { **query, "uuid": uuid } }
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/mission/upload/report', tags=['Mission'])
async def upload_report_file(bg_task: BackgroundTasks, request: Request,
    file    : Annotated[UploadFile, FILE_SINGLE] = FILE_SINGLE,
    payloads: Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS) -> JSONResponse:
    data = validate_payloads(payloads, dict)
    db_name = asdict(MissionDB()).get(data.get('type'))
    query = mission_query(db_name, data.get('script_name'))
    if not query.get('te_data', {}).get(tester := data.get('name')):
        raise HTTPException(status_code=404, detail=f'{tester} Not Found')
    root_path = join(MOUNT_PATH_FILE_STORAGE, db_name, data.get('script_name'))
    file_path = join(root_path, tester, file.filename)
    updated = {
        **query["te_data"][tester], **data,
        "reports" : mission_url_markup(request, file_path),
        "datetime": sub(r'[^\d]', '', datetime_data()["string"])
    }
    bg_task.add_task(
        mission_upload_report_background,
        file, updated, query, db_name, file_path
    )
    resp = { "result": { **updated, "path": file_path } }
    return JSONResponse(status_code=200, content=resp)

@router.put('/api/v1/mission/reschedule', tags=['Mission'])
async def reschedule_mission(
    bg_task: BackgroundTasks, request: Request, sched: Reschedule) -> JSONResponse:
    origin = mission_query(asdict(MissionDB()).get(sched.type), sched.name)
    mission = MissionInfo(**origin | sched.dict())
    history = History(
        author   = sched.submitter,
        comment  = sched.comment,
        phase    = 're-scheduled',
        progress = mission.progress
    )
    mission.history[datetime_data()["string"]] = history.dict()
    with RedisContextManager() as r:
        r.hset(asdict(MissionDB()).get(sched.type), sched.name, str(mission.dict()))
    bg_task.add_task(mission_reschedule_email, request, sched, origin)
    return JSONResponse(status_code=200, content={ "result": sched.dict() })

@router.put('/api/v1/mission/rotate', tags=['Mission'])
async def rotate_mission(
    bg_task: BackgroundTasks, request: Request, body: TeRotate) -> JSONResponse:
    origin = mission_query(asdict(MissionDB()).get(body.type), body.name)
    mission = MissionInfo(**origin | body.dict())
    history = History(
        author   = body.submitter,
        comment  = body.comment,
        phase    = 'tester-rotate',
        progress = mission.progress
    )
    mission.history[datetime_data()["string"]] = history.dict()
    mission.te_data = mission_tedata_assign(mission, 'wait')
    with RedisContextManager() as r:
        r.hset(asdict(MissionDB()).get(body.type), body.name, str(mission.dict()))
    bg_task.add_task(mission_rotate_email, request, body, origin)
    return JSONResponse(status_code=200, content={ "result": body.dict() })

@router.delete('/api/v1/mission/delete', tags=['Mission'])
async def delete_mission(bg_task: BackgroundTasks,
    name : Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT,
    type : Annotated[str, QUERY_MISSION_TYPE] = QUERY_MISSION_TYPE,
    force: Annotated[bool, QUERY_FORCE] = QUERY_FORCE) -> JSONResponse:
    mission = MissionInfo(**mission_query(asdict(MissionDB()).get(type), name))
    with RedisContextManager() as r:
        if type == 'create' or force:
            for e in MISSION_DEL_LIST: r.hdel(e, name)
        elif type == 'update':
            if query := r.hget(RedisDB.backup, name):
                r.hset(MissionDB.update, name, str(json_parse(query)))
                r.hdel(RedisDB.backup, name)
    bg_task.add_task(mission_delete_background, mission, type, force)
    return JSONResponse(status_code=200, content={ "result": "Successfully" })

@router.post('/api/v1/mission/create', tags=['Mission'])
async def create_a_new_mission(
    bg_task: BackgroundTasks, request: Request, mission: MissionInfo) -> JSONResponse:
    mission = mission_create_prerequisite(mission)
    bg_task.add_task(mission_create_background, mission)
    bg_task.add_task(mission_notify_email, request, mission)
    return JSONResponse(status_code=200, content={ "result": mission.dict() })

@router.put('/api/v1/mission/create', tags=['Mission'])
async def modify_new_mission(bg_task: BackgroundTasks, request: Request, mission: MissionInfo,
    origin: Annotated[str, QUERY_SCRIPT] = QUERY_SCRIPT) -> JSONResponse:
    mission_query(MissionDB.create, origin)
    mission = mission_create_prerequisite(mission, True)
    with RedisContextManager() as r:
        r.hset(MissionDB.create, mission.script_name, str(mission.dict()))
        if origin != mission.script_name:
            r.hdel(MissionDB.create, origin)
            r.hdel(AutomationDB.analysis, origin)
    bg_task.add_task(mission_notify_email, request, mission)
    return JSONResponse(status_code=200, content={ "result": mission.dict() })

@router.post('/api/v1/mission/update', tags=['Mission'])
async def update_mission(bg_task: BackgroundTasks, request: Request, mission: MissionInfo,
    type : Annotated[str, QUERY_MISSION_TYPE] = QUERY_MISSION_TYPE,
    order: Annotated[str, QUERY_MISSION_ORDER] = QUERY_MISSION_ORDER) -> JSONResponse:
    date = datetime_data()
    backup = deepcopy(mission.dict())
    origin = mission_query(asdict(MissionDB()).get(type), mission.script_name)
    update_init = type == 'update' and backup.get('status') == 'release'
    if order == 'next':
        mission.script_version = Mission.rev(mission.status, mission.script_version)
    mission.te_data = mission_tedata_assign(mission, order)
    status = mission_status_update(mission, order)
    history = { "author": mission.author, "comment": mission.comment }
    mission.history = {
        **({} if update_init else mission.history),
        date["string"]: History(**history, **status).dict()
    }
    mission.schedules = Schedules(**mission.schedules).dict()
    mission.link = url_to_ares(mission.script_name, type)
    mission.modified_date = date.get('dt')
    current = backup.get(status.get('current', ''), '')
    data = origin | mission.dict() | status | { "current": current }
    mission = MissionInfo(**data)
    with RedisContextManager() as r:
        if update_init:
            r.hset(RedisDB.backup, mission.script_name, dumps(origin))
            bg_task.add_task(mission_source_cache_clean, mission)
        r.hset(asdict(MissionDB()).get(type), mission.script_name, str(data))
    bg_task.add_task(mission_notify_email, request, mission, type)
    bg_task.add_task(mission_release_background, request, mission, type)
    return JSONResponse(status_code=200, content={ "result": data })
