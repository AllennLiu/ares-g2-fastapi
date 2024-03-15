#!/usr/bin/python3
# -*- coding: utf-8 -*-

from iteration import flatten

from re import sub, search
from calendar import Calendar
from pydantic import BaseModel
from time import mktime, strftime
from datetime import date, datetime
from typing import Any, Dict, List, Generator, Optional, Union

class HolidayInfo(BaseModel):
    date         : str
    holiday_name : Optional[str] = ''

class Holiday:
    """This class is based on external PyPi module `chinesecalendar`
    (need to upgrade anytime)

    If the module not support further, means nobody create new
    calendar for module maintenance, then it will not be imported
    this function, finally return empty generator.
    """
    @classmethod
    def validator(cls) -> bool:
        """Check module has been installed and current year is
        available for implementation.
        """
        try:
            __import__('chinese_calendar')
            from chinese_calendar import get_holiday_detail
            cls.func = get_holiday_detail
            result = cls.func(datetime.date(datetime.now()))
            return result is not None
        except ( ImportError, NotImplementedError ):
            return False

    @classmethod
    def yeardates(cls, yyyy: int) -> Generator[List[date], None, None]:
        """Return full specific year generator of :class:`~datetime.date`
        objects.

        Args
        -------
        - yyyy: (int) : search year

        Returns
        -------
            Generator: return with date objects

        Examples
        -------
        ```
        list(Holiday.yeardates(2023))
        ```
        >>> [datetime.date(2022, 12, 26), ...]
        """
        _calendar = Calendar()
        yield from sorted(set(flatten(_calendar.yeardatescalendar(yyyy))))

    @classmethod
    def getdates(cls, yyyy: int = datetime.now().year, detail: bool = True, instance: bool = False
        ) -> Generator[List[Union[Dict[str, str], str, HolidayInfo]], None, None]:
        """Return full specific year holiday within 365 days in a
        generator of (dict, datetime, instance).

        Args
        -------
        - yyyy    : (int) : search year
        - detail  : (bool): more information
        - instance: (bool): return with dataclass objects

        Returns
        -------
            Generator: return the dict or datetime or instance of holiday

        Examples
        -------
        ```
        list(Holiday.getdates(2023))
        ```
        >>> [{'date': '2023-01-01', 'holiday_name': "New Year's Day"}, ...]
        """
        if cls.validator() is False:
            yield
        for _date in cls.yeardates(yyyy):
            if _date.year < yyyy: continue
            try:
                is_holiday, festival = cls.func(_date)
            except NotImplementedError:
                continue
            if not is_holiday: continue
            isoformat = _date.isoformat()
            if detail:
                holiday_name = festival or _date.strftime('%A')
                raw = HolidayInfo(date=isoformat, holiday_name=holiday_name)
                if not instance: raw = raw.dict()
            else:
                raw = isoformat
            yield raw

def datetimer(text: str = '', ts: bool = True,
    date: bool = False, weekday: bool = False,
    fmt: str = '%Y-%m-%dT%H:%M:%S') -> Union[str, int, float]:
    ret = ''
    if weekday:
        return datetime.strptime(text, fmt).strftime('%A')
    if ts:
        ret = mktime(datetime.strptime(text, fmt).timetuple())
    elif date:
        ret = datetime.fromtimestamp(float(text)).strftime(fmt)
    return str(ret)

def datetime_data(pattern: str = 'T', repl: str = ' ') -> Dict[str, Any]:
    ts_cst = round(datetime.now().timestamp())
    return {
        "ts"    : (ts := str(ts_cst)),
        "dt"    : (dt := strftime('%Y-%m-%dT%H:%M:%S')),
        "ts_cst": ts_cst,
        "dt_tag": datetimer(ts, ts=False, date=True, fmt='%B %d, %Y %I:%M %p'),
        "string": sub(pattern, repl, dt)
    }

def date_autocomplete(date: str = '') -> str:
    return date if search(r'T(\d{2}\:){2}\d{2}', date) else f'{date}T00:00:00'

def date_attenuator(
    date: str = '', type: str = 'increase',
    days: int = 0, skip_holiday: bool = True) -> Union[str, Dict[str, Any]]:
    """
    Date attenuator to increase/decrease sepcified
    days on it, then return it without any holiday
    or weekend.
    """
    _exhausted = object()
    types = [ 'increase', 'decrease' ]
    weekend = [ 'Saturday', 'Sunday' ]
    if not date or type not in types:
        return ''
    yyyy = int(date.split('-')[0])
    holidays = Holiday.getdates(yyyy, detail=False)
    limit = 365
    ds = 86400
    dt = date_autocomplete(date)
    ts = float(datetimer(dt))
    for buffer in range(limit):
        if type == types[0]:
            ts = ts + float(ds * (days + buffer))
        elif type == types[1]:
            ts = ts - float(ds * (days - buffer))
        dt = datetimer(str(ts), ts=False, date=True)
        weekday = datetimer(dt, weekday=True)
        if next(holidays, _exhausted) is _exhausted:
            if weekday not in weekend:
                break
        elif dt.split('T')[0] not in holidays:
            break
        if not skip_holiday:
            break
    return datetimer(str(int(ts)), ts=False, date=True)

def date_slice(date: str = '', part: int = 1, slice_char: str = '-') -> str:
    return (
        '/'.join( str(int(s)) for s in date.split(slice_char)[part:] )
        if slice_char in date else '0/0'
    )

def date_day_remains(start: Union[str, int, float], end: Union[str, int, float]) -> int:
    return int((float(end) - float(start)) / 86400)

def time_convertor(d: str = '', is_timestamp: bool = True) -> tuple:
    if not search(r'^\d{4}\-\d{2}\-\d{2}', d):
        return 0
    date = search(r'^\d{4}\-\d{2}\-\d{2}', d).group(0)
    time = search(r'(\d{2}\:){2}\d{2}', d).group(0)
    ts = int(mktime(datetime.strptime(date, "%Y-%m-%d").timetuple()))
    days = int( (datetime.now().timestamp() - ts) / 60 / 60 / 24 )
    return ( date, ts, days ) if is_timestamp else ( date, time, days )
