#!/usr/bin/python3
# -*- coding: utf-8 -*-

from moment import datetimer, time_convertor

from re import search
from time import sleep
from pydantic import BaseModel
from typing import Any, List, Dict, Optional, Type, Union
from argparse import ArgumentParser, RawTextHelpFormatter

from contextlib import suppress
from collections import defaultdict
from gitlab import Gitlab, exceptions
from gitlab.v4.objects.groups import Group
from gitlab.v4.objects.tags import ProjectTag
from gitlab.v4.objects.jobs import ProjectJob
from gitlab.v4.objects.files import ProjectFile
from gitlab.v4.objects.pipelines import ProjectPipelineJob
from gitlab.v4.objects.projects import Project, ProjectPipeline

GITLAB_URL = 'http://ipt-gitlab.ies.inventec:8081'
GITLAB_API_TOKEN = 'LuhHqKxMY7b4nESGRkmv'
GITLAB_API_HEADER = { "PRIVATE-TOKEN": GITLAB_API_TOKEN }

class ProjectScriptRule(BaseModel):
    """搜索參數 `(search=)` GitLab 群組規則，默認 `TA-Team`"""
    search            : Optional[str]  = 'TA-Team'
    visibility        : Optional[str]  = 'public'
    search_namespaces : Optional[bool] = True

def getGitLab() -> Gitlab:
    """獲取並返回 ``GitLab API`` 會話實例"""
    return Gitlab(GITLAB_URL, GITLAB_API_HEADER["PRIVATE-TOKEN"])

def getProjects(**kwargs) -> List[Project]:
    """獲取 GitLab 上所有項目，可傳入搜索群組規則來縮小範圍"""
    lab = Gitlab(GITLAB_URL, GITLAB_API_HEADER["PRIVATE-TOKEN"])
    projects = lab.projects.list(all=True, **kwargs)
    return projects

def getProject(id: int = 0, name: str = '') -> Union[Project, None]:
    """依指定 ID 或名稱獲取指定 GitLab 上的 `Project` 實例"""
    lab = Gitlab(GITLAB_URL, GITLAB_API_HEADER["PRIVATE-TOKEN"])
    with suppress(Exception):
        if name and not id:
            projects = lab.projects.list(search=name)
            project = projects[0]
            if project.name != name:
                for e in projects:
                    if e.name == name:
                        project = e
                        break
        else:
            project = lab.projects.get(id)
        return project
    return None

def getReadme(project: Type[Project], ref: str = 'master') -> str:
    """依指定項目實例獲取指定 Commit 的 `README.md` 內容"""
    raw_content = project.files.raw(file_path='README.md', ref=ref)
    return raw_content.decode()

def get_group_variable(
    keys: List[str] = [], namespace: str = ProjectScriptRule().search) -> Dict[str, Any]:
    """獲取 `GitLab` 上指定群組所有的 `CI/CD` 變量字典"""
    data = defaultdict(str)
    if not keys or not isinstance(keys, list):
        return dict(data)
    if groups := getGitLab().groups.list(search=namespace):
        group = groups.pop()
    for k in keys:
        with suppress(exceptions.GitlabGetError):
            data[k] = group.variables.get(k).value
    return dict(data)

def check_pipeline_running_status(
    project: Type[Project], retry: int = 3) -> tuple[bool, str]:
    """檢查指定項目的 `CI/CD Pipeline` 狀態，是否仍在執行"""
    for _ in range(retry):
        try:
            pipeline_status = project.pipelines.list(all=True)[0].status
            if pipeline_status == 'running':
                return ( False, 'Running' )
            else:
                return ( True, 'Success' )
        except Exception:
            sleep(1)
    return ( False, 'Timeout' )

def commit_message_template(
    project: Type[Project], version: str, contents: List[str]) -> str:
    """生成 `Git` 提交信息 (commit messages) 模板"""
    headers = f'[{(name := project.name)}]'
    names = name.split('-')
    if name.count('-') == 1:
        headers = f'[{names[0]}]'
    elif name.count('-') == 2:
        headers = f'[{names[0]}][{names[1]}]'
    return '\n'.join([
        f'{headers} {names[-1]}\n',
        f'V{version} change list:',
        *contents,
        'Test Done: OK',
        'Bug: None\n'
    ])

def parse_project_commit_at(project: Type[Project], index: int = 0) -> str:
    """擷取出指定項目及下標的``提交時間輟``"""
    regexp = r'\d{4}(-\d{2}){2}T(\d{2}:){2}\d{2}'
    at = project.commits.list(all=True, ref_name='master')[index].created_at
    datetime = datetimer(search(regexp, at).group())
    return datetimer(datetime, ts=False, date=True)

def parse_project_tag_at(project: Type[Project]) -> str:
    """擷取指定項目最新一筆的``標籤 (Tag) 創建時間戳``"""
    if tags := project.tags.list(get_all=True):
        items = [ f'{e.name}_{e.commit["created_at"]}' for e in tags ]
        date_string = sorted(items, reverse=True)[0].split('_')[-1]
        return ' '.join(time_convertor(date_string, is_timestamp=False)[:2])
    return ' '.join(time_convertor(project.created_at, is_timestamp=False)[:2])

if __name__ == '__main__':
    parser = ArgumentParser(description='GitLab project instance', formatter_class=RawTextHelpFormatter)
    parser.add_argument('-p', '--project', action='store', type=str,
                        default='SIT-Flask-API', help='set project name\n(default: "%(default)s")')
    parser.add_argument('-r', '--readme', action='store_true',
                        help='get README content by specified project name')
    parser.add_argument('-a', '--all', action='store_true', help='get all project')
    parser.add_argument('-u', '--url', action='store', type=str, default=GITLAB_URL,
                        help='set GitLab url\n(default: "%(default)s")')
    parser.add_argument('--private-token', action='store', type=str, default=GITLAB_API_TOKEN,
                        help='set API user\'s private token\n(default: "%(default)s")')
    group1 = parser.add_argument_group('Single', 'python3 %(prog)s -p "SIT-Flask-API"')
    group1 = parser.add_argument_group('README', 'python3 %(prog)s -p "SIT-Flask-API" -r')
    group2 = parser.add_argument_group('All', 'python3 %(prog)s -a')
    args = parser.parse_args()
    project = args.project
    get_readme = args.readme
    to_all = args.all
    GITLAB_URL = args.url
    GITLAB_API_TOKEN = args.private_token
    GITLAB_API_HEADER |= { "PRIVATE-TOKEN": GITLAB_API_TOKEN }
    if to_all:
        _ = [ print(p) for p in getProjects(**ProjectScriptRule().dict()) ]
    elif get_readme:
        print(getReadme(getProject(name=project)))
    else:
        print(getProject(name=project))
