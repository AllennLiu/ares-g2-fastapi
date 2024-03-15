#!/usr/bin/python3
# -*- coding: utf-8 -*-

from iteration import flatten

from os import getenv
from re import search
from json import loads
from functools import wraps
from time import time as _ts
from contextlib import suppress
from collections import defaultdict
from pydantic import BaseModel, EmailStr
from typing_extensions import Self
from typing import Any, Dict, List, Callable, Optional, TypeVar, Union
from ldap3.utils.hashed import hashed
from ldap3.core.exceptions import LDAPBindError
from ldap3 import Server, Connection, ALL, SUBTREE, MODIFY_DELETE, MODIFY_REPLACE, HASHED_SALTED_SHA

LDAP_SERVER      = 'ipt-gitlab.ies.inventec'
LDAP_BASE_DN     = 'cn=admin,dc=inventec,dc=com'
LDAP_PASSWORD    = 'admin'
LDAP_OU_BASE     = 'ou=SIT,ou=CNBL,dc=inventec,dc=com'
LDAP_OU_COMMON   = f'ou=Common,{LDAP_OU_BASE}'
LDAP_OU_OUTSORUC = f'ou=Outsourcing,{LDAP_OU_BASE}'

class LdapUser(BaseModel):
    mail     : Optional[EmailStr] = ''
    password : Optional[str]      = ''
    uid_num  : Optional[int]      = 0
    dn       : Optional[str]      = ''
    display  : Optional[str]      = ''

class LdapGroupUser(BaseModel):
    mail        : Optional[EmailStr] = ''
    name        : Optional[str]      = ''
    employee_id : Optional[str]      = ''

def get_user_name_array(username: str) -> List[str]:
    """獲取所有`英業達`工號可能的組合數組 (``IEC`` 或 ``IES``)
    目的是為了依所有可能性嘗試登入用戶，因為老員工、外包人員、順
    維的工號中，可能含有大小寫字符混搭

    Args
    -------
    - username: (str): 員工帳號 (employee_id)，如：\n
        `IEC070168`

    Returns
    -------
        list: 返回所有可能形式用戶工號的數組

    Examples
    -------
    ```
    get_user_name_array('IEC070168')
    ```
    >>> ['IEC070168', 'iec070168']
    """
    if not search('^(ies|iec)', username.lower()):
        return []
    return list({
        username[:3].upper() + username[3:],
        username[:3].lower() + username[3:],
        username.upper(),
        username.lower()
    })

LDAP_T = TypeVar('LDAP_T')

