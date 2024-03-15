#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.cacher import RedisContextManager
from library.schemas import MissionDB, MissionInfo
from library.config import template_path, GLOBAL_ROOT_PATH
from library.params import json_parse, validate_gitlab_project
from library.gitlabs import Group, Project, ProjectFile, getGitLab, getReadme, GITLAB_URL
from library.readme import (readme_update_content, readme_update_reports, readme_update_sms,
    readme_update_version, readme_update_associates, readme_update_validation,
    readme_update_coverage, readme_update_estimate, readme_update_testing_methodology)

from pathlib import Path
from textwrap import dedent
from pydantic import BaseModel
from os.path import join, isfile
from aiofiles import open as aopen
from dataclasses import asdict, dataclass
from starlette.responses import JSONResponse
from typing import Dict, List, Optional, Type, Union
from fastapi import APIRouter, HTTPException, BackgroundTasks

router = APIRouter()

@dataclass
class ProjectRepo:
    file_path      : str = ''
    content        : str = ''
    commit_message : str = 'Created a new file'
    branch         : str = 'master'
    author_email   : str = 'gitlab@ipt-gitlab.ies.inventec'
    author_name    : str = 'Administrator'

class MissionBody(BaseModel):
    name : Optional[str]  = 'SIT-Power-CycleTest'
    type : Optional[str]  = 'create'
    rest : Optional[bool] = False

class ProjectInfo(BaseModel):
    name                   : str
    path                   : Optional[str] = ''
    namespace_id           : Optional[int] = 0
    namespace              : Optional[str] = 'TA-Team'
    visibility             : Optional[str] = 'public'
    description            : Optional[str] = '[ARES] Automated Mission Created'
    build_timeout          : Optional[int] = 2592000
    default_branch         : Optional[str] = 'master'
    auto_devops_enabled    : Optional[bool] = False
    initialize_with_readme : Optional[bool] = True

def project_get_namespace(namespace: str = 'TA-Team'
    ) -> Union[Group, HTTPException]:
    if groups := getGitLab().groups.list(search=namespace):
        return groups[0]
    raise HTTPException(status_code=404, detail='Namespace Not Found')

def project_comm_readme_update(
    f: Type[ProjectFile], mission: MissionInfo) -> ProjectFile:
    """Utility function to update the project readme with common parts"""
    f.content = readme_update_content(f.content, '## Description', mission.description)
    f.content = readme_update_content(f.content, '## When to use ?', mission.when_to_use)
    f.content = readme_update_testing_methodology(f.content, mission.bkms)
    f.content = readme_update_reports(f.content, mission.log_types)
    return f

def project_file_init(project: Type[Project]) -> None:
    """Literally initialize to create the project files"""
    file_list = [
        {
            "file_path"     : "reports/.gitkeep",
            "commit_message": "Created reports directory"
        },
        {
            "file_path"     : "data/.gitkeep",
            "commit_message": "Created data directory"
        },
        {
            "file_path"     : "tools/.gitkeep",
            "commit_message": "Created tool directory"
        },
        {
            "file_path"     : "lib/.gitkeep",
            "commit_message": "Created lib directory"
        },
        {
            "file_path"     : "hosts",
            "content"       : Path(join(template_path.project, 'hosts_template')).read_text(),
            "commit_message": "Created ansible hosts"
        },
        {
            "file_path"     : ".gitignore",
            "content"       : Path(join(template_path.project, '.gitignore_template')).read_text(),
            "commit_message": "Created Git ignore file"
        },
        {
            "file_path"     : ".gitlab-ci.yml",
            "content"       : Path(join(template_path.project, '.gitlab-ci_template.yml')).read_text(),
            "commit_message": "Created CI pipeline yaml"
        }
    ]
    for e in file_list: project.files.create(asdict(ProjectRepo(**e)))

def project_var_init(project: Type[Project]) -> None:
    """Literally initialize the project variables"""
    variable_list = [
        {
            "key"  : "WORK_PATH",
            "value": "/srv/sut_test/$CI_COMMIT_SHA"
        },
        {
            "key"  : "EXE_PATH",
            "value": "/srv/sut_test/$CI_COMMIT_SHA/$CI_PROJECT_NAME"
        }
    ]
    for e in variable_list: project.variables.create(e)

