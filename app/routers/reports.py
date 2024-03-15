#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.iteration import flatten
from library.config import ARES_ENDPOINT
from library.cacher import RedisContextManager
from library.helpers import catch_except_retry
from library.achievement import WorkAchievement
from library.gitlabs import ProjectScriptRule, getProjects
from library.params import json_parse, response_interpreter
from library.schemas import ReportDB, ReportMap, current_duration
from library.achievement import WorkAchievement, AutomationSummary
from library.bts import dict_search, get_bts_return_rate, get_bts_object

from requests import get
from datetime import datetime
from pydantic import BaseModel
from starlette.responses import JSONResponse
from eventlet import Timeout as monkey_timeout
from typing import Any, Dict, List, Annotated, Optional
from fastapi import APIRouter, HTTPException, Response, Query

router = APIRouter()

QUERY_DURATION_HALF = Query(
    default=current_duration().duration,
    description='Require a `Half Year Duration`',
    regex='^2\d{3}\-H[1-2]$'
)
QUERY_PROJECT = Query(..., description='Require a `Project Name`')

class Config(BaseModel):
    begin         : Optional[dict] = {}
    end           : Optional[dict] = {}
    project_begin : Optional[dict] = {}
    project_end   : Optional[dict] = {}

def reports_query_quater_config(minus: int = 0) -> Query:
    duration = current_duration()
    calculator = int(duration.quater.split('Q')[-1]) - minus
    default_year = int(duration.year) - 1 if calculator < 1 else duration.year
    default_quater = f'Q{4 if calculator < 1 else calculator}'
    return Query(
        default=f'{default_year}-{default_quater}',
        description='Require a `Quater Duration`',
        regex='^2\d{3}\-Q[1-4]$'
    )

QUERY_QUATER_BEGIN = reports_query_quater_config(1)
QUERY_QUATER_END = reports_query_quater_config()
QUERY_YEAR_BEGIN = Query(datetime.now().year - 1, description='`Begin Year`')
QUERY_YEAR_END = Query(datetime.now().year, description='`End Year`')

def reports_return_rate_validate(data: Config, project: str, begin: str, end: str) -> dict:
    try:
        assert data.begin, f'{begin} Data Not Found'
        assert data.end, f'{end} Data Not Found'
        data.project_begin = data.begin.get(project)
        data.project_end = data.end.get(project)
        assert data.project_begin, f'{begin} {project} Project Not Found'
        assert data.project_end, f'{end} {project} Project Not Found'
    except Exception as e:
        if 'Project Not Found' in str(e):
            err = f'{str(e)}, Support Project: {sorted({ *data.begin, *data.end })}'
        raise HTTPException(status_code=404, detail=str(err)) from e
    return { "d1": data.project_begin, "d2": data.project_end }

def reports_return_rate_prerequisite(projects: dict, data: dict = {}) -> Dict[str, Any]:
    for k in projects:
        data[k] = {
            "defect_class"       : get_bts_object(projects[k], 'DefectClass'),
            "submitter"          : get_bts_object(projects[k], 'Submitter'),
            "project_return_rate": get_bts_return_rate(projects[k])
        }
    for a in projects:
        for b in [
                { "main_key": "submitter", "sub_key": "Submitter" },
                { "main_key": "defect_class", "sub_key": "DefectClass" }
            ]:
            ls = [ *data["d1"][b["main_key"]], *data["d2"][b["main_key"]] ]
            data[a][b["main_key"]] = [
                [ k for k in data[a][b["main_key"]] if i in k[b["sub_key"]] ][-1]
                if i in [ j[b["sub_key"]] for j in data[a][b["main_key"]] ]
                else {
                    b["sub_key"]  : i,
                    "comments"    : 0,
                    "defect_count": 0,
                    "return_rate" : 0.0,
                    "single_close": 0
                }
                for i in { e[b["sub_key"]] for e in ls }
            ]
    return data

@catch_except_retry()
def reports_get_kpi_raws(annuals: List[int], keys: List[str]) -> Dict[str, Any]:
    """
    Retrieve raw data with the latest duration H2 of annual,
    or if duration H2 not found then serach by H1 instead.
    """
    with RedisContextManager() as r:
        raw = {
            i: { j: r.hget(f'script-management-kpi-{j}', f'{i}-H2') for j in keys }
            for i in annuals
        }
        return {
            i: raw.get(i) if raw[i].get(keys[0]) else
            { j: r.hget(f'script-management-kpi-{j}', f'{i}-H1') for j in keys }
            for i in annuals
        }

@catch_except_retry()
def reports_ares_api_get(route: str, timeout: int = 10) -> Dict[str, Any]:
    with monkey_timeout(timeout):
        resp = get(f'http://{ARES_ENDPOINT}/api/v1/{route}')
    return resp.json() if resp.status_code < 400 else {}

