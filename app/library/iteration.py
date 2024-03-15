#!/usr/bin/python3
# -*- coding: utf-8 -*-

from re import search, I
from copy import deepcopy
from itertools import groupby
from operator import itemgetter
from fastapi import HTTPException
from typing import Any, Dict, List, Callable, Generator, Iterable, Union

def find(pred: Callable[..., Any], iterable: Iterable[Any]) -> Union[None, Any]:
    """Define a find function that equivalent of JavaScript's
    `Array.prototype.find`, it returns the first matching
    element in an array, given a predicate function, or
    undefined when there is no match.

    Args
    -------
    - pred    : (Callable): callable function
    - iterable: (Iterable): iterable data

    Examples
    -------
    ```
    objects = [ { "name": "abc" }, { "name": "efg" } ]
    find(lambda x: x.get('name') == 'abc', objects)
    ```
    >>> {'name': 'abc'}
    """
    return next(( element for element in iterable if pred(element) ), None)

def flatten(items: Iterable[Any] = []) -> Generator[Any, None, None]:
    """`遞歸生成器`，判斷數組元素中的子數組，遞歸合併多層嵌套
    數組為單層數組，類似 :func:`~more_itertools.flatten`
    函數，但該函數只能合併二維數組，二維以上需使用本函數進行
    遞歸合併操作

    Args
    -------
    - items: (list): 嵌套 (nested) 數組

    Returns
    -------
        Generator: 返回已合併單層數組的生成器對象

    Examples
    -------
    ```
    nested = [ {'b': 1}, [ [ {'b':2}, [ {'a':3}, {'b':5} ] ], {'a': 4} ] ]
    list(flatten(nested))
    ```
    >>> [{'b': 1}, {'b': 2}, {'a': 3}, {'b': 5}, {'a': 4}]
    """
    for sublist in items:
        if not isinstance(sublist, list):
            yield sublist
        else:
            yield from flatten(sublist)

def diff_array(origin: List[str] = [], latest: List[str] = []) -> Dict[str, list]:
    """對比兩個指定數組的差異，返回已分類好的結果

    Args
    -------
    - origin: (list): 參照數組
    - latest: (list): 對比數組

    Returns
    -------
        dict: 返回字典 `del` 表示 `缺失` 的元素 `add` 表示 `添加` 的元素
    """
    return {
        "del": list(set(origin) - set(latest)),
        "add": list(set(latest) - set(origin))
    }

def sortby_key(
    array: Iterable[Dict[str, Any]] = [], key: str = '', reverse: bool = False
    ) -> List[Dict[str, Any]]:
    """用 sorted 內置函數依照字典的 key 鍵值排序數組

    Args
    -------
    - array  : (list): 待排序的多字典數組
    - key    : (str) : 鍵值
    - reverse: (bool): 是否反向排序

    Returns
    -------
        list: 返回已按鍵值排序的數組

    Examples
    -------
    ```
    array = [ {'name': 'Faye'}, {'name': 'Allen'}, {'name': 'Keith'} ]
    sortby_key(array, key='name')
    ```
    >>> [{'name': 'Allen'}, {'name': 'Faye'}, {'name': 'Keith'}]
    """
    return sorted(array, key=itemgetter(key), reverse=reverse)

def uniq_items_by_key(
    items: List[dict] = [], key: str = 'name', sorted: bool = True) -> List[dict]:
    """通過指定 key 鍵值，刪除數組中重複的多個字典對象

    Args
    -------
    - items    : (list): 多個數據對象的數組 (`[ object1, object2 ]`)
    - key      : (str) : 指定鍵值
    - sorted   : (bool): 是否按照鍵值對數組的元素進行排序

    Returns
    -------
        list: 返回已按鍵值去重的數組
    """
    array, uniques = [], []
    for e in items:
        value = e.get(key)
        if value not in array:
            array.append(value)
            uniques.append(e)
    return sortby_key(uniques, key) if sorted else uniques


def uniq(array: Iterable[Any] = []) -> list:
    """用`哈希表`處理可哈希且已排序的元素時間複雜度 O(n)，不可
    哈希但已排序則 O(n log n)、未排序則 O(n^2)，用來刪除數組中
    的重複項 (數組中可包含任何型別的元素)

    Args
    -------
    - array: (Iterable): 可跌代對象

    Returns
    -------
        list: 返回已刪除重複項的數組

    Examples
    -------
    ```
    uniq([ 1, 1, 2, 3, 5, 4, 1, 2, 2, 4, 5])
    ```
    >>> [1, 2, 3, 5, 4]

    ```
    uniq([ { "ID": 100 }, { "ID": 200 }, { "ID": 100 } ])
    ```
    >>> [{'ID': 100}, {'ID': 200}]
    """
    table: list = []
    _ = [ table.append(e) for e in array if e not in table ]
    return table

def pagination(
    keyword: str = '', key: str = '', page: int = 0, size: int = 10, items: list = []
    ) -> Dict[str, Union[int, list]]:
    """前端調用接口，用來搜索數據並依照指定頁數返回頁數長度的數據

    Args
    -------
    - keyword: (str) : 搜索關鍵字
    - key    : (str) : 搜索數據的參照鍵值
    - page   : (int) : 指定頁數
    - size   : (int) : 單次搜索的總頁數
    - items  : (list): 多個數據對象的數組 (`[ object1, object2 ]`)

    Returns
    -------
        dict: 返回指定頁數長度的數據

    Examples
    -------
    ```
    pagination('SIT-LogFilter', 'script_name', 1, 10, mission_data)
    ```
    """
    resp = { "page": page, "size": size, "list": items, "total": len(items) }
    if keyword:
        _items = deepcopy(items)
        items.clear()
        for item in _items:
            if not (name := item.get(key)): continue
            if not search(keyword, name, I): continue
            items.append(item)
    if not items:
        raise HTTPException(status_code=422, detail='Keyword Not Found')
    elif page == 0 or size == 0:
        return resp
    try:
        return { **resp, "list": list(grouper(items, size))[page - 1] }
    except IndexError as e:
        raise HTTPException(status_code=422, detail='Invalid Page') from e

