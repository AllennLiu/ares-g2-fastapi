#!/usr/bin/python3
# -*- coding: utf-8 -*-

from helpers import timeit
from cacher import RedisContextManager

from json import loads, dumps
from pydantic import BaseSettings
from typing import Any, Dict, List, Optional, Union

class BtsInfo(BaseSettings):
    mssql_host_old   : Optional[str] = '10.99.104.240'
    mssql_user_old   : Optional[str] = 'sa'
    mssql_passwd_old : Optional[str] = 'ipcadmin'
    mssql_host_new   : Optional[str] = '10.99.104.203'
    mssql_user_new   : Optional[str] = 'IESsit'
    mssql_passwd_new : Optional[str] = 'IESsit2019'

def dict_search(array: list, key: str, value: Union[str, int, float], ref: str
    ) -> Union[str, int]:
    for e in array:
        if 'Submitter' in key or 'DefectClass' in key:
            if e.get(key) == value:
                return e[key]
        elif e.get('DefectClass'):
            if e["DefectClass"] == ref:
                return e[key]
        elif e.get('Submitter'):
            if e["Submitter"] == ref:
                return e[key]
    if isinstance(value, (int, float)):
        return 0
    else:
        return value if 'Submitter' in key or 'DefectClass' in key else ''

def get_bts_projects() -> List[str]:
    """從 `Redis` 中取得所有不重複 `BTS` 项目名，使用
    :func:`~Redis.hkeys` 方法先取得所有的項目名稱，在
    遍歷儲存符合條件的項目
    """
    projects = set()
    with RedisContextManager(decode_responses=True) as r:
        for key in r.hkeys('issues'):
            raw = r.hget('issues', key)
            if not raw: continue
            if not isinstance(issues := loads(raw), list): continue
            if not issues or not isinstance(issues[0], dict): continue
            projects.add(f'{key.strip()}_{issues[0].get("ProjectID")}')
    return list(projects)

def get_bts_return_rate(array: List[Dict[str, Any]] = [], key: str = 'DefectID'
    ) -> Union[float, int]:
    """通過 `DefectID` 來獲取用戶的 `Return Rate`"""
    numerator = denominator = 0
    for e in array:
        if e.get(key): denominator += 1
        if e.get('Comments'): numerator += len(e.get('Comments'))
    return round(numerator / denominator, 4)

def get_bts_object(array: List[Dict[str, Any]] = [], key: str = 'DefectClass'
    ) -> List[Dict[str, Union[str, int, float]]]:
    """通過 `DefectClass` 或 `Submitter` 獲取用用戶的
    `Return Rate` 數據數組"""
    resp = []
    for i in sorted({ e[key] for e in array if e.get(key) }):
        data = { key: i, "defect_count": 0, "comments": 0, "single_close": 0 }
        for j in array:
            if j.get(key) == i:
                data["defect_count"] += 1
                if j.get('Comments'):
                    data["comments"] += len(j.get('Comments'))
                else:
                    data["single_close"] += 1
        data["return_rate"] = round(data["comments"] / data["defect_count"], 4)
        resp.append(data)
    return resp

@timeit
def main():
    print('Listing Project from BTS:')
    print(dumps(get_bts_projects(), indent=4) + '\n')

if __name__ == '__main__':
    main()