@router.get('/api/v1/reports/requirement', tags=['Reports'])
def get_requirement_by_gitlab(
    duration: Annotated[str, QUERY_DURATION_HALF] = QUERY_DURATION_HALF):
    projects = getProjects(**ProjectScriptRule().dict())
    achieve = WorkAchievement(duration, projects)
    return JSONResponse(status_code=200, content=achieve.group_by_developer())

@router.get('/api/v1/reports/kpi-summary', tags=['Reports'])
def get_script_kpi_summary(
    duration: Annotated[str, QUERY_DURATION_HALF] = QUERY_DURATION_HALF):
    with RedisContextManager() as r:
        query = r.hget(ReportDB.kpi_list, duration)
    if not query:
        raise HTTPException(status_code=404, detail=f'{duration} Not Found')
    with RedisContextManager(decode_responses=True) as r:
        resp = { **json_parse(query), "list": sorted(r.hkeys(ReportDB.kpi_list), reverse=True) }
    return JSONResponse(status_code=200, content=resp)

@router.get('/api/v1/reports/return-rate/get', tags=['Reports'])
def get_return_rate_by_project(
    project: Annotated[str, QUERY_PROJECT] = QUERY_PROJECT) -> JSONResponse:
    with RedisContextManager() as r:
        query = r.hget('return-rate', project)
    if not query:
        raise HTTPException(status_code=404, detail=f'{project} Not Found')
    return JSONResponse(status_code=200, content=json_parse(query))

@router.get('/api/v1/reports/return-rate/duration', tags=['Reports'])
def get_return_rate_of_duration_by_project(
    response: Response,
    project : Annotated[str, QUERY_PROJECT] = QUERY_PROJECT,
    begin   : Annotated[str, QUERY_QUATER_BEGIN] = QUERY_QUATER_BEGIN,
    end     : Annotated[str, QUERY_QUATER_END] = QUERY_QUATER_END) -> JSONResponse:
    keys = { "begin": begin, "end": end }
    with RedisContextManager() as r:
        query = { k: r.hget(ReportDB.duration, keys[k]) for k in keys }
    data = Config(**{ k: json_parse(query[k]) if query[k] else {} for k in query })
    project_data = reports_return_rate_validate(data, project, begin, end)
    entry = reports_return_rate_prerequisite(project_data)
    rebuild = {
        "defect_class": [
            {
                "DefectClass_1": dict_search(
                    entry["d1"]["defect_class"],
                    'DefectClass',
                    e["DefectClass"],
                    e["DefectClass"]
                ),
                "comments_1": dict_search(
                    entry["d1"]["defect_class"],
                    'comments',
                    e["comments"],
                    e["DefectClass"]
                ),
                "defect_count_1": dict_search(
                    entry["d1"]["defect_class"],
                    'defect_count',
                    e["defect_count"],
                    e["DefectClass"]
                ),
                "return_rate_1": dict_search(
                    entry["d1"]["defect_class"],
                    'return_rate',
                    e["return_rate"],
                    e["DefectClass"]
                ),
                "single_close_1": dict_search(entry["d1"]["defect_class"],
                    'single_close',
                    e["single_close"],
                    e["DefectClass"]
                ),
                "DefectClass_2" : e["DefectClass"],
                "comments_2"    : e["comments"],
                "defect_count_2": e["defect_count"],
                "return_rate_2" : e["return_rate"],
                "single_close_2": e["single_close"],
                "return_rate_comparison": round(
                    (e["return_rate"] - dict_search(
                        entry["d1"]["defect_class"],
                        'return_rate',
                        e["return_rate"],
                        e["DefectClass"]
                    )) * 100
                )
            }
            for e in entry["d2"]["defect_class"]
        ],
        "submitter": [
            {
                "Submitter_1": dict_search(
                    entry["d1"]["submitter"],
                    'Submitter',
                    e["Submitter"],
                    e["Submitter"]
                ),
                "comments_1": dict_search(entry["d1"]["submitter"],
                    'comments',
                    e["comments"],
                    e["Submitter"]
                ),
                "defect_count_1": dict_search(entry["d1"]["submitter"],
                    'defect_count',
                    e["defect_count"],
                    e["Submitter"]
                ),
                "return_rate_1": dict_search(entry["d1"]["submitter"],
                    'return_rate',
                    e["return_rate"],
                    e["Submitter"]
                ),
                "single_close_1": dict_search(entry["d1"]["submitter"],
                    'single_close',
                    e["single_close"],
                    e["Submitter"]
                ),
                "Submitter_2"   : e["Submitter"],
                "comments_2"    : e["comments"],
                "defect_count_2": e["defect_count"],
                "return_rate_2" : e["return_rate"],
                "single_close_2": e["single_close"],
                "return_rate_comparison": round(
                    (e["return_rate"] - dict_search(
                        entry["d1"]["submitter"],
                        'return_rate',
                        e["return_rate"],
                        e["Submitter"]
                    )) * 100
                )
            }
            for e in entry["d2"]["submitter"]
        ],
        "project_return_rate_1": entry["d1"]["project_return_rate"],
        "project_return_rate_2": entry["d2"]["project_return_rate"],
        "project_return_rate_comparison": round(
            (entry["d2"]["project_return_rate"] - entry["d1"]["project_return_rate"]) * 100
        )
    }
    response_interpreter(response)
    return rebuild

