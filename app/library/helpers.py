#!/usr/bin/python3
# -*- coding: utf-8 -*-

from uuid import uuid4
from markdown import markdown
from datetime import datetime
from shutil import move, rmtree
from re import sub, search, compile
from os import remove, walk, PathLike
from functools import wraps, lru_cache
from fastapi import WebSocketDisconnect
from pydantic import FilePath, DirectoryPath
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from os.path import join, isfile, isdir, exists, abspath, splitext, dirname
from typing import Any, Dict, List, Callable, Generator, Optional, TypeVar, Union

try:
    from library.colorful import Colors
except ModuleNotFoundError:
    from colorful import Colors

EXCEPT_PATHS = [ '/', '/usr/src' ]

class BackendPrint:
    """Using backend format to display colorful message in service logs"""
    @staticmethod
    def info(message: Union[str, Any] = '') -> None:
        print('%-21s%s' % (f'{Colors.fgBrightGreen}INFO{Colors.reset}:', f'{message}'))

    @staticmethod
    def error(message: Union[str, Any] = '') -> None:
        print('%-21s%s' % (f'{Colors.fgBrightRed}ERROR{Colors.reset}:', f'{message}'))

def read_file_chunks(path: FilePath, chunk_size: int = 8192
    ) -> Generator[bytes, None, None]:
    """
    If you serve binary files, you should not iterate through
    lines since it basically contains only one "line", which
    means you still load the whole file all at once into the
    RAM. The only proper way to read large files is via chunks.

    Examples
    -------
    ```
    @router.get('/api/v1/download/{path:path}', response_class=StreamingResponse)
    def download(path: str) -> StreamingResponse:
        resp = StreamingResponse(read_file_chunks(file))
        disposition = f"attachment; filename=filename; filename*=utf-8''filename"
        resp.headers["Content-Disposition"] = disposition
        return resp
    ```
    """
    with open(path, 'rb') as fd:
        while 1:
            if buf := fd.read(chunk_size):
                yield buf
            else:
                break

CALC_T = TypeVar('CALC_T')

def timeit(func: Callable[..., CALC_T]) -> Callable[..., CALC_T]:
    """
    Calculating Run Time of a function using decorator,
    you could use this to over target function and the
    runtime of a function will output after it done.

    Examples
    -------
    ```
    @timeit
    def test(n):
        return [ i ** i for i in range(n) ]
        x = test(10000)
    ```
    >>> time taken: 0:00:05.531982
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> CALC_T:
        begin_ts = datetime.now()
        result = func(*args, **kwargs)
        print(f'time taken: {datetime.now() - begin_ts}')
        return result
    return wrapper

WEBSOCKET_T = TypeVar('WEBSOCKET_T')

def websocket_catch(func: Callable[..., WEBSOCKET_T]) -> Callable[..., WEBSOCKET_T]:
    """
    The main caveat of this method is that route can't
    access the request object in the wrapper and this
    primary intention of websocket exception purpose.

    由於裝飾器 (`decorator`) 會接收一個函數當參數，然後返
    回新的函數，這樣會導致被包裝函數的名子與注釋消失，如此
    便需要使用 :func:`~functools.wraps` 裝飾子修正

    函數的名子與注釋：`func.__name__`、`func.__doc__`
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Union[WEBSOCKET_T, None]:
        try:
            return await func(*args, **kwargs)
        except WebSocketDisconnect:
            pass
        except ( ConnectionClosedError, ConnectionClosedOK ) as e:
            BackendPrint.info(str(e))
        except Exception as e:
            BackendPrint.error(str(e))
    return wrapper

CATCH_RETRY_T = TypeVar('CATCH_RETRY_T')

