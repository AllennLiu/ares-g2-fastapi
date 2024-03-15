#!/usr/bin/python3
# -*- coding: utf-8 -*-

from iteration import flatten
from moment import datetime_data
from openldap import LdapHandler
from helpers import version_increment

from re import search
from time import strftime
from uuid import uuid4, UUID
from dataclasses import dataclass, field
from pydantic import validator, BaseModel
from typing import Any, Dict, List, Optional, Union

LDAP = LdapHandler()

QUATERS = {
    str(i).zfill(2): (
        'Q1' if i < 4 else
        'Q2' if i > 3 and i < 7 else
        'Q3' if i > 6 and i < 10 else 'Q4'
    ) for i in range(1, 13)
}

HALFYEARS = [ 'H1' if i < 7 else 'H2' for i in range(1, 13) ]
HALFYEAR_MAPS = { "H1": list(range(1, 7)), "H2": list(range(7, 13)) }

@dataclass(frozen=True)
class LogFilterDB:
    logfilter  : str = 'script-management-logfilter-history'
    powercycle : str = 'script-management-powercycle-history'

@dataclass(frozen=True)
class AutomationDB:
    analysis : str = 'script-management-automation-analysis'
    settings : str = 'script-management-automation-settings'
    reports  : str = 'gitlab-pipeline-reports'

@dataclass(frozen=True)
class ChatGptDB:
    records : str = 'chatgpt-chat-records'

@dataclass(frozen=True)
class RedisDB:
    history      : str = 'script-management-missions-history'
    changelist   : str = 'script-management-missions-changelist'
    source       : str = 'script-management-missions-changelist-source'
    source_cache : str = 'script-management-missions-changelist-source-cache'
    customers    : str = 'script-management-missions-customers'
    backup       : str = 'script-management-missions-backup'
    logtypes     : str = 'script-management-missions-logtypes'
    platforms    : str = 'script-management-coverage-platforms'
    ares_bkms    : str = 'script-management-ares-published-bkms'
    downloads    : str = 'script-management-scripts-download'

@dataclass(frozen=True)
class MissionDB:
    gitlab : str = 'gitlab-script-list'
    create : str = 'script-management-missions'
    update : str = 'script-management-update-missions'

@dataclass(frozen=True)
class CollectionDB:
    tree    : str = 'script-management-collections-tree'
    maps    : str = 'script-management-collections-requirements-maps'
    history : str = 'script-management-collections-requirements-history'
    version : str = 'script-management-collections-requirements-version'

@dataclass(frozen=True)
class ReportDB:
    achievement : str = 'script-management-kpi-achievement'
    kpi_list    : str = 'script-management-kpi-list'
    requirement : str = 'script-management-kpi-requirement'
    summary     : str = 'script-management-kpi-summary'
    testcase    : str = 'script-management-kpi-testcase'
    duration    : str = 'return-rate-duration'

@dataclass(frozen=True)
class ReportMap:
    keywords  : List[str] = field(default_factory=lambda: [ 'Ali', 'ByteDance', 'TC' ])
    customers : List[str] = field(default_factory=lambda: [ 'Ali', 'ByteDance', 'Tencent' ])
    functions : List[str] = field(default_factory=lambda: [ 'BIOS', 'BMC', 'SV' ])
    # 'SV-computing', 'SV-network', 'SV-storage', 'SV-system'

@dataclass(frozen=True)
class FilterMap:
    logfilter : Dict[str, str] = field(
        default_factory=lambda: { "id": 17, "path": "LogFilterTool/error_key.json" })
    powercycle: Dict[str, str] = field(
        default_factory=lambda: { "id": 12, "path": "lib/bw_list.json" })
    bytedance : Dict[str, str] = field(
        default_factory=lambda: { "id": 325, "path": "lib/bw_list.json" })

class Dropdown(BaseModel):
    label   : Optional[str] = ''
    options : Optional[List[Dict[str, str]]] = []

class DropdownItem(BaseModel):
    label : Optional[str] = ''
    value : Optional[str] = ''

class Maintainer(BaseModel):
    uuid        : Union[str, UUID] = str(uuid4())
    maintainer  : Optional[str] = ''
    last_update : Optional[str] = datetime_data().get('dt')

class Analyzer(Maintainer):
    black   : Optional[List[str]] = [ 'fail', 'fatal', 'error', 'fault', 'bad', 'failure' ]
    white   : Optional[List[str]] = [ '^#+', '^\/{2,}', 'PASS', 'Success' ]
    exclude : Optional[List[str]] = []
    match_case  : Optional[bool] = False
    whole_word  : Optional[bool] = False
    highlight   : Optional[bool] = True
    enable      : Optional[bool] = True
    additional  : Optional[dict] = {}
    script_name : Optional[str]  = ''
    function    : Optional[str]  = ''
    customer    : Optional[str]  = ''
    rev         : Optional[str]  = '0.0.1'
    id          : Optional[int]  = 0
    download_count : Optional[int] = 0