@router.get('/api/v1/reports/script-summary', tags=['Reports'])
def get_script_annual_automation_summary(response: Response,
    begin: Annotated[int, QUERY_YEAR_BEGIN] = QUERY_YEAR_BEGIN,
    end  : Annotated[int, QUERY_YEAR_END] = QUERY_YEAR_END):
    annuals = [ begin, end ]
    report = AutomationSummary()
    report.source()
    bkms = report.src_data.get('list')
    raw = reports_get_kpi_raws(annuals, db_keys := [ 'list', 'testcase' ])
    invalid = [ [ ( j, i, raw[j].get(i) ) for j in annuals ] for i in db_keys ]
    if nothings := [ e for e in flatten(invalid) if not e[2] ]:
        detail = f'{nothings[0][0]} {nothings[0][1].capitalize()} Not Found'
        raise HTTPException(status_code=404, detail=detail)

    # create automated complete data by customer
    sum_begin = json_parse(raw[begin]["list"])["summary"]
    sum_end   = json_parse(raw[end]["list"])["summary"]
    customers = { begin: sum_begin.get('cust'), end: sum_end.get('cust') }
    functions = { begin: sum_begin.get('func'), end: sum_end.get('func') }

    # group by customer data to create SMS automated complete
    _tcs = []
    for annual in annuals:
        _tcs_data = json_parse(raw[annual]["testcase"])
        _tcs.append([
            {
                "name"        : k,
                "annual"      : annual,
                "bkm_quantity": _tcs_data[k].get('bkm_quantity'),
                "customer"    : k.split('-')[0],
                "function"    : report.bkm_filter(_tcs_data[k], bkms).get('bkm_main_tag')
            }
            for k in _tcs_data
        ])
    testcases = {
        func: {
            cust: {
                annual: sum(map(
                    lambda y: y.get('bkm_quantity'),
                    filter(lambda x: (
                        x.get('function') == func
                        and x.get('annual') == annual
                        and x.get('customer') in [ cust, 'SIT' ]
                    ), flatten(_tcs))
                )) + functions[annual][func].get('sms_bkm_num')
                for annual in annuals
            }
            for cust in ReportMap().customers
        }
        for func in ReportMap().functions
    }

    # group by function depends on customer data and separate with annual
    func_data = {
        func: {
            annual: {
                'Tencent' if k == 'TC' else k: {
                    "complete"        : customers[annual][k][func].get('ares_bkm_num'),
                    "can_be_automated": customers[annual][k][func].get('ares_auto_bkm_num'),
                    "total"           : customers[annual][k][func].get('total_bkm_num')
                }
                for k in customers[annual]
                if customers[annual][k].get(func) and k in ReportMap().keywords
            }
            for annual in customers
        }
        for func in ReportMap().functions
    }

    # caculate automated rate scale up with begin/end of annual
    resp = {
        "data": {
            func: {
                **{
                    cust: {
                        begin: {
                            **func_data[func][begin][cust],
                            "sms_complete": testcases[func][cust][begin]
                        },
                        end: {
                            **func_data[func][end][cust],
                            "sms_complete": testcases[func][cust][end]
                        }
                    }
                    for cust in ReportMap().customers
                },
                "can_be_automated": report.sum('can_be_automated', func_data[func][begin]),
                "complete_start"  : report.sum('complete', func_data[func][begin]),
                "complete_end"    : report.sum('complete', func_data[func][end]),
                "scale_up"        : report.weird(
                    ( report.sum('complete', func_data[func][end])
                    - report.sum('complete', func_data[func][begin]) ),
                    report.sum('can_be_automated', func_data[func][end])
                )
            }
            for func in func_data
        }
    }
    resp["data"]["Total"] = {
        "can_be_automated"  : report.sum('can_be_automated', resp["data"]),
        "complete_start"    : report.sum('complete_start', resp["data"]),
        "complete_end"      : report.sum('complete_end', resp["data"]),
        "sms_complete_start": report.sum_sms(begin, resp["data"]),
        "sms_complete_end"  : report.sum_sms(end, resp["data"]),
        "scale_up"          : report.weird(
            ( report.sum('complete_end', resp["data"])
            - report.sum('complete_start', resp["data"]) ),
            report.sum('can_be_automated', resp["data"])
        )
    }
    resp["customers"] = ReportMap().customers
    api_route = f'bkms/bkm-time-reduction-comparison?period-start={begin}&period-end={end}'
    resp["time_reduction"] = reports_ares_api_get(api_route)
    response_interpreter(response)
    return resp
