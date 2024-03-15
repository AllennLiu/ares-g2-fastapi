#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('..')
sys.path.append('../library')

from library.config import settings
from library.params import json_parse
from library.moment import datetime_data
from library.mongodb import ConnectMongo
from library.cacher import RedisContextManager
from library.helpers import timeit, version_class
from library.iteration import find, groupby_array, sortby_key, uniq_items_by_key
from library.schemas import Analyzer, AutomationDB, RedisDB, MissionDB, ScriptConfig
from library.gitlabs import (parse_project_commit_at, getReadme, getProjects,
    ProjectScriptRule, Project)
from library.readme import (get_ver_by_readme, get_developer_by_readme,
    get_testers_by_readme, get_script_name_func)

from uuid import uuid4
from time import strftime
from re import sub, search
from json import loads, dumps
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Type
from argparse import ArgumentParser, RawTextHelpFormatter, Namespace

class Downloads(BaseModel):
    version    : Optional[str] = '0.0.1'
    ver_class  : Optional[str] = 'release'
    datetime   : Optional[str] = datetime_data().get('string')
    name       : Optional[str] = ''
    commit_sha : Optional[str] = ''
    link       : Optional[str] = ''
    message    : Optional[str] = ''
    committer  : Optional[str] = ''
    latest     : Optional[bool] = False

def args_parser() -> Namespace:
    global ARGS
    desc = 'FastAPI CronJob:\nTo handle GitLab script data.'
    parser = ArgumentParser(description=desc, formatter_class=RawTextHelpFormatter)
    parser.add_argument('--update-list', action='store_true',
                        help='update script list from GitLab')
    parser.add_argument('--update-usage', action='store_true',
                        help='update download usage of scripts')
    parser.add_argument('--update-download', action='store_true',
                        help='update script download list by commits')
    ARGS = parser.parse_args()
    return ARGS

def sched_project_trigger_token(project: Type[Project], data: Dict[str, Any]) -> str:
    """
    Create project Automation API trigger token if it
    not exists, and it exists in redis or GitLab will
    return the value automatically.
    """
    if data.get(project.name):
        if api_trigger_token := data[project.name].get('api_trigger_token'):
            return api_trigger_token
    triggers = project.triggers.list(all=True)
    triggers_desc = [ e.description for e in triggers ]
    if 'Automation' not in triggers_desc:
        trigger = project.triggers.create({ "description": "Automation" })
        return trigger.token
    else:
        token = find(lambda x: x.description == 'Automation', triggers)
        return token.token if token else ''

def sched_download_count(name: str = 'SIT-LogFilter') -> int:
    with ConnectMongo(database='flask') as m:
        count, query = 0, m.query('scripts_name', { "group": "TA-Team" })
        if query is None or name not in query.get('projects'):
            return count
        for collection in m.db.list_collection_names():
            if not search('^scripts_counter_', collection): continue
            if q := m.query(collection, { "name": name }, all=True):
                count += len(list(q))
    return count

def sched_pipeline_variables(data: Dict[str, Any], name: str) -> List[str]:
    keys = [ 'sut_ip', 'sut_mac', 'reference', 'script_cmd' ]
    if data.get(name):
        return data[name]['variables'] if data[name].get('variables') else keys
    return keys

def sched_get_db_data(name: str) -> Dict[str, Any]:
    with RedisContextManager(decode_responses=True) as r:
        return { k: json_parse(r.hget(name, k)) for k in r.hkeys(name) }

def sched_save_script_list(
    db_name: str, data: Dict[str, Any], resp: List[Dict[str, Any]]) -> None:
    with RedisContextManager() as r:
        for script_name in set(data) - set(groupby_array(resp, 'script_name')):
            r.hdel(db_name, script_name)
        for script_raw in resp:
            r.hset(db_name, script_raw["script_name"], str(script_raw))

def sched_update_script_list(db_name: str = MissionDB.gitlab
    ) -> tuple[List[Dict[str, Any]], List[Project]]:
    resp: List[Dict[str, Any]] = []
    script_projects = getProjects(**ProjectScriptRule().dict())
    data = sched_get_db_data(db_name)
    for p in script_projects:
        try:
            readme = getReadme(p)
            version = get_ver_by_readme(by_project=p, readme=readme)
            testers = get_testers_by_readme(readme)
            committed = p.commits.list(all=True)[0].committed_date
            last_update = search(r'\d{4}\-\d{2}\-\d{2}', committed).group()
            resp.append({
                "id"               : p.id,
                "script_name"      : p.name,
                "customer"         : p.name.split('-')[0],
                "function"         : get_script_name_func(p.name),
                "repository_url"   : p.web_url,
                "last_update"      : last_update,
                "rev"              : version,
                "ver_class"        : version_class(version),
                "validate_te"      : testers[-1] if testers else '',
                "developer"        : get_developer_by_readme(readme),
                "variables"        : sched_pipeline_variables(data, p.name),
                "modified_date"    : parse_project_commit_at(p),
                "api_trigger_token": sched_project_trigger_token(p, data),
                "readme"           : readme,
                "download_count"   : sched_download_count(p.name)
            })
        except Exception as err:
            print(f'ERROR: {err}')
            exit(-1)
    sched_save_script_list(db_name, data, resp)
    return (resp, script_projects)