class ScriptConfig(Maintainer):
    reboot_needed   : Optional[bool] = False
    retry_timeout   : Optional[int]  = 3600
    monitor_delay   : Optional[int]  = 10
    process_timeout : Optional[int]  = 600
    counter_path    : Optional[str]  = ''
    finish_signal   : Optional[str]  = 'test finished'
    kill_processes  : Optional[List[str]] = []

class Schedules(BaseModel):
    expected    : Optional[str] = strftime('%Y-%m-%d')
    development : Optional[str] = ''
    validation  : Optional[str] = ''
    release     : Optional[str] = ''

    @validator('expected', 'development', 'validation', 'release', pre=True)
    def check_format(value, field):
        if not value:
            return ''
        return value if search(r'\d{4}(\-\d{2}){2}', value) else ''

class Records(BaseModel):
    name      : str
    comment   : str
    submitter : str
    href      : Optional[str] = ''
    type      : Optional[str] = 'create'

class Reschedule(Records):
    schedules : Optional[dict] = Schedules().dict()

class TeRotate(Records):
    te_name : Optional[str] = ''
    current : Optional[str] = ''

class LogType(BaseModel):
    filename    : str
    description : Optional[str] = 'Please refer to this filename.'

class MissionFlag(BaseModel):
    pipeline_trigger : Union[str, bool] = 'False'
    protected        : Union[str, bool] = 'False'

class MissionInfo(BaseModel):
    script_name        : str
    priority           : Optional[str]  = 'P2'
    hard               : Optional[str]  = 'medium'
    customers          : Optional[list] = []
    link               : Optional[str]  = ''
    repository         : Optional[str]  = ''
    coverages          : Optional[dict] = {}
    schedules          : Optional[dict] = Schedules().dict()
    status             : Optional[str]  = 'assess'
    phase              : Optional[str]  = 'create'
    current            : str
    author             : str
    lte_name           : Optional[str]  = ''
    te_name            : Optional[str]  = ''
    owner              : str
    requester          : str
    developer          : Optional[str]  = ''
    description        : str
    bkms               : dict
    when_to_use        : str
    comment            : str
    validation_comment : Optional[str]  = ''
    readme_comment     : Optional[str]  = ''
    history            : Optional[dict] = {}
    ta_manager         : Optional[str]  = LDAP.get_ta_manager()
    modified_date      : Optional[str]  = datetime_data().get('dt')
    flags              : Optional[dict] = MissionFlag().dict()
    script_version     : Optional[str]  = '0.0.1'
    te_data            : Optional[dict] = {}
    progress           : Union[int, str] = 0
    time_saving        : Union[int, str] = 0
    source_uuid        : Union[UUID, str] = ''
    log_types          : Union[List[LogType], None] = []

class Model(BaseModel):
    status   : Optional[str] = 'create'
    phase    : Optional[str] = 'create'
    current  : Optional[str] = 'requester'
    progress : Optional[int] = 0

class Receivers(BaseModel):
    recipients : Optional[List[str]] = [ 'current' ]
    cc         : Optional[List[str]] = [ 'author' ]
    bcc        : Optional[List[str]] = []

