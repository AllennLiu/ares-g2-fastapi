#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.iteration import find
from library.remote import SSHConnect
from library.moment import datetime_data
from library.schemas import AutomationDB
from library.readme import markup_content
from library.cacher import RedisContextManager
from library.helpers import is_true, catch_except_retry, delete_ansi
from library.params import json_parse, raise_gitlab_list, catch_exception
from library.gitlabs import getProject, get_group_variable, Project, ProjectPipeline, ProjectJob

from re import sub
from json import dumps
from os import makedirs
from shutil import copy2
from gitlab import exceptions
from pydantic import validator, BaseModel
from starlette.responses import JSONResponse
from os.path import join, dirname, isdir, isfile
from typing import Any, Dict, List, Annotated, Optional, Type, Union
from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks

router = APIRouter()
PROCESS_LIST_CMD = "ps -ef | grep -v grep | grep -E '%s' | awk '{print $2}'"
PROCESS_KILL_CMD = r"kill $(pstree -p %d | sed 's/(/\n(/g' | grep '(' | sed 's/(\(.*\)).*/\1/' | tr '\n' ' ')"

class JobReference(BaseModel):
    project_id  : Optional[int] = 12
    pipeline_id : Optional[int] = 12

class JobAction(JobReference):
    operation : Optional[str] = 'cancel'
    step      : Optional[str] = 'runTest'

    @validator('operation')
    def validate_operation(value, field):
        options = [ 'play', 'retry' ,'cancel', 'erase' ]
        if value not in options:
            raise ValueError(f'operation must in {options}')
        return value

class JobArchive(JobReference):
    nas_log_path   : str
    name           : Optional[str] = ''
    path           : Optional[str] = ''
    ares_bkm_id    : Optional[int] = 0
    ares_bkm_index : Optional[int] = 0

    @validator('nas_log_path')
    def validate_nas_path(value, field):
        root = sub(r'^\/', '', value).split('/')[0]
        parent = join('/mnt', sub(r'^\/', '', value))
        try:
            assert root == 'Projects', 'Root directory must be Projects'
            assert isdir(parent), 'Parent directory not exists'
        except AssertionError as err:
            raise ValueError(str(err)) from err
        return value

class JobArtifacts(BaseModel):
    link         : Optional[str] = ''
    project      : Optional[str] = ''
    job_id       : Optional[int] = 0
    datetime     : Optional[str] = datetime_data().get('dt')
    nas_path     : Optional[str] = ''
    nas_log_dir  : Optional[str] = ''
    nas_log_file : Optional[str] = ''

class PipelineAction(JobReference):
    operation : Optional[str] = 'cancel'

    @validator('operation')
    def validate_operation(value, field):
        options = [ 'retry' ,'cancel', 'delete' ]
        if value not in options:
            raise ValueError(f'operation must in {options}')
        return value

QUERY_PROJECT_ID = Query(12, description='A number of `Project ID`')
QUERY_PIPELINE_ID = Query(..., description='A number of `Pipeline ID`')
QUERY_LOG_ALL = Query(False, description='All `Pipeline Jobs`')
QUERY_LOG_COLOR = Query(False, description='ANSI `Color Print`')
QUERY_LOG_SIZE = Query(3.8, description='Max `Log Size` *(MiB)*')
QUERY_JOB_NAME = Query(JobAction().step, description='Job Name')

@catch_exception
def automation_opt_job(job: Type[ProjectJob], operation: str) -> Any:
    return getattr(job, operation or 'cancel')()

@catch_exception
def automation_opt_pipeline(pipeline: Type[ProjectPipeline], operation: str) -> Any:
    return getattr(pipeline, operation or 'cancel')()

def automation_get_pipe(project_id: int, pipeline_id: int
    ) -> Union[tuple[Project, ProjectPipeline], HTTPException]:
    project = getProject(project_id)
    if not project:
        raise HTTPException(status_code=404, detail='Project Not Found')
    try:
        return ( project, project.pipelines.get(pipeline_id) )
    except exceptions.GitlabGetError:
        raise_gitlab_list(project.pipelines, f'Pipeline {pipeline_id}')

def automation_get_job(project: Type[Project], pipeline: Type[ProjectPipeline],
    step: str = JobAction().step) -> Union[ProjectJob, HTTPException]:
    job_ids = set()
    for e in pipeline.jobs.list(all=True)[::-1]:
        job_ids.add(e.id)
        if e.name == step:
            return project.jobs.get(e.id, lazy=True)
    detail = f'Job {step} Not Found, Allowed List: {list(job_ids)}'
    raise HTTPException(status_code=404, detail=detail)

