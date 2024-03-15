#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('..')
sys.path.append('../library')

from library.helpers import timeit
from library.mongodb import ConnectMongo
from library.openldap import LdapHandler

from json import dumps
from typing import Any, Dict, List
from argparse import ArgumentParser, RawTextHelpFormatter, Namespace

LDAP = LdapHandler()

def args_parser() -> Namespace:
    global ARGS
    desc = 'FastAPI CronJob:\nTo delete resigned members of LDAP server.'
    parser = ArgumentParser(description=desc, formatter_class=RawTextHelpFormatter)
    parser.add_argument('-c', '--clean', action='store_true',
                        help='delete resigned member of LDAP server')
    ARGS = parser.parse_args()
    return ARGS

def sched_get_resigned_employee() -> List[Dict[str, Any]]:
    with ConnectMongo(database='chrysaetos') as m:
        return m.query('users', { "user_employed": 2 }, True, True)

def sched_clean_resigned_employee() -> List[Dict[str, Any]]:
    ares_resigned_users = sched_get_resigned_employee()
    groups, accounts = LDAP.get_ldap_group(), LDAP.get_ldap_account()
    ldap_users = { k.lower(): accounts[k] for k in accounts }
    ldap_groups = {
        k: {
            "dn"     : groups[k].get('dn'),
            "members": {
                f'{e.get("employee_id")}'.lower(): e for e in groups[k]["members"]
            }
        } for k in groups
    }

    # binding resigned employee data
    resp = [
        {
            "name"       : e.get('user_name'),
            "employee_id": e.get('user_id'),
            "dn"         : ldap_users[f'{e.get("user_id")}'.lower()].get('dn')
        }
        for e in ares_resigned_users
        if f'{e.get("user_id")}'.lower() in ldap_users
    ]
    if not ARGS.clean:
        print('NOTICE: This operation will show resigned employee only.')
        return resp

    # delete user entirely before
    # test condition with specified user: if 'IES180588' in e["dn"]
    _ = [ LDAP.conn.delete(e["dn"]) for e in resp if e.get('dn') ]

    # delete user by LDAP's Groups after
    # test condition with specified user: and e["employee_id"] == 'IES180588'
    _ = [
        [
            LDAP.conn.modify(
                v["dn"],
                {
                    "memberUid": [
                        (
                            LDAP.MODIFY_DELETE,
                            [ LdapHandler.get_uid_by_dn(e["dn"], e["employee_id"]) ]
                        )
                    ]
                }
            )
            for v in ldap_groups.values()
            if f'{e.get("employee_id")}'.lower() in v["members"]
        ]
        for e in resp
    ]
    return resp

@timeit
def main() -> None:
    args_parser()
    print(' * Schedule Rule: [0 7 * * *]')
    print(' * Clearning SIT Resigned Users from OpenLDAP:')
    print(dumps(sched_clean_resigned_employee(), indent=4) + '\n')

if __name__ == '__main__':
    main()
