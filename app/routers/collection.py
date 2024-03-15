#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.excel import Excel
from library.readme import get_ver_by_readme
from library.cacher import RedisContextManager
from library.structure import freeze, HashedDict
from library.mailer import FastMail, EmailManager
from library.config import settings, ARES_ENDPOINT
from library.schemas import CollectionDB, Dropdown, DropdownItem
from library.params import json_parse, validate_payloads, QUERY_DATE_STRING, FORM_PAYLOADS, FILE_MULTIPLE
from library.helpers import safety_move, safety_remove, safety_rmtree, version_increment, read_file_chunks, BackendPrint

from uuid import uuid4
from time import strftime
from re import sub, search
from json import loads, dumps
from functools import lru_cache
from contextlib import suppress
from os import listdir, makedirs
from aiofiles import open as aopen
from collections import defaultdict
from ntpath import dirname as ntdirname
from ntpath import basename as ntbasename
from os.path import join, getsize, isdir, isfile
from typing import Any, Dict, List, Annotated, Optional, Union
from starlette.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, HttpUrl, FilePath, DirectoryPath
from fastapi import APIRouter, HTTPException, Request, UploadFile, BackgroundTasks, Query, Path

router = APIRouter()
postman = EmailManager()

MOUNT_PATH_DIR = '/mnt'
MOUNT_PATH_ROOT = '/mnt/External_Doc/Test_Tools/Script_Collect/Collection'
MOUNT_PATH_ROOT_REALPATH = sub(f'{MOUNT_PATH_DIR}/', '', MOUNT_PATH_ROOT)
MOUNT_PATH_FILE_STORAGE = '/mnt/storage/script-management-collections-requirements/tmp'

PATH_FILENAME = Path(..., description='Require `File Path` *(absolutely)*')
PATH_COLLECTION = Path(..., description=f'Require `Collection Path` *(root:{MOUNT_PATH_ROOT})*')
QUERY_EXCEL = Query('excel.xlsx', max_length=50, regex='.*.xlsx$')
QUERY_ROOT_PATH = Query(MOUNT_PATH_ROOT_REALPATH, description='**Collection** `Root Path`')

if settings.env != 'prod':
    MOUNT_PATH_FILE_STORAGE += '-test'

class TreeUpdate(BaseModel):
    root_path: Optional[str] = MOUNT_PATH_ROOT_REALPATH

class TreeNode(BaseModel):
    id          : int
    title       : str
    value       : Optional[str] = ''
    label       : Optional[str] = ''
    source      : Optional[str] = ''
    company     : Optional[str] = ''
    guide       : Optional[str] = ''
    update_time : Optional[str] = ''
    check_date  : Optional[str] = ''
    operation   : Optional[str] = ''
    author      : Optional[str] = ''
    remark      : Optional[str] = ''

@lru_cache
def collection_query_tree(path: str) -> Dict[str, Union[str, int, List[dict]]]:
    with RedisContextManager() as r:
        return loads(r.hget(CollectionDB.tree, ntbasename(path)) or '{}')

@lru_cache
def collection_treeview(
    path: Union[FilePath, DirectoryPath], api_url: HttpUrl, map_data: HashedDict
    ) -> Dict[str, Union[str, int, List[dict]]]:
    if search(regexp := r'SynologyDrive|Thumbs.db', path):
        return
    item = TreeNode(**{
        "id"   : uuid4().int >> 100,
        "value": (name := sub(r'.*\/Script_Collect\/Collection\/', '', path)),
        "title": ntbasename(path),
        "label": ntbasename(path),
        **(map_data[name] if map_data.get(name) else {})
    }).dict()
    if isdir(path):
        while True:
            item["children"]: List[str, Union[str, int, List[dict]]] = []
            with suppress(OSError):
                for file in listdir(path):
                    if search(regexp, file): continue
                    item["children"].append(
                        collection_treeview(join(path, file), api_url, map_data)
                    )
                break
    else:
        item["link"] = f'{api_url}api/v1/collection/download{path}'
    return item