def automation_query_vars(project: Type[Project], pipeline: Type[ProjectPipeline]
    ) -> Dict[str, Union[List[dict], str]]:
    with RedisContextManager() as r:
        query = r.hget(AutomationDB.settings, project.name)
    data = json_parse(query) if query else {}
    ps_names = data["kill_processes"] if data.get('kill_processes') else []
    vars_pip = [ v._attrs for v in pipeline.variables.list(all=True) ]
    vars_pro = [ v._attrs for v in project.variables.list(all=True) ]
    return { "project": vars_pro, "pipeline": vars_pip, "ps_names": ps_names }

def automation_docker_stop(pipe: List[Dict[str, Any]], uuid: str) -> Dict[str, Any]:
    cmd = f'docker stop selenium-{uuid.replace("-", "")}'
    web = find(lambda x: x.get('key') == 'ARES_BMC_WEB_TEST', pipe)
    if not isinstance(web, dict):
        return {}
    is_web_test = is_true(web.get('value', False))
    try:
        assert is_web_test, 'skipped when ARES_BMC_WEB_TEST is false'
        v = get_group_variable(
            keys      = [ 'SRV_USER', 'SRV_PASS', 'SRV_HOST' ],
            namespace ='Sit-develop-tool'
        )
        with SSHConnect(v["SRV_HOST"], v["SRV_USER"], v["SRV_PASS"]) as ssh:
            output, _ = ssh.run(cmd)
        return { "docker": { "exec": cmd, "output": output } }
    except Exception as err:
        return { "docker": { "error": str(err) } } if is_web_test else {}

def automation_process_kill(resp: Dict[str, Any], data: Dict[str, Any],
                            names: List[str]) -> Union[Dict[str, Any], HTTPException]:
    regexp_name = '|'.join(names)
    group_var = get_group_variable([ 'SUT_USER', 'SUT_PASS', 'SUT_PORT' ])
    variables = { e.get('key'): e.get('value') for e in data["pipeline"] }
    if (job_id := variables.get('ARES_JOB_UUID')):
        regexp = job_id
        stopped = automation_docker_stop(data["pipeline"], regexp)
        resp = { **resp, **stopped }
    regexp = regexp or regexp_name
    resp["ps_names"] = regexp.split('|')
    try:
        assert regexp.strip(), 'Empty Process Name'
        with SSHConnect(variables.get('sut_ip'),
                        variables.get('SUT_USER', group_var["SUT_USER"]),
                        variables.get('SUT_PASS', group_var["SUT_PASS"]),
                        variables.get('SUT_PORT', group_var["SUT_PORT"])) as ssh:
            ssh.run(f'sed -i -E \'/{regexp_name}/d\' /etc/rc.d/rc.local')
            output = ssh.run(PROCESS_LIST_CMD % regexp)[0].strip()
            if not sub(r'\s|\n', '', output):
                return { **resp, "message": "Process Group Killed" }
            for line in iter(output.splitlines()):
                if not line.strip().isdigit(): continue
                pid = int(line.strip())
                resp["processes"].append({
                    "parent": pid,
                    "stdout": ssh.run(PROCESS_KILL_CMD % pid)[0],
                    "stderr": ""
                })
    except Exception as err:
        raise HTTPException(status_code=503, detail=f'SSH Failed: {str(err)}') from err
    return resp

def automation_log_tracer(color: bool, limit: float, job: Type[ProjectJob]) -> str:
    m = (f'\x1b[33;1mJob\'s output exceeded limit over than {limit} MB.\n' +
        'Runtime log will only display the last 1000 lines.\x1b[0;m')
    log = job.trace().decode()
    output = markup_content(log) if color else delete_ansi(log)
    if len(output.encode('utf-8')) > (limit * 1024 * 1024):
        output = '\n'.join(output.splitlines()[-1000:]) + m
    return output

def automation_parse_artifacts(
    request: Type[Request], arc: JobArchive, art: JobArtifacts) -> JobArtifacts:
    nas_abs_path = join('/mnt', arc.nas_log_path.strip('/'))
    art.nas_log_dir = f'{nas_abs_path}/Automation-Logs'
    art.nas_log_file = join(art.nas_log_dir, arc.name)
    art.link = f'{request.base_url}api/v1/collection/download{art.nas_path}'
    return art

