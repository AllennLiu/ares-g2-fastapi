#!/usr/bin/python3
# -*- coding: utf-8 -*-

from library.config import settings

from uuid import uuid4
from pymongo import MongoClient
from urllib.parse import quote_plus
from typing import Any, List, Optional, Union

MONGO_URL: str = settings.app_config(f'MONGODB_{settings.env.upper()}')

class ConnectMongo:
    """Handle Mongodb to operate with collection and document.

    Kubernetes
    ----------
    Using following settings for ``Mongo Cluster``:
    ```
    mongo_domain = ','.join( f'mongo-{i}.mongo-hs.mongodb' for i in range(3) )
    MONGO_URL = f'{mongo_domain}/?replicaSet=rs0'
    ```

    Attributes
    ----------
    database: str
        Which database to be query
    host: str
        such as: 172.17.0.100:27017
    username: str
        Access username
    password: str
        Access password
    authenticate: bool
        Require to authenticate with passing username/password

    Methods
    -------
    query(name='', rule={}, all=False, string_id=False)
        Query object with specified rule

    listCollection(name='', rule={}, string_id=False)
        Listing all documents with specified rule

    insertCollection(name=', data={}, uuid=True)
        Add a new document entry (could be set with unique UUID)

    deleteDocument(name='', rule={}, many=False)
        Remove a document entry with specified rule (multiple supported)

    updateDocument(name='', rule={}, data={}, ignore_id=False)
        Modify a document entry with specified rule

    Examples
    -------
    Query all script names of TA-Team:
    ```
    with ConnectMongo(database='flask') as m:
        m.query('scripts_name', { "group": "TA-Team" })
    ```
    >>> {
        '_id': ObjectId('652cde18ecbe61a3cb744839'),
        'uuid': 'b2c53841-6450-4fd6-9983-1a0473da376f',
        'group': 'TA-Team',
        'projects': ['SIT-LogFilter', ...]
    }
    """
    def __init__(self,
        database: str = 'flask', host: str = MONGO_URL,
        username: str = 'root', password: str = '111111',
        authenticate: Optional[bool] = False
    ) -> None:
        self.database = database
        self.host = host
        self.url_head = 'mongodb://'
        self.db_url = f'{self.url_head}{self.host}'
        if authenticate:
            self.username = username
            self.password = quote_plus(password)
            self.db_url = f'{self.url_head}{self.username}:{self.password}@{self.host}'

    def __enter__(self) -> MongoClient:
        self.client: MongoClient = MongoClient(self.db_url)
        self.db = self.client[self.database]
        return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> Union[None, AssertionError]:
        self.client.close()
        if any(( type, value, traceback )):
            assert False, value

    def query(self,
        name: str = '', rule: dict = {}, all: bool = False, string_id: bool = False
    ) -> dict:
        collection = self.db[name]
        if all:
            queries = collection.find(rule)
            return (
                [ { **e, "_id": str(e["_id"]) } for e in queries ]
                if string_id else queries
            )
        if string_id:
            if not (data := collection.find_one(rule)):
                return data
            return { **collection.find_one(rule), "_id": str(data["_id"]) }
        return collection.find_one(rule)

    def listCollection(
        self, name: str = '', rule: dict = {}, string_id: bool = False
    ) -> List[dict]:
        collection = self.db[name]
        return [
            ( { **e, "_id": str(e.get('_id')) } if string_id else e )
            for e in collection.find(rule)
        ]

    def insertCollection(
        self, name: str = '', data: dict = {}, uuid: bool = True) -> dict:
        if uuid: data["uuid"] = str(uuid4())
        collection = self.db[name]
        collection.insert_one(data)
        return data

    def deleteDocument(
        self, name: str = '', rule: dict = {}, many: bool = False) -> dict:
        collection = self.db[name]
        if many:
            return collection.delete_many(rule)
        if not (query := collection.find_one(rule)):
            return {}
        collection.delete_one(rule)
        query.pop('_id', None)
        return query

    def updateDocument(self,
        name: str = '', rule: dict = {}, data: dict = {}, ignore_id: bool = False
    ) -> dict:
        if ignore_id: data.pop('_id', None)
        collection = self.db[name]
        query = collection.find_one(rule)
        collection.update_one(query, { "$set": query | data })
        query.pop('_id', None)
        return query | data