def collection_tree_update(
    root_path: str = MOUNT_PATH_ROOT_REALPATH, request: Optional[Request] = None) -> Dict[str, str]:
    collection = ntbasename(root_path)
    with RedisContextManager(decode_responses=True) as r:
        map_data = freeze({
            k: json_parse(r.hget(CollectionDB.maps, k))
            for k in r.hkeys(CollectionDB.maps)
        })
    tmp_mount_point = join(MOUNT_PATH_DIR, root_path)
    data = collection_treeview(tmp_mount_point, str(request.base_url), map_data)
    with RedisContextManager() as r:
        r.hset(CollectionDB.tree, collection, dumps(data).encode('utf-8'))
    return { "message": "success" }

def collection_validate_requirements(payloads: str) -> List[dict]:
    requirements = validate_payloads(payloads)
    for req in requirements:
        if not req.get('gitlab'):
            raise HTTPException(status_code=422, detail='Invalid Requests Data')
    return requirements

def collection_apply_version(datetime: str) -> Dict[str, Any]:
    with RedisContextManager(decode_responses=True) as r:
        query = r.hkeys(CollectionDB.version)
        query.sort(reverse=True)
        version = query[0] if query else get_ver_by_readme(id=62)
        data = {
            "origin_version": version,
            "latest_version": (ver_plus := version_increment(version)),
            "datetime"      : datetime
        }
        r.hset(CollectionDB.version, ver_plus, dumps(data))
    return data

def collection_apply_history(items: List[dict], date: str) -> None:
    data = { (e["uuid"] if e.get('uuid') else str(uuid4())): e for e in items }
    with RedisContextManager() as r:
        r.hset(CollectionDB.history, date, str(data))

async def collection_apply_email(
    author: str, requirements: list, date: str, version: dict, request: Request) -> Dict[str, Any]:
    resp = { "message": "success", "status_code": 200 }
    try:
        msg = EmailManager.schema(
            'Collection Tools Update Notification',
            EmailManager.group_receiver().recipients,
            EmailManager.group_receiver().cc,
            postman.get_header_by_priority('P1')
        )
        msg = EmailManager.render(msg, 'collection-apply.html', {
            "request"      : request,
            "requirements" : requirements,
            "version"      : version,
            "author"       : loads(author),
            "datetime"     : date.replace('T', ' '),
            "ares_endpoint": ARES_ENDPOINT
        })
        mail = FastMail(postman.configure(request.base_url))
        await mail.send_message(msg)
    except Exception as err:
        resp = { "message": str(err), "status_code": 422 }
    return resp

def collection_operation_manager(requirements: list, date: str) -> tuple:
    operations, exceptions = [], []
    with RedisContextManager() as r:
        for e in requirements:
            try:
                file = e.get('file')
                gitlab = e.get('gitlab')
                if e.get('operation') == 'New':
                    r.hset(
                        CollectionDB.maps,
                        join(gitlab, file),
                        str(e | { "uuid": str(uuid4()), "modified_date": date })
                    )
                    source = join(MOUNT_PATH_FILE_STORAGE, file)
                    target = join(MOUNT_PATH_ROOT, gitlab, file)
                    operations.append(e | { "action": f"move({source}, {target})" })
                    safety_move(source, target)
                elif e.get('operation') == 'Delete':
                    r.hdel(CollectionDB.maps, gitlab)
                    target = join(MOUNT_PATH_ROOT, gitlab)
                    if isdir(target):
                        operations.append(e | { "action": f"rmtree({target})" })
                        safety_rmtree(target)
                    else:
                        operations.append(e | { "action": f"remove({target})" })
                        safety_remove(target)
                elif e.get('operation') == 'MoveTo':
                    query = json_parse(r.hget(CollectionDB.maps, file))
                    r.hdel(CollectionDB.maps, file)
                    r.hset(
                        CollectionDB.maps,
                        join(gitlab, ntbasename(file)),
                        str(query | e | { "file": ntbasename(file), "modified_date": date })
                    )
                    source = join(MOUNT_PATH_ROOT, file)
                    target = join(MOUNT_PATH_ROOT, gitlab, ntbasename(file))
                    operations.append(e | { "action": f"move({source}, {target})" })
                    safety_move(source, target)
                elif e.get('operation') == 'NewDir':
                    source = join(MOUNT_PATH_ROOT, gitlab)
                    target = join(source, ntbasename(file))
                    if isdir(source) and not isdir(target):
                        operations.append(e | { "action": f'makedirs({target})' })
                        makedirs(target)
                elif e.get('operation') == 'Update':
                    query = json_parse(r.hget(CollectionDB.maps, gitlab))
                    r.hset(
                        CollectionDB.maps,
                        gitlab,
                        str(query | e | { "gitlab": ntdirname(gitlab), "modified_date": date })
                    )
                    source = join(MOUNT_PATH_FILE_STORAGE, file)
                    target = join(MOUNT_PATH_ROOT, gitlab)
                    operations.append(e | { "action": f"move({source}, {target})" })
                    safety_move(source, target)

            except Exception as err:
                exceptions.append(e | { "error": str(err) })
    return ( operations, exceptions )