def grouper(array: List[Any] = [], fillvalue: int = 0
    ) -> Generator[List[Any], None, None]:
    """依指定群组数量，对数组切割进行分组，時間複雜度 O(n)

    Args
    -------
    - array    : (List[Any]): 待分组的数组
    - fillvalue: (int)      : 分组数量

    Returns
    -------
        list: 返回已分组的数组

    Examples
    -------
    ```
    my_array = [ 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 ]
    list(grouper(my_array, 3))
    ```
    >>> [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11]]
    """
    for i in range(0, len(array), fillvalue):
        yield array[i:i + fillvalue]

def groupby_array(array: Iterable[Dict[str, Any]], item: str) -> Dict[str, Any]:
    """將指定可跌代數據，如``多個字點的數組``本地排序後，再通過
    :class:`~itertools.groupby` 類分群組轉換成以指定鍵值的字典

    Args
    -------
    - array: (Iterable[Dict[str, Any]]): 存在多個字典的数组
    - item : (str)                     : 數組中字典已存在的鍵

    Returns
    -------
        dict: 返回已按指定鍵分群的字典

    Examples
    -------
    ```
    my_array = [ { 'name': 'Allen', 'age': 30 }, { 'name': 'Faye', 'age': 25 } ]
    groupby_array(my_array, 'name')
    ```
    >>> {'Allen': {'name': 'Allen', 'age': 30}, 'Faye': {'name': 'Faye', 'age': 25}}
    """
    array.sort(key=itemgetter(item))
    return {
        key: list(group)[0] for key, group in groupby(array, itemgetter(item)) if key
    }

class Sets(set):
    """教學 ``Set`` 集合 (:class:`~set`)，數據型態 `{1, 2, 3}` 可
    快速運算 n 個集合的結果，時間複雜度 O(n)
    - 交集 (:func:`~set.intersection`) 運算元：`&`
    - 並集 (:func:`~set.union`) 運算元：`|`
    - 差集 (:func:`~set.difference`) 運算元：`-`
    - 對稱差集 (:func:`~set.symmetric_difference`) 運算元：`^`

    Examples
    -------
    架設兩個集合分別為
    ```
    set1, set2 = { 1, 1, 2, 3, 5 }, { 4, 1, 2, 2, 4, 5 }
    ```

    求交集 (兩個方法等價)
    ```
    set1 & set2
    set.intersection(set1, set2)
    ```
    >>> {1, 2, 5}

    求並集 (兩個方法等價)
    ```
    set1 | set2
    set.union(set1, set2)
    ```
    >>> {1, 2, 3, 4, 5}

    求差集 (兩個方法等價)
    ```
    set1 - set2
    set.difference(set1, set2)
    ```
    >>> {3}

    求對稱差集，返回两个集合中不重复的元素 (兩個方法等價)
    ```
    set1 ^ set2
    set.symmetric_difference(set1, set2)
    ```
    >>> {3, 4}
    """
    def __init__(self) -> None:
        ...

def intersection_dicts(array1: List[dict], array2: List[dict]) -> List[dict]:
    """列表推導式將兩個由多個字典組成的數組取交集
    時間複雜度 O(n)

    Args
    -------
    - first : (list): 第一組多個字典組成的數組
    - second: (list): 第二組多個字典組成的數組

    Examples
    -------
    ```
    intersection_dicts([ { 'a': 2 }, { 'b': 4 }, { 'a': 1 }, { 'b': 9} ], [ { 'b': 4 }, { 'b': 9 } ])
    ```
    >>> [{'b': 4}, {'b': 9}]
    """
    return [ e for e in array1 if e in array2 ]

def intersection(
        first: List[Union[int, float, str, list]] = [],
        second: List[Union[int, float, str, list]] = []
    ) -> List[Union[int, float, str, list]]:
    """採`分離雙指針`算法時間複雜度 O(n)，求兩個指定數組經
    排序後的交集

    - 模擬內置函數 :func:`~set.intersection`
    - 傳入數組元素僅支持非字典類的類型

    Args
    -------
    - first : (list): 第一組數組
    - second: (list): 第二組數組

    Returns
    -------
        list: 返回兩個數組的交集

    Examples
    -------
    ```
    set.intersection({ 1, 1, 2, 3, 5 }, { 4, 1, 2, 2, 4, 5 })
    intersection([ 1, 1, 2, 3, 5 ], [ 4, 1, 2, 2, 4, 5 ])
    ```
    >>> {1, 2, 5}
    >>> [1, 2, 5]

    ```
    intersection([ [5], [1], [2] ], [ [4], [2], [2], [4] ])
    ```
    >>> [[2]]
    """
    first.sort()
    second.sort()
    cross, p1, p2 = [], 0, 0
    while p1 < len(first) and p2 < len(second):
        if first[p1] == second[p2]:
            if first[p1] not in cross: cross.append(first[p1])
            p1 += 1
            p2 += 1
        elif first[p1] < second[p2]:
            p1 += 1
        else:
            p2 += 1
    return cross
