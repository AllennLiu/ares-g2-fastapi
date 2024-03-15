#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('..')
sys.path.append('../library')

from library.helpers import timeit
from library.schemas import RedisDB
from library.config import ARES_ENDPOINT
from library.cacher import RedisContextManager

from json import dumps
from requests import get
from typing import Any, Dict, List, Union
from eventlet import Timeout as monkey_timeout
from argparse import ArgumentParser, RawTextHelpFormatter, Namespace

ERROR_OCCURRED = False

def args_parser() -> Namespace:
    global ARGS
    desc = 'FastAPI CronJob:\nTo update ARES BKM raws.'
    parser = ArgumentParser(description=desc, formatter_class=RawTextHelpFormatter)
    parser.add_argument('--ares-url', action='store', type=str, default=f'{ARES_ENDPOINT}/api/v1',
                        help='set url of ARES backend API\n(default: %(default)s)')
    ARGS = parser.parse_args()
    return ARGS

def sched_update_redis_helper(
    route: str = '', message: str = '', key: str = '', timeout: int = 10
) -> Union[Dict[str, Any], List[str]]:
    global ERROR_OCCURRED
    try:
        with monkey_timeout(timeout):
            res = get(f'http://{ARGS.ares_url}/{route}')
        data = res.json()
        assert data, message
        with RedisContextManager() as r:
            r.hset(RedisDB.ares_bkms, key, dumps(data))
    except Exception as err:
        print(f'ERROR: {err}')
        ERROR_OCCURRED = True
        return {}
    return data

def sched_update_ares_bkm_customers() -> List[str]:
    return sched_update_redis_helper(
        route   = 'customers/bkm-use',
        message = 'empty customers of ARES published BKMs',
        key     = 'customers'
    )

def sched_update_ares_bkm_raws() -> Dict[str, Any]:
    return sched_update_redis_helper(
        route   = 'bkms/published?notSOP=1',
        message = 'empty raw data of ARES published BKMs',
        key     = 'raws',
        timeout = 30
    )

@timeit
def main() -> None:
    args_parser()
    print(' * Schedule Rule: [*/3 * * * *]')
    print(' * Updating the customers of ARES published BKMs:')
    print(dumps(sched_update_ares_bkm_customers(), indent=4) + '\n')
    print(' * Updating the raw data of ARES published BKMs:')
    print(dumps(sched_update_ares_bkm_raws(), indent=4) + '\n')

if __name__ == '__main__':
    main()
    if ERROR_OCCURRED: exit(-1)
