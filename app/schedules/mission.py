#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('..')
sys.path.append('../library')

from library.params import json_parse
from library.openldap import LdapHandler
from library.config import url_to_ares, template_path, ARES_ENDPOINT
from library.mailer import EMAIL_ADMINS, Jinja2Templates, EmailManager
from library.schemas import Schedules, RedisDB, MissionDB, MissionInfo
from library.helpers import timeit, BackendPrint
from library.cacher import RedisContextManager, get_script_customers, get_customers_by_name
from library.gitlabs import (ProjectScriptRule, parse_project_tag_at,
    parse_project_commit_at, getReadme, getProjects)
from library.moment import (Holiday, datetimer, datetime_data,
    date_autocomplete, date_attenuator, date_slice, date_day_remains)
from library.readme import (get_readme_content, get_readme_associates,
    get_ver_by_readme, get_readme_coverage, get_readme_validation,
    get_readme_testing_methodology, get_readme_reports, get_readme_estimate)

from json import dumps
from functools import wraps
from traceback import format_exc
from collections import defaultdict
from asyncio import run as async_run
from pydantic import BaseModel, EmailStr
from pydantic.error_wrappers import ValidationError
from argparse import ArgumentParser, RawTextHelpFormatter, Namespace
from typing import Any, List, Dict, Callable, Optional, TypeVar, Union

LDAP = LdapHandler()
postman = EmailManager()

TEMPLATE = Jinja2Templates(directory=f'{template_path.mail}/')
EXCLUDE_SCRIPT = [ 'SIT-Script-Collections', 'SIT-Script-Validator' ]

class Authors(BaseModel):
    author : Optional[str] = 'TA-Team'
    phase  : Optional[str] = 'release'

class MoreData(Authors):
    schedules : Optional[Dict[str, str]] = {}
    status    : Optional[str]  = 'release'
    current   : Optional[str]  = 'TA-Team'
    requester : Optional[str]  = ''
    comment   : Optional[str]  = ''

class ReleaseHistory(Authors):
    comment  : Optional[str] = 'The script has been released.'
    progress : Union[int, str] = 100

class MissionBasic(BaseModel):
    script_name : str
    current     : Optional[str]  = ''
    author      : Optional[str]  = ''
    priority    : Optional[str]  = 'P2'
    link        : Optional[str]  = ''
    schedules   : Optional[Dict[str, str]] = {}

class MissionMerge(MissionBasic):
    status      : str
    ta_manager  : Optional[str]  = ''
    manager     : Optional[str]  = ''
    raw         : Optional[Dict[str, Any]]  = {}
    history     : Optional[Dict[str, dict]] = {}
    last_update : Optional[Dict[str, dict]] = {}

class MissionEmail(MissionBasic):
    recipients : List[EmailStr]
    cc         : Optional[List[EmailStr]]  = []
    comment    : Optional[Dict[str, Any]] = {}
    last_date  : Optional[str]  = ''
    overdays   : Union[int, str] = 0

class WeeklyReport(BaseModel):
    progress     : Union[int, str] = 0
    status_color : Dict[str, Union[int, str]]
    plan         : Dict[str, Any]
    req_desc     : Optional[str] = ''

def args_parser() -> Namespace:
    global ARGS
    desc = 'FastAPI CronJob:\nHandling script mission from GitLab.'
    parser = ArgumentParser(description=desc, formatter_class=RawTextHelpFormatter)
    parser.add_argument('-s', '--sync', action='store_true',
                        help='synchronize mission from GitLab project')
    parser.add_argument('-r', '--remind', action='store_true',
                        help='sending mission due email notification')
    parser.add_argument('-w', '--weekly', action='store_true',
                        help='sending weekly report email notification')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force to operating specified cronjob')
    ARGS = parser.parse_args()
    return ARGS

EMAIL_CATCH_T = TypeVar('EMAIL_CATCH_T')

def sched_catch_email_handle(func: Callable[..., EMAIL_CATCH_T]) -> Callable[..., EMAIL_CATCH_T]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Union[EMAIL_CATCH_T, Dict[str, str]]:
        try:
            return await func(*args, **kwargs)
        except Exception as err:
            BackendPrint.error(str(err))
            return { "message": "Sending E-mail Failed", "detail": str(err) }
    return wrapper

def sched_safety_progress(data: Dict[str, dict], key: str) -> int:
    defaults = defaultdict(dict, data)
    progress = defaultdict(int, defaults[key])
    return int(progress["progress"])

def sched_script_mission_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
    with RedisContextManager(decode_responses=True) as r:
        c_keys = r.hkeys(c_name := MissionDB.create)
        u_keys = r.hkeys(u_name := MissionDB.update)
        create = { k: json_parse(r.hget(c_name, k)) for k in c_keys }
        update = { k: json_parse(r.hget(u_name, k)) for k in u_keys }
    return (create, update)

