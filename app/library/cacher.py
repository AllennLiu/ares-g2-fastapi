#!/usr/bin/python3
# -*- coding: utf-8 -*-

from helpers import timeit
from schemas import RedisDB
from params import json_parse
from library.config import settings

from json import loads, dumps
from redis import Redis, ConnectionPool
from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Generic, Union
from fastapi_sessions.frontends.session_frontend import ID
from fastapi_sessions.backends.session_backend import BackendError, SessionBackend, SessionModel

global REDIS_URL, REDIS_DB_INDEX

REDIS_URL: str = settings.app_config(f'REDIS_{settings.env.upper()}')
REDIS_DB_INDEX: int = 0

class RedisContextManager:
    """A class used to handle Redis cache.

    Attributes
    ----------
    host: str
        The redis server host
    port: int
        The redis server port
    db: int
        The redis server db index
    decode_responses: bool
        Decode the responses of hash data

    Methods
    -------
    parse_hgetall(data={})
        Parse the data of hash dict and return

    Examples
    -------
    ```
    with RedisContextManager() as r:
        r.exists(name)    : Boolean
        r.ttl(name)       : Number
        r.hget(name, key) : String
        r.hgetall(name)   : Object<string>
        r.hkeys(name)     : Array
        r.hset(name, key, value)
        r.hsetnx(name, key, value)
        r.hdel(name, key)
        r.delete(name)
        r.expire(name, expired_time)
    ```
    """

    def __init__(self,
        host: str = REDIS_URL.split(':')[0],
        port: int = int(REDIS_URL.split(':')[1]),
        db: int = REDIS_DB_INDEX,
        decode_responses: bool = False
    ) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.rd = None
        self.decode_responses = decode_responses

    def __enter__(self) -> Redis:
        pool: ConnectionPool = ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            decode_responses=self.decode_responses
        )
        self.rd: Redis = Redis(connection_pool=pool)
        return self.rd

    def __exit__(self, type: Any, value: Any, traceback: Any) -> Union[None, AssertionError]:
        if self.rd is not None:
            self.rd.connection_pool.disconnect()
            self.rd.close()
        if any(( type, value, traceback )):
            assert False, value

    def parse_hgetall(self, data: Dict[Union[str, int], Any] = {}) -> Dict[Union[str, int], Any]:
        return { k: json_parse(data[k]) for k in data }

class RedisBackend(Generic[ID, SessionModel], SessionBackend[ID, SessionModel]):
    """Stores session data to Redis expired cache."""
    def __init__(self) -> None:
        ...

    async def create(
        self, session_id: ID, data: SessionModel, expires: int
    ) -> Union[None, BackendError]:
        with RedisContextManager() as r:
            query = r.hget(name := f'session-{session_id}', 'session')
            if query:
                raise BackendError('create can not overwrite an existing session')
            r.hset(name, 'session', dumps(dict(data)))
            r.expire(name, expires)

    async def read(self, session_id: ID) -> Union[Dict[str, Any], None]:
        with RedisContextManager() as r:
            query = r.hget(f'session-{session_id}', 'session') or '{}'
            return loads(query) or None

    async def update(self, session_id: ID, data: SessionModel) -> None:
        with RedisContextManager() as r:
            query = r.hget(name := f'session-{session_id}', 'session')
            if not query:
                raise BackendError('session does not exist, cannot update')
            r.hset(name, 'session', dumps(dict(data)))

    async def delete(self, session_id: ID) -> None:
        with RedisContextManager() as r:
            r.delete(f'session-{session_id}')

def get_script_customers() -> List[str]:
    with RedisContextManager() as r:
        customers = r.hget(RedisDB.customers, 'customers')
    return json_parse(customers)

def get_customers_by_name(name: str, customers: List[str]) -> List[str]:
    if 'SIT' in customers: customers.remove('SIT')
    customer = name.split('-')[0].upper()
    return customers if customer == 'SIT' else [ customer ]

def args_parser() -> Namespace:
    global ARGS, REDIS_URL, REDIS_DB_INDEX
    parser = ArgumentParser(description='Redis manageemnt.')
    parser.add_argument('-n', '--name', action='store', type=str, default='gitlab-script-list',
                        help='set name of redis collection (default: %(default)s)')
    parser.add_argument('--redis-url', action='store', type=str, default=REDIS_URL,
                        help='set url of redis (default: %(default)s)')
    parser.add_argument('--redis-db', action='store', type=int, default=REDIS_DB_INDEX,
                        help='set db index of redis (default: %(default)s)')
    ARGS = parser.parse_args()
    REDIS_URL = ARGS.redis_url
    REDIS_DB_INDEX = ARGS.redis_db
    return ARGS

@timeit
def main() -> None:
    args_parser()
    with RedisContextManager(decode_responses=True) as r:
        ret = r.hgetall(ARGS.name)
    print(dumps(ret, indent=4))

if __name__ == '__main__':
    main()
