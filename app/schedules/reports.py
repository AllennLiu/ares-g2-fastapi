#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('..')
sys.path.append('../library')

from library.helpers import timeit
from library.moment import datetimer
from library.params import json_parse
from library.iteration import flatten
from library.bts import get_bts_projects
from library.achievement import WorkAchievement, AutomationSummary
from library.cacher import RedisContextManager, get_script_customers
from library.gitlabs import getProjects, ProjectTag, ProjectScriptRule
from library.schemas import current_duration, MissionDB, ReportDB, Durations, QUATERS, HALFYEAR_MAPS

from time import mktime
from json import loads, dumps
from datetime import datetime
from pydantic import BaseModel
from re import sub, search, findall
from typing import Any, Dict, List, Optional, Type, Union
from argparse import ArgumentParser, RawTextHelpFormatter, Namespace

DATE_REGEXP = r'^(\d{2}\/){2}\d{4}\s(\d{2}\:){2}\d{2}'
OPEN_DATE_REGEXP = r'([A-Z][a-z]{2}\s){2}\d{2}\s\d{4} (\d{2}\:){2}\d{2}'
CUSTOMERS = get_script_customers()
CUSTOMERS.remove('SIT')
CUSTOMERS.append('Common')
DURATIONS = current_duration()
# debug code: DURATIONS = Durations(year='2023', half_year='H2', quater='Q4', duration='2023-H2')

class KpiConfig(BaseModel):
    script     : Optional[int] = 10
    timesaving : Optional[int] = 500
    coverage   : Optional[int] = 100
    year       : Optional[str] = DURATIONS.year
    half_year  : Optional[str] = DURATIONS.half_year
    duration   : Optional[str] = DURATIONS.duration

class KpiData(BaseModel):
    time_saving  : Optional[float] = 0.1
    bkm_quantity : Optional[int]   = 0
    developer    : Optional[str]   = ''
    bkms         : Optional[dict]  = {}

class ReturnRate(BaseModel):
    DefectID    : Optional[int] = 0
    Duration    : Optional[str] = ''
    OpenDate    : Optional[str] = ''
    Submitter   : Optional[str] = ''
    DefectClass : Optional[str] = ''
    Comments    : Union[list, None] = []

def args_parser() -> Namespace:
    global ARGS
    desc = 'FastAPI CronJob:\nUpdate return rate for caching data.'
    parser = ArgumentParser(description=desc, formatter_class=RawTextHelpFormatter)
    parser.add_argument('-u', '--update', action='store_true',
                        help='update return rate from issues cache data')
    parser.add_argument('-s', '--summary', action='store_true',
                        help='summary TA-Team work achievement cache')
    ARGS = parser.parse_args()
    return ARGS

def sched_format_datetime(open_date: str, full: bool = False) -> str:
    if not search(OPEN_DATE_REGEXP, open_date):
        return open_date
    date_str = search(OPEN_DATE_REGEXP, open_date).group()
    ts = mktime(datetime.strptime(date_str, '%a %b %d %Y %X').timetuple())
    if full:
        return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %X')
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')

def sched_find_datetime(open_date: str) -> str:
    if search(OPEN_DATE_REGEXP, open_date):
        return sched_format_datetime(open_date, True)
    items = findall(r'\d{4}\-\d{2}\-\d{2}|\d{2}\:\d{2}\:\d{2}', open_date)
    return ' '.join(items)

def sched_parse_duration(open_date: str) -> str:
    open_date_origin = open_date
    for i in range(2):
        try:
            items = sched_find_datetime(open_date).split()[0].split('-')
            assert len(items) > 1, 'open_date split items must large than 1.'
            return f'{items[0]}-{QUATERS.get(items[1])}'
        except Exception as err:
            if i == 1:
                print(f'ERROR: {err}')
                print(f'OpenDate Old: {open_date_origin}')
                print(f'OpenDate New: {open_date}')
                return open_date_origin
            open_date = sched_format_datetime(open_date)
            if not open_date:
                return open_date_origin

def sched_return_rate_save(data: Dict[str, Any] = {}, duration_data: Dict[str, Any] = {}) -> None:
    with RedisContextManager() as r:
        for k in data:
            r.hset('return-rate', k, str(data[k]))
            for e in data[k]:
                duration = e.get('Duration')
                if not duration:
                    continue
                if duration not in duration_data:
                    duration_data[duration] = {}
                if k not in duration_data[duration]:
                    duration_data[duration][k] = []
                duration_data[duration][k].append(e)
        for k in duration_data:
            r.hset('return-rate-duration', k, str(duration_data[k]))