def sched_script_mission_save(data: Dict[str, dict]) -> None:
    with RedisContextManager() as r:
        for name in [ MissionDB.update, RedisDB.backup ]:
            _ = [ r.hset(name, k, str(data[k])) for k in data ]

def sched_script_mission_mgmt() -> tuple:
    create, update = sched_script_mission_data()
    cleans = [ e["script_name"] for e in create.values() if int(e["progress"]) >= 100 ]
    return ({ k: create[k] for k in create if k not in cleans }, update)

def sched_script_mission_sync(resp: Dict[str, Any] = {}) -> Dict[str, dict]:
    data_create, data_update = sched_script_mission_mgmt()
    projects = getProjects(**ProjectScriptRule().dict())
    project_maps = defaultdict(lambda: 100)
    for p in projects:
        _ = project_maps[p.name]
        if data_update.get(p.name):
            project_maps[p.name] = sched_safety_progress(data_update, p.name)
    projects_allowed = [
        k for k in project_maps
        if project_maps[k] == 100 and k not in EXCLUDE_SCRIPT
        and k not in data_create
    ]
    customers = get_script_customers()
    for p in projects:
        if p.name not in projects_allowed:
            continue
        readme = getReadme(p)
        origin = data_update.get(p.name)
        try:
            associates = get_readme_associates(readme)
            history = { parse_project_tag_at(p): ReleaseHistory().dict() }
            resp[p.name] = MissionInfo(**{
                "link"          : url_to_ares(p.name, 'update'),
                "repository"    : p.web_url,
                "script_name"   : p.name,
                "script_version": get_ver_by_readme(by_project=p),
                "customers"     : get_customers_by_name(p.name, customers),
                "coverages"     : get_readme_coverage(readme),
                "progress"      : project_maps.get(p.name),
                "lte_name"      : associates.get('lte_name'),
                "te_name"       : associates.get('te_name'),
                "owner"         : associates.get('owner'),
                "developer"     : associates.get('developer'),
                "te_data"       : get_readme_validation(readme),
                "description"   : get_readme_content(readme, '## Description'),
                "bkms"          : get_readme_testing_methodology(readme),
                "when_to_use"   : get_readme_content(readme, '## When to use ?'),
                "ta_manager"    : LDAP.get_ta_manager(),
                "time_saving"   : get_readme_estimate(readme),
                "history"       : origin.get('history') if origin else history,
                "modified_date" : parse_project_commit_at(p),
                "log_types"     : get_readme_reports(readme),
                **(MoreData(**origin).dict() if origin else MoreData().dict())
            }).dict()
        except Exception as err:
            print(f'ERROR: {err}')
            print(format_exc())
            print(f'PROJECT: {p.name} parsed README found invalid syntex.')
    return resp

def sched_datetime_moment() -> Dict[str, Any]:
    dt = datetime_data()
    moment = {
        "timestamp": datetimer(dt["dt"]),
        "datetime" : datetimer(dt["ts"], ts=False, date=True)
    }
    moment["weekday"] = datetimer(moment["datetime"], weekday=True)
    moment["current"] = moment["datetime"].split('T')[0]
    yyyy = int(moment["current"].split('-')[0])
    moment["holiday"] = list(Holiday.getdates(yyyy, False))
    return moment

def sched_script_mission_merge(
    excludes: List[str] = [], missions: List[dict] = []) -> List[dict]:
    data_create, data_update = sched_script_mission_data()
    for e in [ *data_create.values(), *data_update.values() ]:
        try:
            mission = MissionInfo(**e)
        except ValidationError as err:
            print(f' * Mission: {e.get("script_name")} data parsed error:')
            print(f'Error detail: {err}\n')
            continue
        if mission.status in excludes or not mission.history:
            continue
        history_last = sorted(mission.history)[-1]
        history_date = history_last.replace(' ', 'T')
        missions.append(MissionMerge(**{
            **mission.dict(),
            "raw"        : mission.dict(),
            "manager"    : mission.owner,
            "last_update": { history_date: mission.history[history_last] }
        }).dict())
    return missions

def sched_parse_datetime(mission: MissionMerge, current_ts: float) -> Dict[str, Any]:
    parse_date = { "ldate": list(mission.last_update).pop() }
    last_time = parse_date["ldate"].split('T')[-1]
    last_date = [
        f'{mission.schedules[i]}T{last_time}'
        for i in [ 'development', 'validation' ]
        if mission.status == i and i in mission.schedules
    ]
    parse_date["last_date"] = last_date[-1] if last_date else parse_date["ldate"]
    parse_date["latest_ts"] = float(datetimer(parse_date["last_date"]))
    remain_ts = (current_ts - parse_date["latest_ts"])
    parse_date["remain_day"] = int(remain_ts / 86400)
    parse_date["current_ts"] = current_ts
    return parse_date