def automation_save_db_reports(art: JobArtifacts) -> None:
    with RedisContextManager() as r:
        query = r.hget(AutomationDB.reports, art.project)
        data = { **(json_parse(query) if query else {}), art.datetime: art.dict() }
        r.hset(AutomationDB.reports, art.project, dumps(data))

@catch_except_retry(times=3)
def automation_save_artifacts(job: Type[ProjectJob], art: JobArtifacts
    ) -> Union[None, AssertionError]:
    for e in [ dirname(art.nas_path), art.nas_log_dir ]:
        if not isdir(e): makedirs(e)
    with open(art.nas_path, 'wb') as f:
        job.artifacts(streamed=True, action=f.write)
    assert isfile(art.nas_path), f'Artifacts \'{art.nas_path}\' Not Found'
    copy2(art.nas_path, art.nas_log_file)
    automation_save_db_reports(art)

def automation_config_artifacts(
    project: Type[Project], pipeline: Type[ProjectPipeline], arc: JobArchive) -> JobArchive:
    date_tag = sub(r'\-|T|\:|\..*', '', pipeline.created_at)
    arc.name = '-'.join([
        str(arc.ares_bkm_id),
        str(arc.ares_bkm_index).zfill(2),
        project.name,
        f'Report-{date_tag}.zip'
    ])
    arc.path = join('/mnt/storage', AutomationDB.reports, project.name, arc.name)
    return arc

@router.get('/api/v1/automation/job/logger', tags=['Automation'])
def output_log_by_automation_job(
    project_id  : Annotated[int, QUERY_PROJECT_ID] = QUERY_PROJECT_ID,
    pipeline_id : Annotated[int, QUERY_PIPELINE_ID] = QUERY_PIPELINE_ID,
    all         : Annotated[bool, QUERY_LOG_ALL] = QUERY_LOG_ALL,
    colour      : Annotated[bool, QUERY_LOG_COLOR] = QUERY_LOG_COLOR,
    limit       : Annotated[float, QUERY_LOG_SIZE] = QUERY_LOG_SIZE,
    step        : Annotated[str, QUERY_JOB_NAME] = QUERY_JOB_NAME) -> JSONResponse:
    resp = { "message": "Successfully", "outputs": [] }
    project, pipeline = automation_get_pipe(project_id, pipeline_id)
    job_dict = { j.name: j.id for j in pipeline.jobs.list(all=True) }
    job_ids = sorted(job_dict.values()) if all else [ job_dict.get(step) ]
    for job_id in job_ids:
        if job_id:
            job = project.jobs.get(job_id)
            resp["outputs"].append(automation_log_tracer(colour, limit, job))
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/automation/job/operate', tags=['Automation'])
def automation_job_operation(opt: PipelineAction) -> JSONResponse:
    pipeline = automation_get_pipe(opt.project_id, opt.pipeline_id)[1]
    automation_opt_pipeline(pipeline, opt.operation)
    resp = { "message": f"{opt.operation.capitalize()} Successfully" }
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/automation/job/pkill', tags=['Automation'])
def process_kill_automation_job(ref: JobReference) -> JSONResponse:
    resp = { "message": "Killed Successfully", "processes": [] }
    project, pipeline = automation_get_pipe(ref.project_id, ref.pipeline_id)
    variables = automation_query_vars(project, pipeline)
    if not variables.get('ps_names'):
        return JSONResponse(status_code=200, content=resp)
    if pipeline.status != 'running':
        msg = f'Pipeline Already {pipeline.status.capitalize()}'
        return JSONResponse(status_code=200, content={ **resp, "message": msg })
    resp = automation_process_kill(resp, variables, variables["ps_names"])
    return JSONResponse(status_code=200, content=resp)

@router.post('/api/v1/automation/job/archive', tags=['Automation'])
async def archive_report_by_automation_job(bg_task: BackgroundTasks,
    request: Request, arc: JobArchive) -> JSONResponse:
    project, pipeline = automation_get_pipe(arc.project_id, arc.pipeline_id)
    job = automation_get_job(project, pipeline)
    arc = automation_config_artifacts(project, pipeline, arc)
    artifacts = JobArtifacts(
        project  = project.name,
        job_id   = job.id,
        datetime = pipeline.created_at.split('.')[0],
        nas_path = arc.path
    )
    resp = automation_parse_artifacts(request, arc, artifacts)
    bg_task.add_task(automation_save_artifacts, job, resp)
    return JSONResponse(status_code=200, content=resp.dict())