MISSION_MAP = {
    "create": {
        "prev": Model().dict(),
        "next": Model(status='assess', current='owner').dict(),
        "mail": Receivers(cc=[ 'owner' ]).dict()
    },
    "assess": {
        "prev": Model(phase='assess-reject').dict(),
        "next": Model(
            status='review', phase='assess-agree', current='ta_manager'
        ).dict(),
        "mail": Receivers(cc=[ 'requester' ]).dict()
    },
    "review": {
        "prev": Model(
            status='assess', phase='review-reject', current='owner'
        ).dict(),
        "next": Model(
            status='plan', phase='review-agree', current='developer', progress=20
        ).dict(),
        "mail": Receivers(cc=[ 'owner', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "plan": {
        "prev": Model(status='assess', phase='assess-change').dict(),
        "next": Model(
            status='confirm', phase='confirm', current='lte_name', progress=20
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "confirm": {
        "prev": Model(
            status='plan', phase='confirm-reject', current='developer', progress=20
        ).dict(),
        "next": Model(
            status='development', phase='confirm-agree', current='developer', progress=40
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'developer', 'te_name', 'requester' ]).dict()
    },
    "development": {
        "prev": Model(
            status='confirm', phase='confirm-agree', current='lte_name', progress=20
        ).dict(),
        "next": Model(
            status='validation', phase='development', current='te_name', progress=50
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "validation": {
        "prev": Model(
            status='development', phase='validation-fail', current='developer', progress=40
        ).dict(),
        "wait": Model(
            status='validation', phase='validation-wait', current='te_name', progress=50
        ).dict(),
        "next": Model(
            status='edit-readme', phase='validation-pass', current='developer', progress=75
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'developer', 'lte_name', 'requester' ]).dict()
    },
    "edit-readme": {
        "prev": Model(
            status='validation', phase='validation-fail', current='te_name', progress=50
        ).dict(),
        "next": Model(
            status='readme', phase='edit-readme', current='owner', progress=80
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "readme": {
        "prev": Model(
            status='edit-readme', phase='readme-change', current='developer', progress=75
        ).dict(),
        "next": Model(
            status='pre-release', phase='pre-release', current='ta_manager', progress=90
        ).dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'developer', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "pre-release": {
        "prev": Model(
            status='readme', phase='release-change', current='owner', progress=80
        ).dict(),
        "next": Model(
            status='release', phase='release', current='developer', progress=100
        ).dict(),
        "mail": Receivers(cc=[ 'owner', 'developer', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "release": {
        "prev": Model(
            status='pre-release', phase='pre-release', current='ta_manager', progress=90
        ).dict(),
        "next": Model(status='assess', current='owner').dict(),
        "mail": Receivers(cc=[ 'ta_manager', 'owner', 'lte_name', 'te_name', 'requester' ]).dict()
    },
    "unknown": { "prev": Model().dict(), "next": Model().dict() }
}

MISSION_VER_MAP = {
    "development": { "release": False, "force": True },
    "edit-readme": { "release": True, "force": False }
}

MISSION_DEL_LIST = [
    MissionDB.create,
    MissionDB.update,
    MissionDB.gitlab,
    RedisDB.history,
    RedisDB.changelist,
    RedisDB.backup,
    AutomationDB.analysis,
    AutomationDB.settings
]

class Mission:
    data = MISSION_MAP
    data_ver = MISSION_VER_MAP

    @classmethod
    def map(cls, status: str = '', order: str = '') -> Dict[str, Any]:
        return (
            Mission.data[status].get(order) if Mission.data.get(status)
            else Mission.data["unknown"].get(order)
        )

    @classmethod
    def rev(cls, status: str = '', version: str = '0.0.1') -> str:
        return (
            version_increment(
                version,
                release=Mission.data_ver[status].get('release'),
                force=Mission.data_ver[status].get('force')
            ) if Mission.data_ver.get(status) else version
        )

    @classmethod
    def sep(cls, name: str = '') -> List[str]:
        return name.split(';') if name else []

    @classmethod
    def rec(cls, mission: MissionInfo) -> Receivers:
        if Mission.data.get(mission.status):
            data = Mission.data[mission.status]["mail"]
            ls = [ Mission.sep(mission.dict().get(e)) for e in data["cc"] ]
            cc = Mission.rec_extra(mission) + list(flatten(ls)) + [ mission.author ]
            return Receivers(recipients=Mission.sep(mission.current), cc=cc)
        return Receivers()

    @classmethod
    def associates(cls, mission: MissionInfo, extra: List[str] = []) -> Receivers:
        receivers = [ 'owner', 'lte_name', 'te_name', 'developer', 'ta_manager' ]
        reciv_cc = [ mission.dict().get(e) for e in [ 'owner', 'ta_manager' ] ]
        recipients = [ Mission.sep(mission.dict().get(e)) for e in receivers ]
        cc = Mission.rec_extra(mission) + reciv_cc + [ mission.author ]
        return Receivers(recipients=list(flatten(recipients)), cc=[ *cc, *extra ])

    @classmethod
    def rec_extra(cls, mission: MissionInfo) -> List[str]:
        """
        The notification email of mission must to cc the
        manager of SIT director and LTE minister and each
        TE owns manager. (extra cc recipients)
        """
        testers = mission.te_name.split(';')
        managers = set(flatten([ LDAP.get_owns_managers(e) for e in testers ]))
        director = set(LDAP.get_members('Director'))
        return list(managers - director)

class Durations(BaseModel):
    year      : str
    half_year : str
    quater    : str
    duration  : str

def current_duration() -> Durations:
    year = strftime('%Y')
    half_year = HALFYEARS[int(strftime('%m')) - 1]
    quater = QUATERS[strftime('%m')]
    duration = f'{year}-{half_year}'
    return Durations(year=year, half_year=half_year, quater=quater, duration=duration)