class LdapHandler:

    MODIFY_DELETE = MODIFY_DELETE

    def __init__(self,
        ldap_srv: str = LDAP_SERVER,
        ldap_base_dn: str = LDAP_BASE_DN,
        ldap_passwd: str = LDAP_PASSWORD,
        ldap_ou_common: str = LDAP_OU_COMMON,
        ldap_ou_outsourc: str = LDAP_OU_OUTSORUC
    ) -> None:
        self.tmp_user = ''
        self.ldap_srv = ldap_srv
        self.ldap_base_dn = ldap_base_dn
        self.ldap_passwd = ldap_passwd
        self.ldap_ou_common = ldap_ou_common
        self.ldap_ou_outsourc = ldap_ou_outsourc
        self.user_filter = '(&(objectClass=inetOrgPerson)(uid=IE*))'
        self.user_attrs = [ 'uid', 'mail', 'userPassword', 'uidNumber', 'displayName' ]
        self.create_connection()

    def __repr__(self) -> str:
        return str(self.conn)

    def __call__(self) -> None:
        print(self.conn)
        self.close()

    @staticmethod
    def gen_uidnum(array: List[int]) -> int:
        """產生數組中不存在的數作為用戶 ``uidNumber``

        Args
        -------
        - array: (List[int]): 整數數組

        Returns
        -------
            int: 返回不重複新的用戶 ``uidNumber``

        Algorithm
        -------
        先排序使數組轉換有序，再用 :func:`~set.difference` 方法查找
        數組區間內不存在的數，找不到表示不存在，則返回最後的元素 `+1`

        算法時間複雜度 O(n), 空間複雜度 O(1)

        Examples
        -------
        ```
        LdapHandler.gen_uidnum([ 1, 2, 4 ])
        ```
        >>> 3
        """
        if not array:
            return 1
        array.sort()
        diffs = list(set(range(array[0], array[-1] + 1)).difference(array))
        return diffs[0] if diffs else array[-1] + 1

    @staticmethod
    def get_uid_by_dn(dn: str, default: str) -> str:
        """解析 ``DN`` 字符中的 ``UID`` 部分，未匹配不存在則返回提供默認值

        Args
        -------
        - dn     : (str): `OpenLDAP` 形式的 DN 字符，如：\n
            `uid=IES187094,ou=Common,ou=SIT,ou=CNBL,dc=inventec,dc=com`
        - default: (str): 員工帳號 (employee_id)，如：\n
            `IEC070168`

        Returns
        -------
            str: 返回從 `DN` 擷取到的用戶 ``uid``

        Examples
        -------
        ```
        LdapHandler.get_uid_by_dn(
            'uid=IEC070168,ou=Common,ou=SIT,ou=CNBL,dc=inventec,dc=com',
            'IES123456'
        )
        ```
        >>> 'IEC070168'
        """
        match = search(r'uid=\w+', dn)
        return match.group().split('=')[-1] if match else default

    def search_handle(func: Callable[..., LDAP_T]) -> Callable[..., LDAP_T]:
        """處理查找數據後因無效數據所引發的例外"""
        @wraps(func)
        def wrapper(self: Self, *args: Any, **kwargs: Any) -> LDAP_T:
            try:
                return func(self, *args, **kwargs)
            except AssertionError as err:
                print(f'Invalid search: {str(err)}')
        return wrapper

    def keep_alive(func: Callable[..., LDAP_T]) -> Callable[..., LDAP_T]:
        """每次操作數據庫時，用以確保服務連線會話仍有效"""
        @wraps(func)
        def wrapper(self: Self, *args: Any, **kwargs: Any) -> LDAP_T:
            if not self.conn.listening: self.conn.rebind()
            return func(self, *args, **kwargs)
        return wrapper

    def create_connection(self) -> Connection:
        self.conn = Connection(
            Server(self.ldap_srv, get_info=ALL),
            self.ldap_base_dn,
            self.ldap_passwd,
            auto_bind=True
        )
        return self.conn

    def login(self, username: str, password: str) -> bool:
        ous = [ self.ldap_ou_common, self.ldap_ou_outsourc ]
        usernames = get_user_name_array(username)
        for user in usernames:
            with suppress(LDAPBindError):
                for ou in ous:
                    with suppress(LDAPBindError):
                        args = ( self.ldap_srv, f'uid={user},{ou}', password )
                        conn = Connection(*args, auto_bind=True)
                        conn.unbind()
                        self.tmp_user = user
                        return True
        return False

    def modify_passwd(self, username: str, password: str, **data) -> Dict[str, Any]:
        user = self.get_user(username)
        if not user.dn:
            return { "description": "user not found" }
        hashed_passwd = hashed(HASHED_SALTED_SHA, password)
        self.conn.modify(user.dn, {
            "displayName" : [( MODIFY_REPLACE, [ data.get('user_web_name') ]   )],
            "o"           : [( MODIFY_REPLACE, [ data.get('user_department') ] )],
            "title"       : [( MODIFY_REPLACE, [ data.get('user_title') ]      )],
            "userPassword": [( MODIFY_REPLACE, [ hashed_passwd ]               )]
        })
        return self.conn.result

    def create_user(self, username: str = '', **data) -> Dict[str, Any]:
        users = self.get_ldap_account()
        if username in users:
            return { "description": "user exists" }
        user_ids = [ e.get('uid_num') for e in users.values() ]
        user_group = self.ldap_ou_common
        hashed_passwd = hashed(HASHED_SALTED_SHA, data.get('password'))
        nick_name = data.get('given_name', '').lower()
        last_change = int(float(_ts()) / ( 60 * 60 * 24 ))
        full_username = f'{data.get("given_name")} {data.get("first_name")}'
        phone_number = data.get('phone_number')
        if not isinstance(phone_number, int):
            phone_number = 63218
        if search('^IESW', username.upper()):
            user_group = self.ldap_ou_outsourc
        attributes = {
            "objectClass"     : [ 'inetOrgPerson', 'posixAccount', 'top', 'shadowAccount' ],
            "gidNumber"       : 0,
            "uid"             : username,
            "uidNumber"       : LdapHandler.gen_uidnum(user_ids),
            "sn"              : data.get('first_name'),
            "loginShell"      : "/bin/bash",
            "shadowFlag"      : 0,
            "shadowMin"       : 0,
            "shadowMax"       : 99999,
            "shadowWarning"   : 0,
            "shadowInactive"  : 99999,
            "shadowLastChange": last_change,
            "shadowExpire"    : 99999,
            "cn"              : full_username,
            "givenName"       : data.get('given_name'),
            "displayName"     : data.get('user_web_name'),
            "o"               : data.get('user_department'),
            "title"           : data.get('user_title'),
            "homeDirectory"   : f"/home/{nick_name}",
            "gecos"           : full_username,
            "telephoneNumber" : phone_number,
            "mail"            : data.get('mail'),
            "userPassword"    : hashed_passwd
        }
        self.conn.add(f'uid={username},{user_group}', attributes=attributes)
        return self.conn.result

    def delete_user(self, username: str) -> bool:
        user = self.get_user(username)
        if not user.dn:
            return False
        self.conn.delete(user.dn)
        return self.conn.result.get('result') == 0

    @keep_alive
    def get_ldap_account(self) -> Dict[str, Any]:
        """獲取所有用戶並依照用戶屬性對應並整理其數據

        Returns
        -------
            dict: 以用戶工號為鍵的數據字典 (:class:`~LdapUser`)
        """
        users = defaultdict(lambda: dict(LdapUser()))
        self.conn.search(LDAP_OU_BASE, self.user_filter, attributes=self.user_attrs)
        for e in self.conn.entries:
            with suppress(Exception):
                user = loads(e.entry_to_json())
                users[''.join(user["attributes"]["uid"])] = LdapUser(
                    mail     = ''.join(user["attributes"]["mail"]),
                    password = ''.join(user["attributes"]["userPassword"]),
                    uid_num  = user["attributes"]["uidNumber"][0],
                    dn       = user["dn"],
                    display  = user["attributes"]["displayName"][0]
                ).dict()
        return dict(users)

    @keep_alive
    def get_user(self, username: str) -> LdapUser:
        """依指定用戶工號獲取用戶數據實例

        Args
        -------
        - username: (str): 員工帳號 (employee_id)，如：\n
            `IEC070168`

        Returns
        -------
            LdapUser: 已處理過的用戶實例 (:class:`~LdapUser`)

        Examples
        -------
        ```
        LdapHandler().get_user('IEC070168')
        ```
        >>> LdapUser(mail='Liu.AllenJH@inventec.com', ...)
        """
        search_filter = f'(&(objectClass=inetOrgPerson)(uid={username}))'
        if not self.conn.search(LDAP_OU_BASE, search_filter, attributes=self.user_attrs):
            return LdapUser()
        user = loads(self.conn.entries[0].entry_to_json())
        return LdapUser(
            mail     = ''.join(user["attributes"]["mail"]),
            password = ''.join(user["attributes"]["userPassword"]),
            uid_num  = user["attributes"]["uidNumber"][0],
            dn       = user["dn"],
            display  = user["attributes"]["displayName"][0]
        )

    def get_ldap_group(self) -> Dict[str, Any]:
        """獲取所有群組的成員用戶數據數組 (:class:`~LdapGroupUser`)
        代碼資源占用較高，因為需遍歷所有群組以及生成其用戶數據

        已知群組名稱可用 :func:`~LdapHandler.get_members` 方法獲取

        Returns
        -------
            list: 所有群組成員用戶數據數組
        """
        groups: Dict[str, Dict[str, Union[List[dict], str]]] = {}
        ldap_users = self.get_ldap_account()
        self.conn.search(
            LDAP_OU_BASE,
            '(objectclass=posixGroup)',
            attributes=[ 'cn', 'memberUid' ]
        )
        for e in self.conn.entries:
            user = loads(e.entry_to_json())
            cn = ''.join(user["attributes"]["cn"])
            groups[cn] = { "members": [], "dn": user["dn"] }
            for m in user["attributes"]["memberUid"]:
                if m in ldap_users:
                    groups[cn]["members"].append(LdapGroupUser(
                        mail        = (mail := ldap_users[m]["mail"]),
                        name        = ''.join(mail.split('@')[:1]),
                        employee_id = m
                    ).dict())
        return groups

    @search_handle
    def get_members(
        self,
        group_name: str,
        get_raw: bool = False
    ) -> List[Union[str, LdapGroupUser]]:
        """通過 ``LDAP`` 搜索方法 (:func:`~Connection.search`)
        獲取指定群組名稱的成員名稱數組

        Args
        -------
        - group_name: (str) : 群組名稱 (部門名)
        - get_raw   : (bool): 是否獲取群組用戶數據 (:class:`~LdapGroupUser`)

        Returns
        -------
            list: 群組成員名稱或數據的數組

        Examples
        -------
        ```
        LdapHandler().get_members('TA')
        ```
        >>> ['Liu.Faye', 'Chen.Ke-ke', 'Chiang.Keith', ...]
        """
        members = []
        self.conn.search(
            LDAP_OU_BASE,
            f'(&(objectClass=posixGroup)(cn={group_name}))',
            attributes=[ 'cn', 'memberUid' ]
        )
        assert self.conn.entries, f'group {group_name} not found'
        for uid in self.conn.entries[0].memberUid.values:
            raw = self.get_user(uid)
            user = LdapGroupUser(mail=raw.mail, name=raw.mail.split('@')[0], employee_id=uid)
            member = user if get_raw else user.name
            if member not in members: members.append(member)
        return members

    def get_member_maps(self) -> Dict[str, List[str]]:
        """獲取固定群組的成員對應哈希表

        Returns
        -------
            dict: 群組成員對應哈希表
        """
        groups: List[str] = [ 'TA', 'SV', 'FV', 'SIT', 'LTE', 'FAE', 'TAO', 'Minister', 'Director' ]
        return { group: self.get_members(group) for group in groups }

    def get_ta_manager(self, default: str = 'Liu.Faye') -> str:
        """查找 `LDAP` 服務 `TA-Team` 群組中的主管名稱，從該群組
        成員與主管群組成員求交集 (:func:`~set.intersection`)

        Args
        -------
        - default: (str): 默認 Manager

        Attention
        -------
            注釋原本判斷邏輯的代碼，此處由於業務需求已固定為
            ``Liu.Faye``

        Returns
        -------
            str: `TA-Team` 主管名稱
        """
        # mems1 = set(self.get_members('Manager'))
        # mems2 = set(self.get_members('TA'))
        # managers = set.intersection(mems1, mems2)
        # manager = managers[-1] if managers else default
        # return manager if getenv('FASTAPI_ENV') == 'prod' else 'Liu.AllenJH'
        return default if getenv('FASTAPI_ENV') == 'prod' else 'Liu.AllenJH'

    @search_handle
    def get_owns_managers(self, name: str) -> List[str]:
        """獲取指定成員名稱的主管名稱數組

        1. 先獲取指定成員的工號
        2. 再用其工號獲取所有`所屬群組成員`
        3. 再找出所有`主管群組成員`的工號
        4. 求`所屬群組成員`和`主管群組成員`交集，得與該成員有關聯的主管工號
            (:func:`~set.intersection`)
        5. 依照關聯主管工號反向對應並獲取其名稱

        Args
        -------
        - name: (str): 成員名稱

        Returns
        -------
            list: 指定成員名稱的主管名稱數組
        """
        search_filter = f'(&(objectClass=inetOrgPerson)(mail={name}@*))'
        self.conn.search(LDAP_OU_BASE, search_filter, attributes=[ 'uid' ])
        assert self.conn.entries, f'user {name} not found'
        uid = self.conn.entries[0].uid.value
        search_filter = f'(&(objectClass=posixGroup)(memberUid={uid}))'
        self.conn.search(LDAP_OU_BASE, search_filter, attributes=[ 'memberUid' ])
        assert self.conn.entries, f'user {name} not belong to any group'
        member_uids = set(flatten([ e.memberUid.values for e in self.conn.entries ]))
        manager_raws = (self.get_members('Director', get_raw=True) +
                        self.get_members('Manager', get_raw=True) +
                        self.get_members('FAE_Manager', get_raw=True))
        manager_dict = { m.employee_id: m.name for m in manager_raws }
        owns_uids = set.intersection(set(manager_dict), member_uids)
        return [ manager_dict[uid] for uid in owns_uids ]

    @search_handle
    def is_readonly(self, id: str) -> bool:
        """驗證指定用戶工號是否在 `ReadOnly` 群組，如果在表示
        該用戶在 `Web` 頁面上，只能有``讀``的權限

        Returns
        -------
            bool: 是否維只讀用戶

        Examples
        -------
        ```
        LdapHandler().is_readonly('IES123456')
        ```
        >>> True
        """
        result = self.conn.search(
            LDAP_OU_BASE,
            '(&(objectClass=posixGroup)(cn=ReadOnly))',
            attributes=[ 'cn', 'memberUid' ]
        )
        assert result, f'user uid {id} not found'
        members = map(str.lower, self.conn.entries[0].memberUid.values)
        return id.lower() in members

    def close(self) -> None:
        self.conn.unbind()

