#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.openldap import LdapHandler
from library.iteration import sortby_key
from library.schemas import Dropdown, DropdownItem

from re import sub
from typing import List, Annotated
from starlette.responses import JSONResponse
from dataclasses import asdict, dataclass, field
from fastapi import APIRouter, HTTPException, Path

LDAP = LdapHandler()

router = APIRouter()

@dataclass(frozen=True)
class Maps:
    managers  : List[str] = field(default_factory=lambda: [ 'Manager', 'FAE_Manager' ])
    ltes      : List[str] = field(default_factory=lambda: [ 'Manager', 'FAE_Manager', 'LTE' ])
    tes       : List[str] = field(default_factory=lambda: [ 'SV', 'FV', 'FAE_Manager' ])
    developers: List[str] = field(default_factory=lambda: [ 'TA' ])

PATH_GROUP = Path(
    default     = 'developers',
    description = 'Require `Group Name` *(Team)*',
    regex       = f'^{"|".join(asdict(Maps()))}$'
)

@router.get('/api/v1/openldap/member/{group}', tags=['OpenLDAP'])
async def list_member_by_openldap(
    group: Annotated[str, PATH_GROUP] = PATH_GROUP) -> JSONResponse:
    if not (teams := asdict(Maps())).get(group):
        detail = f'Support Teams: {list(teams)}'
        raise HTTPException(status_code=404, detail=detail)
    resp = { "list": [] }
    for team in teams.get(group):
        label, options = sub('_', ' ', team), []
        for member in LDAP.get_members(team, get_raw=True):
            option = DropdownItem(label=member.name, value=member.name).dict()
            option |= member.dict()
            options.append(option)
        resp["list"].append(dict(Dropdown(label=label, options=sortby_key(options, 'value'))))
    return JSONResponse(status_code=200, content=resp)
