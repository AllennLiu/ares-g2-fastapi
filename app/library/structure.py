#!/usr/bin/python3
# -*- coding: utf-8 -*-

from typing import Any, Dict, List, TypeVar, Union

class HashableDict(dict):
    """Implement hash method for unhashable dictionary"""
    def __hash__(self):
        return hash(tuple(sorted(self.items())))

HashedDict = TypeVar('HashedDict', HashableDict, dict)

class HashableList(list):
    """Implement hash method for unhashable list"""
    def __hash__(self):
        return hash(tuple(sorted(self)))

HashedList = TypeVar('HashedList', HashableList, list)

def freeze(data: Union[Dict[str, Any], List[Any]]) -> Union[HashableDict, HashableList]:
    """Fulfill nested dictionary or list hashed requirement,
    nine times out of ten to make function could be use with
    :func:`~functools.lru_cache`."""
    if isinstance(data, dict):
        return HashableDict({ k: freeze(v) for k, v in data.items() })
    if isinstance(data, list):
        return HashableList([ freeze(v) for v in data ])
    return data