async def collection_apply_bg(
    request: Request, files: List[UploadFile], author: str, requirements: List[dict]) -> None:
    resp = { "files": [] }
    date = strftime('%Y-%m-%dT%H:%M:%S')
    try:
        resp["version"] = collection_apply_version(date)
        for file in files:
            path = join(MOUNT_PATH_FILE_STORAGE, file.filename)
            async with aopen(path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
            resp["files"].append({
                "size"        : getsize(path),
                "name"        : file.filename,
                "path"        : path,
                "content_type": file.content_type
            })
        collection_apply_history(requirements, date)
        resp["email"] = await collection_apply_email(
            author, requirements, date, resp["version"], request)
        ( resp["operations"], resp["exceptions"] ) = collection_operation_manager(requirements, date)
        resp["tree_update"] = collection_tree_update(request=request)
    except Exception as err:
        BackendPrint.error(str(err))
        BackendPrint.error(resp)

@router.post('/api/v1/collection/tree/update', tags=['Collection'])
def update_tree_with_collection(request: Request, body: TreeUpdate) -> JSONResponse:
    resp = collection_tree_update(body.root_path, request)
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/collection/tree/view', tags=['Collection'])
async def view_tree_by_collection(
    root_path: Annotated[str, QUERY_ROOT_PATH] = QUERY_ROOT_PATH) -> JSONResponse:
    return JSONResponse(status_code=200, content={ "tree": collection_query_tree(root_path) })

@router.get('/api/v1/collection/history/list', tags=['Collection'])
async def get_maintenance_history_list_of_collection() -> JSONResponse:
    sets, history = set(), defaultdict(lambda: dict(Dropdown()))
    with RedisContextManager(decode_responses=True) as r:
        for datestr in sorted(r.hkeys(CollectionDB.history), reverse=True):
            year, value = datestr.split('-')[0], datestr.split('T')[0]
            history[year]["label"] = year
            if value not in sets:
                raw = DropdownItem(value=value, label=value)
                history[year]["options"].append(raw.dict())
            sets.add(value)
    resp = { "list": list(history.values()) }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/collection/history/items', tags=['Collection'])
async def get_maintenance_history_items_of_collection(
    date: Annotated[str, QUERY_DATE_STRING] = QUERY_DATE_STRING) -> JSONResponse:
    resp = { "items": [] }
    with RedisContextManager(decode_responses=True) as r:
        for k in r.hkeys(CollectionDB.history):
            if k.split('T')[0] != date: continue
            query = r.hget(CollectionDB.history, k)
            for uuid in (raws := json_parse(query) if query else {}):
                resp["items"].append((raw := raws[uuid]) | {
                    "uuid"    : uuid,
                    "title"   : ntbasename(raw.get('file')),
                    "datetime": k
                })
    return JSONResponse(status_code=200, content=resp)

@router.delete('/api/v1/collection/history/delete', tags=['Collection'])
async def delete_maintenance_history_entry_of_collection(
    date: Annotated[str, QUERY_DATE_STRING] = QUERY_DATE_STRING) -> JSONResponse:
    with RedisContextManager(decode_responses=True) as r:
        query = [ k for k in r.hkeys(CollectionDB.history) if k.split('T')[0] == date ]
        if not query:
            raise HTTPException(status_code=404, detail='Date Not Found')
        for e in query: r.hdel(CollectionDB.history, e)
    resp = { "message": "success", "deleted_entries": query }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/collection/download/{path:path}',
            tags=['Collection'], response_class=StreamingResponse)