def sched_update_script_analysis(items: List[dict] = []) -> Dict[str, Any]:
    with RedisContextManager(decode_responses=True) as r:
        keys = r.hkeys(name := AutomationDB.analysis)
        for k in (script_data := groupby_array(items, 'script_name')):
            # update dynamic project data with existing script
            if k in keys:
                r.hset(name, k, dumps({
                    **loads(r.hget(name, k)),
                    "rev"           : script_data[k].get('rev'),
                    "download_count": script_data[k].get('download_count')
                }))
            # update project data with base model to not exists script
            else:
                r.hset(name, k, dumps({
                    **Analyzer().dict(),
                    "id"            : script_data[k].get('id'),
                    "uuid"          : str(uuid4()),
                    "rev"           : script_data[k].get('rev'),
                    "customer"      : script_data[k].get('customer'),
                    "function"      : script_data[k].get('function'),
                    "download_count": script_data[k].get('download_count'),
                    "last_update"   : strftime('%Y-%m-%dT%H:%M:%S')
                }))
        return sched_get_db_data(AutomationDB.analysis)

def sched_update_script_settings(
    items: List[Dict[str, Any]], projects: List[Project]) -> List[str]:
    settings = sched_get_db_data(AutomationDB.settings)
    updated_scripts: List[Dict[str, Any]] = []
    with RedisContextManager() as r:
        for e in items:
            if e.get('script_name') in settings: continue
            project = find(lambda x: x.name == e["script_name"], projects)
            data = ScriptConfig(uuid=str(uuid4()), kill_processes=[
                e["name"] for e in project.repository_tree(ref='master')
                if e.get('type') == 'blob'
                and search('\.(py|sh|js)$', e.get('name'))
            ])
            r.hset(AutomationDB.settings, e["script_name"], dumps(data.dict()))
            updated_scripts.append(e["script_name"])
    return sorted(updated_scripts)

def sched_update_script_usage() -> List[dict]:
    names = [ e.name for e in getProjects(**ProjectScriptRule().dict()) ]
    data = { "group": "TA-Team", "projects": names }
    with ConnectMongo(database='flask') as m:
        m.deleteDocument('scripts_name', many=True)
        m.insertCollection('scripts_name', data)
        resp = m.listCollection('scripts_name', string_id=True)
    return resp

def sched_save_download_list(
    data: Dict[str, list] = {}, resp: Dict[str, list] = {}) -> Dict[str, list]:
    with RedisContextManager() as r:
        for k in data:
            uniques = uniq_items_by_key(
                sortby_key(data[k], 'datetime', reverse=True),
                key    = 'version',
                sorted = False
            )
            r.hset(RedisDB.downloads, k, dumps(uniques))
            resp[k] = [ e["version"] for e in uniques ]
    return resp

def sched_update_download_list(
    data: Dict[str, list] = {}, resp: Dict[str, list] = {}) -> Dict[str, list]:
    endpoint = f'{settings.app_config["service"]["fastapi"]}.{settings.app_config["domain"][settings.env]}'
    for p in getProjects(**ProjectScriptRule().dict()):
        data[p.name]: List[Dict[str, Any]] = []
        tags = map(lambda x: x.name, p.tags.list(all=True))
        master_ver = get_ver_by_readme(by_project=p)
        for e in p.commits.list(ref_name='master', get_all=True):
            readme = getReadme(p, ref=e.id)
            ver = get_ver_by_readme(by_project=p, readme=readme)
            if not search(r'^(\d{1,2}\.){2}\d{1,2}$', ver): continue
            if search(r'^\d{2}(\.\d{1,2}){2}$', ver) and ver not in tags: continue
            dev = get_developer_by_readme(readme)
            data[p.name].append(dict(Downloads(**{
                **p._attrs,
                "version"   : ver,
                "ver_class" : version_class(ver),
                "datetime"  : sub('T', ' ', e.committed_date.split('.')[0]),
                "commit_sha": e.id,
                "latest"    : ver == master_ver,
                "message"   : e.message,
                "committer" : dev or e.committer_email.split('@')[0],
                "link"      : f'http://{endpoint}/api/v1/scripts/download/{p.name}/{e.id}'
            })))
    return sched_save_download_list(data, resp)

@timeit
def main() -> None:
    args_parser()
    if ARGS.update_list:
        print(' * Schedule Rule: [*/8 * * * *]')
        print(' * Updating script list from GitLab:')
        script_data, projects = sched_update_script_list()
        print(dumps(script_data, indent=4) + '\n')
        print(' * Updating Automation Analysis by script list:')
        print(dumps(sched_update_script_analysis(script_data), indent=4) + '\n')
        print(' * Updating Automation Settings by script list:')
        items = sched_update_script_settings(script_data, projects)
        print(dumps(items, indent=4) + '\n')
    if ARGS.update_usage:
        print(' * Schedule Rule: [*/9 * * * *]')
        print(' * Updating download usage by scripts:')
        print(dumps(sched_update_script_usage(), indent=4) + '\n')
    if ARGS.update_download:
        print(' * Schedule Rule: [*/10 * * * *]')
        print(' * Updating download list by commit SHA:')
        print(dumps(sched_update_download_list(), indent=4) + '\n')

if __name__ == '__main__':
    main()