def sched_return_rate_update(data: Dict[str, Any] = {}, not_founds: List[str] = []) -> tuple:
    for e in get_bts_projects():
        project_name = '_'.join(e.split('_')[:-1])
        try:
            with RedisContextManager(decode_responses=True) as r:
                query = r.hget('issues', project_name)
            if not query:
                not_founds.append(project_name)
                continue
            data[project_name] = []
            for raw in loads(query.replace(r'\r\n', r'\n')):
                if (raw.get('DefectID') and raw.get('OpenDate')
                    and raw.get('Submitter') and raw.get('DefectClass')):
                    return_rate = dict(ReturnRate(**{
                        **raw,
                        "OpenDate": sched_find_datetime(raw["OpenDate"]),
                        "Duration": sched_parse_duration(raw["OpenDate"]),
                        "Comments": []
                    }))
                    if raw.get('Comments'):
                        user_regexp = DATE_REGEXP + r'|\:\>'
                        comments = [
                            {
                                "user"    : sub(user_regexp, '', i).strip(),
                                "datetime": search(DATE_REGEXP, i).group()
                            }
                            for i in raw["Comments"].splitlines()
                            if search(DATE_REGEXP, i)
                        ]
                        return_rate = { **return_rate, "Comments": comments }
                    data[project_name].append(return_rate)
                else:
                    data[project_name].append({})
        except Exception as err:
            print(f'Project full name: "{e}" occurred unexpected error:')
            print(f'Detail: {err}\n')
    return (data, not_founds)

def sched_scaler(numerator: int, denominator: int) -> float:
    return float(f'{float(numerator / denominator) * 100:.2f}')

def sched_tag_at(tag: Type[ProjectTag], index: int = 1) -> int:
    dt = datetimer(tag.commit["created_at"].split('.')[0])
    date = datetimer(dt, ts=False, date=True).split('-')[index]
    return int(date) if index == 1 else date

def sched_parse_requirement(data: Dict[str, Any], regexp: str) -> Dict[str, Any]:
    resp = { "quantity": 0, "scripts": {} }
    for k in data:
        if search(regexp, k):
            resp["quantity"] += len(data[k])
            resp["scripts"][k] = [
                { "tag": i["name"], "datetime": i["created_at"] } for i in data[k]
            ]
    return resp

def sched_kpi_achievement_save(db_maps: Dict[str, Any]) -> None:
    with RedisContextManager() as r:
        for k in db_maps:
            r.hset(f'script-management-kpi-{k}', KpiConfig().duration, str(db_maps[k]))