class ADHandler:
    """通過上下文特性建立 `LDAP` 連線來存取公司 `AD` 用戶的數據

    Attributes
    ----------
    username : str
        用戶工號
    password : str
        開機密碼

    Methods
    -------
    parser() -> dict
        返回經整理過有效的用戶數據

    Examples
    -------
    ```
    with ADHandler('IEC070168', '12345678') as c:
        if not c:
            assert False, 'Authorized Failed'
        user_data = c.parser()
    ```
    >>> [{'attributes': {'cn': 'Micheal.Jordan 麥可喬丹 IES', ...}, ...}, ...]
    """
    def __init__(self, username: str, password: str) -> None:
        self.conn = None
        self.username = username
        self.password = password
        self.domain_map = {
            "iec": { "host": "10.3.2.3",   "domain": "iec" },
            "ies": { "host": "10.99.2.59", "domain": "ies" }
        }

    def __enter__(self) -> Union[Self, None]:
        username_format = get_user_name_array(self.username)
        if not username_format:
            return
        for user in [ username_format[0] ]:
            self.userid = user
            self.passwd = self.password
            self.domain = self.userid[:3].lower()
            self.depend = self.domain_map.get(self.domain)
            with suppress(LDAPBindError):
                self.conn = Connection(
                    Server(self.depend.get('host')),
                    f'{self.userid}@{self.depend.get("domain")}.inventec',
                    self.passwd,
                    auto_bind=True
                )
                return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        if not self.conn:
            return
        if self.conn.listening: self.conn.unbind()
        if any(( type, value, traceback )):
            assert False, value

    def search(self) -> Dict[str, Any]:
        self.basedn = f'dc={self.depend.get("domain")},dc=inventec'
        self.filter = f'(sAMAccountName={self.userid})'
        self.attributes = [
            'sAMAccountName',
            'mail',
            'cn',
            'department',
            'title',
            'telephoneNumber',
            'otherTelephone',
            'physicalDeliveryOfficeName'
        ]
        self.conn.search(
            search_base   = self.basedn,
            search_filter = self.filter,
            search_scope  = SUBTREE,
            attributes    = self.attributes
        )
        entries = loads(self.conn.response_to_json()).get('entries')
        return entries.pop() if entries else {}

    def parser(self) -> Dict[str, Any]:
        entries = self.search().get('attributes', {})
        cn_slices = entries.get('cn', 'Unknown.Unknown Unknown Unknown').split()
        return {
            "user_id"        : entries.get('sAMAccountName'),
            "user_cn"        : entries.get('cn'),
            "user_web_name"  : ' '.join(cn_slices[:2]),
            "full_name"      : cn_slices[1],
            "given_name"     : cn_slices[0].split('.')[-1],
            "first_name"     : cn_slices[0].split('.')[0],
            "user_mail"      : entries.get('mail'),
            "user_title"     : entries.get('title'),
            "user_department": entries.get('department'),
            "user_telephone1": entries.get('telephoneNumber'),
            "user_telephone2": entries.get('otherTelephone'),
            "user_location"  : entries.get('physicalDeliveryOfficeName')
        }