def sched_history_date(history: Dict[str, str], phase: str) -> str:
    date = [ k for k in history if history[k]["phase"] == phase ]
    return sorted(date)[-1].replace(' ', 'T') if date else ''

@sched_catch_email_handle
async def sched_script_mission_due_email(mission: MissionEmail) -> Dict[str, str]:
    priority = postman.get_header_by_priority(mission.priority)
    subject = f'Script Mission Remind - {mission.script_name} [Due]'
    context = {
        "request"      : {},
        "mission"      : mission.dict(),
        "subject"      : subject,
        "ares_endpoint": ARES_ENDPOINT
    }
    msg = EmailManager.schema(subject, mission.recipients, mission.cc, priority)
    content = TEMPLATE.TemplateResponse('mission-remind.html', context=context)
    msg.html = content.template.render(context)
    await EmailManager.safety_send(msg, postman.configure())
    return { "message": "Remind Successfully", "detail": "Sent O.K." }

@sched_catch_email_handle
async def sched_weekly_report_email(data: Dict[str, Any]) -> Dict[str, str]:
    date = data["CST"]["datetime"].split('T')[0].replace('-', '/')
    subject = f'TA Weekly Report {date} Merge'
    context = { "request": {}, "reports": data, "date": date }
    members = [ e.mail for e in LDAP.get_members('SMS_Recipients', get_raw=True) ]
    cc = [ f'{LDAP.get_ta_manager()}@inventec.com', *EMAIL_ADMINS ]
    msg = EmailManager.schema(subject, members + EMAIL_ADMINS, cc)
    content = TEMPLATE.TemplateResponse('weekly-report.html', context=context)
    msg.html = content.template.render(context)
    await EmailManager.safety_send(msg, postman.configure())
    return { "message": "Report Successfully", "detail": "Sent O.K." }

def sched_script_mission_remind() -> Dict[str, Any]:
    """
    This cronjob is used to send E-amil with specified
    mission, it works on workday excepts any holiday.
    """
    moment = sched_datetime_moment()
    resp = { "list": [], "message": f"Skipped Weekday {moment['weekday']}" }

    # skipping on exclude days or any weekend and holiday
    if not ARGS.force:
        if moment["holiday"] and moment["current"] in moment["holiday"]:
            return resp
        if not moment["holiday"] and moment["weekday"] in [ 'Saturday', 'Sunday' ]:
            return resp

    resp = { "list": [], "message": "Job Successfully" }
    for e in sched_script_mission_merge([ 'release' ]):
        try:
            mission = MissionMerge(**e)
            recipients = mission.current.split(';')
            ccs = [ *mission.author.split(';'), *recipients ]
            current_ts = float(moment["timestamp"])
            parse_date = sched_parse_datetime(mission, current_ts)
            if parse_date["remain_day"] == 2:
                ccs = [ mission.manager, *ccs ]
            elif parse_date["remain_day"] > 2:
                ccs = [ mission.ta_manager, mission.manager, *ccs ]
            else:
                continue
            data = MissionEmail(**{
                **e,
                "recipients": EmailManager.mailize(recipients),
                "cc"        : EmailManager.mailize(ccs),
                "overdays"  : parse_date["remain_day"],
                "last_date" : parse_date["last_date"],
                "comment"   : mission.last_update.get(parse_date["ldate"])
            })
            request = data.dict()
            response = async_run(sched_script_mission_due_email(data))
            resp["list"].append({ "request": request, "response": response })
        except Exception as err:
            response = { "message": "Remind Failured", "detail": str(err) }
            resp["list"].append({ "request": {}, "response": response })
    return resp