def catch_except_retry(times: int = 1, exceptions: tuple = ( Exception, )):
    """Retry Decorator
    -------
    Retries the wrapped function/method `times` times if the exceptions listed
    in ``exceptions`` are thrown.

    Args
    -------
    - times     : (int)  : The number of times to repeat the wrapped function/method
    - exceptions: (tuple): Lists of exceptions that trigger a retry attempt

    Examples
    -------
    ```
    @catch_except_retry(times=3)
    def test(t: int):
        sleep(t)
        assert (int(strftime('%s')) % 2) == 0, 'maximum exceeded'
    ```
    """
    def decorator(func: Callable[..., CATCH_RETRY_T]) -> Callable[..., CATCH_RETRY_T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> CATCH_RETRY_T:
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except exceptions as err:
                    msg = f'Exception thrown when attempting to run {func} ({attempt + 1}/{times})'
                    BackendPrint.error(msg)
                    BackendPrint.error(str(err))
            return func(*args, **kwargs)
        return wrapper
    return decorator

def openfile(filename: FilePath) -> Dict[str, str]:
    with open(join('pages/', filename), 'r', encoding='utf-8') as f:
        return { "text": markdown(f.read()) }

@lru_cache
def read_readme(readme: FilePath) -> Dict[str, str]:
    """從指定 `README` 文件獲取``項目名稱``與``版本號``"""
    with open(readme, 'r', encoding='utf-8') as f:
        content = f.read()
    ver = sub('[^\d+\.]', '', search('`Rev:\s{0,}(\d+\.){1,2}\d+`', content).group(0))
    name = search('^(\w+\-){2}\w+\n\={5,}', content).group(0).split('\n')[0]
    return { "version" : ver, "project_name" : name }

def create_commit_id() -> str:
    """通過 `UUID v4`，生成一組提交識別碼 (Commit ID)，"""
    return str(uuid4()).replace('-', '') + str(uuid4()).replace('-', '')[-8::]

@catch_except_retry()
def safety_move(
    src: Union[str, PathLike] = '', dst: Union[str, PathLike] = '', force: bool = False
) -> Union[bool, AssertionError]:
    """安全地``搬移``或``重命名``文件"""
    assert src, 'empty source path detected'
    assert dst, 'empty destination detected'
    abs_src, abs_dst = abspath(src), abspath(dst)
    assert exists(abs_src), f'source path: {abs_src} not found'
    assert exists(parent := dirname(abs_dst)), f'destination: {parent} not found'
    assert abs_src not in EXCEPT_PATHS, f'should not in {EXCEPT_PATHS}'
    assert abs_dst not in EXCEPT_PATHS, f'should not in {EXCEPT_PATHS}'
    assert abs_src != abs_dst, 'source path and destination are the same'
    if force:
        _ = safety_rmtree(abs_dst) if isdir(abs_dst) else safety_remove(abs_dst)
    move(abs_src, abs_dst)
    return exists(abs_dst)

@catch_except_retry()
def safety_remove(file: Union[str, PathLike] = '') -> Union[bool, AssertionError]:
    """安全地``刪除``文件"""
    assert file, 'empty file detected'
    abs_path = abspath(file)
    assert isfile(abs_path), f'file: {abs_path} not found'
    remove(abs_path)
    return not exists(abs_path)

@catch_except_retry()
def safety_rmtree(path: Union[str, PathLike] = '') -> Union[bool, AssertionError]:
    """安全地``刪除``整個文件夾 (含子目錄)"""
    assert path, 'empty path detected'
    assert path not in EXCEPT_PATHS, f'should not in {EXCEPT_PATHS}'
    abs_path = abspath(sub('/+$', '', path))
    assert abs_path not in EXCEPT_PATHS, f'should not in {EXCEPT_PATHS}'
    assert abs_path.count('/') >= 2, 'must be at latest 2 nested path'
    assert isdir(abs_path), f'directory: {abs_path} not found'
    rmtree(abs_path)
    return not exists(abs_path)

def is_true(boolean: Optional[str] = None) -> bool:
    """驗證傳入的字符是否為 `True`"""
    boolean = 'y' if boolean is None else boolean
    values = { 'true', '1', 't', 'y', 'yes', 'yeah', 'yup', 'certainly', 'uh-huh' }
    return boolean.lower() in values if boolean else False

def delete_ansi(text: str) -> str:
    """刪除``指定文本``所有的顏色 `ANSI Code`"""
    ansi_escape = compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def delete_ansi_recursive(
    directory: DirectoryPath, extensions: List[str] = [ 'log', 'txt' ]) -> None:
    """遞歸刪除``指定路徑下``所有的文件其文本之顏色 `ANSI Code`"""
    regexp = '^{0}$'.format('|'.join(extensions))
    for (root, _, files) in walk(directory, topdown=False):
        for name in files:
            path = join(root, name)
            ext = splitext(path)[-1]
            if search(regexp, ext.lower().strip('.')):
                with open(path) as rf:
                    content = delete_ansi(rf.read())
                with open(path, 'w') as wf:
                    wf.write(content)

def version_increment(ver: str = '0.0.0', release: bool = False, force: bool = True) -> str:
    """提升指定版本的一個小版本，或強制提升至正式發布版本，最終
    返回一個版本字符串

    Args
    -------
    - ver    : (str) : 待提升的版本號，如：`0.0.1`
    - release: (bool): 是否提升到正式發布版本
    - force  : (bool): 強制提升版本，默認是啟用的，可因特殊原因
        關閉，如腳本任務修改 ``README`` 階段時

    Examples
    -------
    提升小版本
    ```
    version_increment('1.0.0')
    ```
    >>> '1.0.1'

    提升正式版本
    ```
    version_increment('1.0.0', True)
    ```
    >>> '1.1.0'
    """
    if release and not force and ver[-1] == '0':
        return ver
    digits = list(map(int, ver.split('.')))
    if release and digits[0] == 0 and digits[1:-1].count(0) == len(digits[1:-1]):
        digits[0] = 1
        digits[1:] = [ 0 for _ in digits[1:] ]
    elif release:
        digits[-2] += 1
        digits[-1] = 0
    else:
        digits[-1] += 1
    for i in range(len(digits) - 1, -1, -1):
        if digits[i] >= 100:
            digits[i] = 0
            if i == 0:
                digits.insert(0, 1)
            else:
                digits[i - 1] += 1
    return '.'.join(map(str, digits))

def version_class(version: str) -> str:
    """獲取指定版本的類型，類型非為：`release 正式版` 與`revision 驗證版`"""
    if not search(r'\d+\.\d+\.\d+', version):
        return 'unknown'
    return 'revision' if version.split('.')[-1] != '0' else 'release'