def project_initialize(name: str) -> Union[List[Dict[str, str]], HTTPException]:
    project = validate_gitlab_project(name)
    binary = Path(f'{template_path.project}/README_template.md').read_bytes()
    with RedisContextManager() as r:
        if not (query := r.hget(MissionDB.create, name)):
            raise HTTPException(status_code=404, detail='Mission Not Found')
    mission = MissionInfo(**json_parse(query))
    customer = mission.script_name.split('-')[0]
    namespace = join(project.namespace.get('path', ''), project.name)
    te_names = mission.te_name.split(';')
    te_name = '\n' + ''.join([ f'    - {e}\n' for e in te_names ])
    f = project.files.get(file_path='README.md', ref='master')
    f.content = (
        binary.decode('utf-8')
            .replace('<SM_LINK>', mission.link)
            .replace('<PROJECT_NAME>', mission.script_name)
            .replace('<PROJECT_NAMESPACE>', namespace)
            .replace('<OWNER>', mission.owner)
            .replace('<LTE_NAME>', mission.lte_name)
            .replace('<TE_NAME>', te_name)
            .replace('<DEVELOPER>', mission.developer)
    )
    checked = '' if customer == 'SIT' else customer
    f.content = f.content.replace(f'  - [ ] {checked}', f'  - [x] {checked}')
    f = project_comm_readme_update(f, mission)
    f.save(branch='master', commit_message='[ARES] Automated Mission Initialized')
    project_file_init(project)
    project_var_init(project)
    return project.repository_tree()

async def project_create_background(info: ProjectInfo, avatar: str) -> None:
    """Create a all new project with created mission data as
    background when API requests"""
    info.path = info.name
    project = getGitLab().projects.create(info.dict())
    async with aopen(avatar, 'rb') as image:
        project.avatar = await image.read()
    project.save()
    project_initialize(info.name)

def project_update_background(body: MissionBody, mission: MissionInfo) -> None:
    """Update an exists project with exists mission data as
    background when API requests"""
    restore_message = '[ARES] Automated Mission Restored'
    commit_message = restore_message if body.rest else dedent(
        f"""\
        [ARES] Automated Mission Updated
            - Status   : [{mission.status.capitalize()}]
            - Phase    : [{mission.phase.capitalize()}]
            - Revision : v{mission.script_version}
            - Progress : {mission.progress}%
            - Author   : {mission.author}
            - Comment  : {mission.comment}
        """
    )
    project = validate_gitlab_project(body.name)
    readme = getReadme(project)
    f = project.files.get(file_path='README.md', ref='master')
    f.content = (
        readme.replace('<ESTIMATE>', str(mission.time_saving))
        if '<ESTIMATE>' in readme
        else readme_update_estimate(readme, str(mission.time_saving))
    )
    f = project_comm_readme_update(f, mission)
    f.content = readme_update_version(f.content, mission.script_version)
    f.content = readme_update_sms(f.content, mission.link, body.type)
    f.content = readme_update_associates(f.content, mission)
    f.content = readme_update_validation(f.content, mission.te_data)
    f.content = readme_update_coverage(f.content, mission.coverages)
    f.save(branch='master', commit_message=commit_message)

def project_update_new_mission(info: ProjectInfo) -> ProjectInfo:
    """Update a new mission that query by Redis DB with `GitLab Project`
    , then sync the data in each other"""
    with RedisContextManager() as r:
        if query := r.hget(MissionDB.create, info.name):
            mission = MissionInfo(**json_parse(query))
            mission.repository = join(GITLAB_URL, info.namespace, info.name)
            info.description = mission.when_to_use
            r.hset(MissionDB.create, info.name, str(mission.dict()))
    return info

@router.post('/api/v1/mission/project/create', tags=['Mission'])
async def create_new_mission_project(
    background_tasks: BackgroundTasks, info: ProjectInfo) -> JSONResponse:
    info.namespace_id = project_get_namespace(info.namespace).id
    info = project_update_new_mission(info)
    customer = info.name.split('-')[0].lower()
    if not isfile(avatar := join(GLOBAL_ROOT_PATH, 'static/image', f'{customer}.png')):
        raise HTTPException(status_code=404, detail='Avatar Not Found')
    background_tasks.add_task(project_create_background, info, avatar)
    return JSONResponse(status_code=200, content={ "result": info.dict() })

@router.post('/api/v1/mission/project/update', tags=['Mission'])
async def update_mission_project_readme(
    background_tasks: BackgroundTasks, body: MissionBody) -> JSONResponse:
    with RedisContextManager() as r:
        if not (query := r.hget(asdict(MissionDB()).get(body.type), body.name)):
            raise HTTPException(status_code=404, detail='Mission Not Found')
    mission = MissionInfo(**json_parse(query))
    background_tasks.add_task(project_update_background, body, mission)
    return JSONResponse(status_code=200, content={ "result": "Background" })