def sched_weekly_report_remind(threshold: int = 1) -> Dict[str, Any]:
    """
    This cronjob is used to send E-amil with all mission
    which is ongoing, then combine into MS-PPT syntex of
    weekly report (SIT staff meeting).
    """
    moment = sched_datetime_moment()
    resp = { "tasks" : [] }

    # skipping on any weekend and holiday
    if moment["current"] in moment["holiday"] and not ARGS.force:
        return { "message": f"Skipped Holiday {moment['weekday']}" }
    elif moment["weekday"] != 'Tuesday' and not ARGS.force:
        return { "message": "On Tuesday Only" }

    """
    Fullfill schedule with mission's data and the schedule
    deadline which is depends on start date or finish date.
    It'll also retrieve the last datetime updated history.
    """
    for e in sched_script_mission_merge():
        schedules = Schedules(**e.get('schedules'))
        if not schedules.development:
            continue
        progress = e["last_update"][sorted(e["last_update"])[-1]]["progress"]
        history = e.get('history')

        # retrieve basic date to be criterion
        search_confirm = sched_history_date(history, 'confirm')
        if not search_confirm:
            continue
        search_confirm = search_confirm.split('T')[0]
        schedule_start = date_slice(search_confirm)
        schedule_end = date_slice(schedules.release)
        valid_start = date_attenuator(schedules.development, days=1).split('T')
        valid_end = date_attenuator(schedules.validation, days=1).split('T')
        histories = [ k for k in history if history[k]["phase"] == 'create' ]

        # generate a new plan and merge with original data
        data = {
            **e,
            "plan": {
                "schedule_start"   : schedule_start,
                "schedule_end"     : schedule_end,
                "development_start": schedule_start,
                "development_end"  : date_slice(schedules.development),
                "validation_start" : date_slice(valid_start[0]),
                "validation_end"   : date_slice(schedules.validation),
                "release_start"    : date_slice(valid_end[0]),
                "release_end"      : schedule_end,
                "schedule_duration_days": date_day_remains(
                    datetimer(date_autocomplete(search_confirm)),
                    datetimer(date_autocomplete(schedules.release))
                )
            },
            "progress": int(progress),
            "req_desc": history[sorted(histories)[-1]]["comment"]
        }

        """
        Task progress status light:
            - W (white) : not happend event or on planning
            - G (green) : work in progress
            - Y (yellow): procedural contains risk
            - R (red)   : reach schedule deadline
            - C (blue)  : task was completed
        """
        data["status_color"] = { "last": "W", "this": "W" }

        # stauts corresponding map
        status_maps = {
            20 : "confirm",
            40 : "development",
            50 : "validation",
            75 : "edit-readme",
            80 : "readme",
            90 : "pre-release",
            100: "release"
        }
        status = status_maps[data["progress"]]

        # status: confirm, 20%
        if data["progress"] == 20:
            dt = sched_history_date(data["history"], status)
            overdays = date_day_remains(datetimer(dt), moment["timestamp"])
            data["status_color"] = (
                { "last": "W", "this": "G" } if overdays <= threshold
                else { "last": "G", "this": "G" }
            )

        # status: development 40%, validation 50%, pre-release 90%, release 100%
        elif data["progress"] in [ 40, 50, 90, 100 ]:
            dt = (
                sched_history_date(data["history"], 'readme-agree')
                if data["progress"] == 90
                else date_autocomplete(data["schedules"][status])
            )
            overdays = date_day_remains(datetimer(dt), moment["timestamp"])
            data["status_color"] = { "last": "G", "this": "G" }
            if overdays <= threshold:
                data["status_color"] = { "last": "W", "this": "G" }
            if data["progress"] in [ 90, 100 ]:
                data["status_color"] = { "last": "C", "this": "W" }
                if overdays <= threshold:
                    data["status_color"] = { "last": "G", "this": "C" }

        # status: edit-readme 75%, readme 80%
        elif data["progress"] in [ 75, 80 ]:
            dt = sched_history_date(data["history"], 'validation-pass')
            overdays = date_day_remains(datetimer(dt), moment["timestamp"])
            data["status_color"] = { "last": "G", "this": "G" }
            if overdays <= threshold:
                data["status_color"] = { "last": "W", "this": "G" }

        # overdays large than schedule duration, turn light to RED
        if overdays >= data["plan"]["schedule_duration_days"]:
            data["status_color"] = { "last": "R", "this": "R" }
        data["status_color"]["overdays"] = overdays

        # filter the data during 7 days only
        timestamp = float(moment.get('timestamp'))
        parse_date = sched_parse_datetime(MissionMerge(**data), timestamp)
        if parse_date.get('remain_day') <= 7:
            resp["tasks"].append(data)

    request = { **resp, "CST": moment }
    resp["response"] = async_run(sched_weekly_report_email(request))
    resp["tasks"] = [ WeeklyReport(**e).dict() for e in resp["tasks"] ]
    return resp

@timeit
def main() -> None:
    args_parser()
    if ARGS.sync:
        print(' * Schedule Rule: [*/6 * * * *]')
        print(' * Synchronize mission from GitLab project:')
        missions = sched_script_mission_sync()
        sched_script_mission_save(missions)
        print(dumps(sorted(missions), indent=4) + '\n')
    if ARGS.remind:
        print(' * Schedule Rule: [0 8 * * *]')
        print(' * Reminding due mission schedulely:')
        print(dumps(sched_script_mission_remind(), indent=4) + '\n')
    if ARGS.weekly:
        print(' * Schedule Rule: [8 0 * * 2]')
        print(' * Sending weekly report schedulely:')
        print(dumps(sched_weekly_report_remind(), indent=4) + '\n')

if __name__ == '__main__':
    main()