def sched_kpi_achievement_update() -> Dict[str, Any]:
    projects = getProjects(**ProjectScriptRule().dict())
    achieve = WorkAchievement(KpiConfig().duration, projects)
    # retrieve script released tags by specified duration
    commit_tags = achieve.group_by_developer()
    # create the tuple data with script name and it owns developer
    script_owns = [ ( e["script_name"], e["developer"] ) for e in flatten(commit_tags.values()) ]
    # create the set data for valid tag scripts
    script_own_names = { i for i, _ in script_owns }
    script_tags = { e.name: tags for e in projects if (tags := e.tags.list(get_all=True)) }
    script_tagged: Dict[str, List[Dict[str, str]]] = {}
    for k in script_tags:
        tag_raws = [
            e for e in script_tags[k]
            if sched_tag_at(e, 0) == KpiConfig().year
            and sched_tag_at(e) in HALFYEAR_MAPS[KpiConfig().half_year]
        ]
        if not tag_raws: continue
        script_tagged[k] = []
        for e in tag_raws:
            script_tagged[k].append({
                "name"      : e.name,
                "created_at": e.commit["created_at"].split('.')[0]
            })
    requirement = {
        e: sched_parse_requirement(script_tagged, '^SIT')
        if e == 'Common'
        else sched_parse_requirement(script_tagged, f'^{e}')
        for e in CUSTOMERS
    }
    with RedisContextManager(decode_responses=True) as r:
        keys = r.hkeys(u_name := MissionDB.update)
        missions = { k: json_parse(r.hget(u_name, k)) for k in keys }
    kpi_new = { "kpi_status": "new" }
    kpi_maps = {
        k: dict(KpiData(**{
            **missions[k],
            "time_saving" : float(missions[k]["time_saving"]),
            "bkm_quantity": len(missions[k]["bkms"])
        }))
        for k in missions if int(missions[k].get('progress')) >= 100
        or k in script_own_names
    }
    if KpiConfig().half_year == 'H2':
        query_duration = f'{KpiConfig().year}-H1'
    else:
        query_duration = f'{int(KpiConfig().year) - 1}-H2'
    with RedisContextManager() as r:
        query = r.hget(ReportDB.testcase, query_duration)
    if query:
        kpi_prev = json_parse(query)
        this = {
            k: dict(KpiData(**{
                **(v := kpi_maps[k]),
                "bkms": ({
                    i: { **v["bkms"][i], "kpi_status": "old" }
                    if i in v["bkms"] and i in kpi_prev[k]["bkms"]
                    else v["bkms"][i] | kpi_new
                    if i in v["bkms"] and i not in kpi_prev[k]["bkms"]
                    else { **kpi_prev[k]["bkms"][i], "kpi_status": "del" }
                    for i in set(v["bkms"] | kpi_prev[k]["bkms"])
                } if k in kpi_prev
                else { x: v["bkms"][x] | kpi_new for x in v["bkms"] })
            }))
            for k in kpi_maps if k in script_tagged
        }
    else:
        this = {
            k: dict(KpiData(**{
                **(v := kpi_maps[k]),
                "bkms": { x: v["bkms"][x] | kpi_new for x in v["bkms"] }
            }))
            for k in kpi_maps if k in script_tagged
        }
    # initialize KPI source data with developer name
    kpi_source = {
        e: { "scripts": {}, "bkms_num": [], "time_num": [] }
        for e in sorted(commit_tags.keys())
    }
    # mapping data between of kpi_source(variable) and this(variable)
    for e in [ { **this[key], "script_name": key } for key in this ]:
        for _script, _developer in script_owns:
            if e.get('script_name') != _script: continue
            kpi_source[_developer]["scripts"] |= {
                _script: { "bkms_num": e["bkm_quantity"], "time_num": e["time_saving"] }
            }
            kpi_source[_developer]["bkms_num"].append(e["bkm_quantity"])
            kpi_source[_developer]["time_num"].append(e["time_saving"])
    # summarize work achievement with kpi_source(variable) for building property
    achievements = {
        k: {
            "scripts" : kpi_source[k]["scripts"],
            "bkms_num": sum(kpi_source[k]["bkms_num"]),
            "time_num": sum(kpi_source[k]["time_num"]),
            "reqs_num": len(commit_tags[k])
        }
        for k in kpi_source
    }
    sum_timesaving = sum_bkm_quantity = 0
    for e in this.values():
        sum_timesaving += e["time_saving"]
        sum_bkm_quantity += e["bkm_quantity"]
    summary = {
        "script_num"      : (script_num := len(this)),
        "time_num"        : sum_timesaving,
        "bkm_num"         : sum_bkm_quantity,
        "script_threshold": KpiConfig().script,
        "time_threshold"  : KpiConfig().timesaving,
        "bkm_threshold"   : KpiConfig().coverage,
        "scripts"         : sched_scaler(script_num, KpiConfig().script),
        "timesavings"     : sched_scaler(sum_timesaving, KpiConfig().timesaving),
        "coverages"       : sched_scaler(sum_bkm_quantity, KpiConfig().coverage)
    }
    return {
        "requirement": requirement,
        "testcase"   : this,
        "summary"    : summary,
        "achievement": achievements
    }

def sched_kpi_summary_save(data: Dict[str, Any]) -> None:
    with RedisContextManager() as r:
        r.hset(ReportDB.kpi_list, KpiConfig().duration, str(data))

def sched_kpi_summary_update() -> Dict[str, Any]:
    automation = AutomationSummary()
    automation.source()
    automation.summary_ares()
    key_map: Dict[str, str] = {
        "requirement": "requirement",
        "testcase"   : "testcase",
        "summary"    : "kpi",
        "achievement": "achievement"
    }
    rebuild: Dict[str, Dict[str, dict]] = {}
    with RedisContextManager(decode_responses=True) as r:
        for key in key_map:
            if not (keys := r.hkeys(name := f'script-management-kpi-{key}')):
                continue
            rebuild[key_map[key]] = {}
            for k in sorted(keys, reverse=True):
                rebuild[key_map[key]][k] = json_parse(r.hget(name, k))
    return { "summary": automation.summary_sms() } | rebuild

@timeit
def main() -> None:
    args_parser()
    if ARGS.update:
        print(' * Schedule Rule: [*/5 * * * *]')
        print(' * Updating Return-Rate by issues of Redis..')
        return_rate_data, project_not_found = sched_return_rate_update()
        sched_return_rate_save(return_rate_data)
        print(' * Listing Project valid in issues:')
        print(dumps(sorted(return_rate_data), indent=4) + '\n')
        print(' * Listing Project not found in issues:')
        print(dumps(sorted(project_not_found), indent=4) + '\n')
    if ARGS.summary:
        print(' * Schedule Rule: [*/30 * * * *]')
        print(f' * Caching TA-Team Work Achievement (Duration: {KpiConfig().duration})..')
        kpi_achievements = sched_kpi_achievement_update()
        sched_kpi_achievement_save(kpi_achievements)
        print(' * Renewing KPI list from work achievement..')
        kpi_summary = sched_kpi_summary_update()
        sched_kpi_summary_save(kpi_summary)
        for k in kpi_summary:
            print(f'\n * Show {k.capitalize()} cache data:')
            print(dumps(kpi_summary[k], indent=4) + '\n')

if __name__ == '__main__':
    main()