def download_tool_with_collection(
    path: Annotated[Union[str, FilePath], PATH_FILENAME] = PATH_FILENAME) -> StreamingResponse:
    if not isfile(file := join('/', path)):
        raise HTTPException(status_code=404, detail='File Not Found')
    size = getsize(file := join('/', path))
    resp = StreamingResponse(read_file_chunks(file))
    name = ntbasename(file).encode('ISO-8859-1', 'ignore').decode('utf-8')
    disposition = f"attachment; filename={name}; filename*=utf-8''{name}"
    resp.headers["Content-Length"] = str(size)
    resp.headers["Content-Disposition"] = disposition
    return resp

@router.get('/api/v1/collection/edit/info/{path:path}', tags=['Collection'])
async def get_edited_info_of_collection(
    path: Annotated[str, PATH_COLLECTION] = PATH_COLLECTION) -> JSONResponse:
    with RedisContextManager() as r:
        query = r.hget(CollectionDB.maps, (file := join('/', path))[1:])
    if not query:
        raise HTTPException(status_code=404, detail='Info Not Found')
    resp = { "info": { **json_parse(query), "gitlab": file } }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/collection/export', tags=['Collection'], response_class=StreamingResponse)
def collection_tree_export_to_excel(
    filename: Annotated[str, QUERY_EXCEL] = QUERY_EXCEL) -> StreamingResponse:
    with RedisContextManager() as r:
        query = r.hget(CollectionDB.tree, 'Collection')
    excel = Excel(json_parse(query) if query else {})
    excel.main()
    resp = StreamingResponse(excel.bytes)
    filename = filename if '.xlsx' in filename else f'{filename}.xlsx'
    disposition = f"attachment; filename={filename}; filename*=utf-8''{filename}"
    resp.headers["Content-Length"] = str(excel.size)
    resp.headers["Content-Disposition"] = disposition
    return resp

@router.post('/api/v1/collection/edit/apply', tags=['Collection'])
def apply_edited_info_of_collection(
    request: Request, payloads: Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS) -> JSONResponse:
    date = strftime('%Y-%m-%dT%H:%M:%S')
    requirements = collection_validate_requirements(payloads)
    with RedisContextManager() as r:
        for e in requirements:
            r.hset(CollectionDB.maps, e.get('gitlab'), str(e | {
                "modified_date": date,
                "operation"    : "Update",
                "file"         : ntbasename(e.get('gitlab', '')),
                "gitlab"       : ntdirname(e.get('gitlab', ''))
            }))
    resp = collection_tree_update(request=request)
    resp["requirements"] = requirements
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/collection/upload/apply', tags=['Collection'])
async def apply_upload_of_collection(
    bg_task: BackgroundTasks, request: Request,
    author  : Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS,
    payloads: Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS,
    files   : Annotated[List[UploadFile], FILE_MULTIPLE] = FILE_MULTIPLE) -> JSONResponse:
    requirements = collection_validate_requirements(payloads)
    bg_task.add_task(collection_apply_bg, request, files, author, requirements)
    resp = { "message": "Apply Successfully", "requirements": requirements }
    return JSONResponse(status_code=200, content=resp)
