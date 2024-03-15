#!/usr/bin/python3
# -*- coding: utf-8 -*-

from params import json_parse
from iteration import flatten, uniq
from cacher import RedisContextManager
from readme import get_readme_associates
from gitlabs import getReadme, Project, ProjectTag
from schemas import HALFYEAR_MAPS, RedisDB, MissionDB

from re import sub
from json import loads, dumps
from collections import defaultdict
from typing import Any, Dict, List, Union, Iterable

class WorkAchievement:

    def __init__(self, duration: str, projects: List[Project]) -> None:
        self.duration = duration
        self.projects = projects
        self.yyyy = self.duration.split('-')[0]
        self.half = self.duration.split('-')[1]

    def tag_splice(self, tag: ProjectTag, index: int = 1) -> str:
        created_at = dict(tag.commit.items())["created_at"]
        return sub(r'[^\d{4}\-\d{2}].*', '', created_at).split('-')[index]

    def parse_developer(self, project: Project, tag: ProjectTag) -> str:
        if int(self.yyyy) < 2020 or self.duration == '2020-H1':
            address = tag.commit["committer_email"].split('@')[0].split('.')
            return '.'.join([ e[0].upper() + e[1:] for e in address ])
        else:
            readme = getReadme(project, ref=tag.commit.get('id'))
            return get_readme_associates(readme).get('developer', '')

    def group_by_duration(self) -> Dict[str, list]:
        """
        Project tags handler with specified duration:
        developer will be selected with duration if it is
        lower equals 2020-H1, and then data will group by
        committer otherwise group by developer with it's
        readme contents.
        """
        return {
            i.name: [
                {
                    **dict(j.commit.items()),
                    "version"  : j.name,
                    "developer": self.parse_developer(i ,j)
                }
                for j in tags if self.tag_splice(j, 0) == self.yyyy
                and int(self.tag_splice(j)) in HALFYEAR_MAPS[self.half]
            ]
            for i in self.projects
            if i.namespace["name"] == 'TA-Team' and (tags := i.tags.list(get_all=True))
        }

    def group_by_developer(self) -> Dict[str, list]:
        """
        Merge two dimensional lists in a the one.
        """
        duration = self.group_by_duration()
        group_tags = list(flatten([
            [ { **e, "script_name": k } for e in duration[k] ]
            for k in duration if duration[k]
        ]))
        return {
            i: [ j for j in group_tags if j["developer"] == i ]
            for i in { e["developer"] for e in group_tags }
        }

class AutomationSummary:

    def __init__(self) -> None:
        """
        Variable "self.bkmfuncs" is the BKM function number
        in ARES means BKM which function it belongs to.
        BKM function map:
        1: BIOS, 2: BMC, 3: SV-A,
        4: SV-B, 5: RMC, 14: FAE
        """
        self.adata = {}
        self.src_data = {}
        self.customers = []
        self.excepts = [ 'test', 'tateam' ]
        self.functions = [ 'BIOS', 'BMC', 'SV' ]
        self.bkmfuncs = list(range(1,6)) + [ 14 ]
        self.bkm_automated = {
            "yes"   : { "bkm_automated": [ 1 ] },
            "yes_og": { "bkm_automated": [ 1, 2 ] }
        }
        self.bkm_map = {
            "BIOS"         : [ 'BIOS' ],
            "BMC"          : [ 'BMC', 'RMC', 'PMC' ],
            "SV"           : [ 'SV' ],
            "PRE-CONDITION": [ 'PRE-CONDITION' ],
            "SIT"          : [ 'BIOS', 'BMC', 'SV', 'RMC', 'PMC', 'PRE-CONDITION' ]
        }
        self.class_map = { "func": list(self.bkm_map) }
        self.cust_func_map = { "Baidu": [ "RMC" ], "JD": [ "PMC" ] }
        self.cust_func_map_val = list(flatten(self.cust_func_map.values()))

    def __call__(self) -> None:
        print(self.class_map)

    def __repr__(self) -> str:
        return dumps(self.bkm_map, indent=4, sort_keys=True)

    def query_raws(self) -> Union[bool, None]:
        """
        Cache the data of ARES BKMs for improving API
        request, and this gonna be use the kubernetes
        polling cronjob.
        """
        with RedisContextManager(decode_responses=True) as r:
            if not (keys := r.hkeys(name := RedisDB.ares_bkms)):
                return False
            raws = { k: loads(r.hget(name, k)) for k in keys }
        self.src_data = raws.get('raws', {})
        self.customers = raws.get('customers', [])

    def findByKey(self, key: str = '', nums: Iterable[str] = []) -> int:
        return len([ e for e in self.df if e[key] in nums ])

    def findBy2Key(self, key1: str = '', key2: str = '', nums: Iterable[str] = [],
        key2_value: Iterable[bool] = [], dataframes: List[Any] = []) -> int:
        l = [ e for e in dataframes if e[key1] in nums and e[key2] in key2_value ]
        return len(l)

    def findByKeys(self, rules: Dict[str, Any] = {}) -> int:
        rule_0, rule_1 = {}, {}
        for k in rules:
            if k == 'bkm_main_tag':
                rule_0[k] = rules[k]
            elif k == 'bkm_automated':
                rule_1[k] = rules[k]
        return len([
            s for s in [
                (e if (
                    e[list(rule_0)[0]] in list(rule_0.values())[0] and
                    e[list(rule_1)[0]] in list(rule_1.values())[0]
                ) else {})
                for e in self.df if list(rule_1)[0] in e
            ] if s
        ])

    def findBy2Keys(self, rules: Dict[str, Any] = {}, key2: str = '',
                    dataframes: List[Any] = []) -> int:
        rule_0, rule_1, rule_2 = {}, {}, {}
        for k in rules:
            if k == 'bkm_main_tag':
                rule_0[k] = rules[k]
            elif k == 'bkm_automated':
                rule_1[k] = rules[k]
            elif k == key2:
                rule_2[k] = rules[k]
        return len([
            s for s in [
                (e if (
                    e[list(rule_0)[0]] in list(rule_0.values())[0] and
                    e[list(rule_1)[0]] in list(rule_1.values())[0] and
                    e[list(rule_2)[0]] in list(rule_2.values())[0]
                ) else {})
                for e in dataframes if list(rule_1)[0] in e
            ] if s
        ])

    def findByTags(self, key: str, func: str, automated: str = '') -> int:
        """
        This function will follow up the rule variable:
        "self.bkm_automated" and it depends on main key
        bkm_automated of dict data.
        List comprehension if statement as following conditions:
        1.if automated not in self.bkm_automated:
            bkm_automated in [1, 2, 3] and bkm_main_tag and
            bkm_customer_tag all exists.
            (return total_bkm_num)
        2.elif automated in self.bkm_automated:
            bkm_automated equals 1 and bkm_main_tag and
            bkm_customer_tag all exists.
            (return ares_bkm_num)
        3.else:
            empty dict data for ignoring in outside list
            comprehension.
            (return {})
        """
        return len([
            i for i in [
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.cust_func_map[key]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and automated not in self.bkm_automated
                    and key in self.cust_func_map
                    and func in self.cust_func_map_val)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.cust_func_map[key]
                    and j["bkm_automated"] in
                    self.bkm_automated[automated]["bkm_automated"]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and 'bkm_automated' in j
                    and automated in self.bkm_automated
                    and key in self.cust_func_map
                    and func in self.cust_func_map_val)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.bkm_map[func]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and automated not in self.bkm_automated)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.bkm_map[func]
                    and j["bkm_automated"] in
                    self.bkm_automated[automated]["bkm_automated"]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and 'bkm_automated' in j
                    and automated in self.bkm_automated)
                else {}
                for j in self.df
            ] if i
        ])

    def findBy2Tags(self, key: str, func1: str, func2: str, automated: str = '') -> int:
        return len([
            i for i in [
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.cust_func_map[key]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and automated not in self.bkm_automated
                    and key in self.cust_func_map
                    and func1 in self.cust_func_map_val)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.cust_func_map[key]
                    and j["bkm_automated"] in
                    self.bkm_automated[automated]["bkm_automated"]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and 'bkm_automated' in j
                    and automated in self.bkm_automated
                    and key in self.cust_func_map
                    and func1 in self.cust_func_map_val)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.bkm_map[func1]
                    and j["bkm_sub_tag"] in func2
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and 'bkm_sub_tag' in j
                    and automated not in self.bkm_automated)
                else
                (
                    j if key in j["bkm_customer_tag"]
                    and j["bkm_main_tag"] in self.bkm_map[func1]
                    and j["bkm_sub_tag"] in func2
                    and j["bkm_automated"] in
                    self.bkm_automated[automated]["bkm_automated"]
                    else {}
                )
                if ('bkm_customer_tag' in j
                    and 'bkm_main_tag' in j
                    and 'bkm_sub_tag' in j
                    and 'bkm_automated' in j
                    and automated in self.bkm_automated)
                else {}
                for j in self.df
            ] if i
        ])

    def sum(self, key: str, entry: Dict[str, Any]) -> int:
        value = 0
        for v in entry.values():
            raw = defaultdict(int, v)
            value += raw[key]
        return value

    def sum_sms(self, annual: str, entry: Dict[str, Any]) -> int:
        value = 0
        vals = flatten(map(lambda x: list(x.values()), entry.values()))
        for v in vals:
            if not isinstance(v, dict): continue
            raw = defaultdict(dict, v)
            val = defaultdict(int, raw[annual])
            value += val["sms_complete"]
        return value

    def bkm_filter(self, entry: Dict[str, Any], bkms: List[dict]) -> Dict[str, Any]:
        bkm_ids = list(entry.get('bkms', {}))
        try:
            assert bkm_ids, 'bkm entry is empty'
            items = [ e for e in bkms if e.get('bkm_id') == int(bkm_ids[0]) ]
            assert items, f'search BKM ID {bkm_ids[0]} not found'
            return items.pop()
        except:
            return {}

    def weird(self, n: Union[int, float], m: Union[int, float, Any]) -> float:
        """
        Preventing the zero division error of calculation,
        this function will detect the second value (var:m),
        then return float value that after two numbers at
        dot position.
        At last it will format to string and then convert
        to float number.
        """
        return float(f'{float(n / m if m else 0) * 100:.2f}')

    def source(self) -> None:
        """
        Source data from ARES API get method, generate dataframe
        for this object callable.
        DataFrame formula as below:
        df = {
            "bkm_main_tag": self.bkm_map["SIT"],
            "bkm_function": self.bkmfuncs + null
        }
        null -> this key not exists in it's object
        """
        self.query_raws()
        self.class_map = { **self.class_map, "cust": self.customers }
        self.df = [
            i for i in [
                (
                    j if j["bkm_main_tag"] in self.bkm_map["SIT"]
                    and j["bkm_function"] in self.bkmfuncs
                    else {}
                )
                if 'bkm_main_tag' in j and 'bkm_function' in j
                else (j if j["bkm_main_tag"] in self.bkm_map["SIT"] else {})
                if 'bkm_main_tag' in j and 'bkm_function' not in j
                else {}
                for j in self.src_data["list"]
            ] if i
        ]
        self.dfId = { e["bkm_id"]: e for e in self.df }
        self.TRDCdf = [
            i for i in [
                (
                    j if j["bkm_main_tag"] in self.bkm_map["SIT"]
                    and j["bkm_function"] in self.bkmfuncs + [ 15 ]
                    else {}
                )
                if 'bkm_main_tag' in j and 'bkm_function' in j
                else (j if j["bkm_main_tag"] in self.bkm_map["SIT"] else {})
                if 'bkm_main_tag' in j and 'bkm_function' not in j
                else {}
                for j in self.src_data["list"]
            ] if i
        ]
        self.TRDCdfId = { e["bkm_id"]: e for e in self.TRDCdf }
        """
        Source data from SMS database in Redis, retrieve the
        update missions data.
        And parsing the data for script's BKM coverage summary.
        """
        self.mdata = {}
        with RedisContextManager(decode_responses=True) as r:
            keys = r.hkeys(name := MissionDB.update)
            if keys: self.mdata |= { k: json_parse(r.hget(name, k)) for k in keys }

    def individualize_sms_bkm(self) -> List[Union[str, int]]:
        """
        Retrieve all script's BKMs ID from SMS, and remove the
        duplicated items for duplicated calculation.
        return list data []
        """
        data = flatten([
            list(self.mdata[k]["bkms"]) for k in self.mdata
            if 'bkms' in self.mdata[k] and k.lower().split('-')[1] not in self.excepts
        ])
        return uniq(data)

    def summary_ares(self) -> None:
        """
        DataFrame Calculation/Filter as following conditions:
        Formula: [ares_coverage = ares_bkm_num / total_bkm_num]
            - total_bkm_num: {"bkm_automated": [1, 2, 3]}
            - ares_bkm_num: {"bkm_automated": [1]}
        """
        self.adata = {
            "func": {
                k: {
                    "total_bkm_num": self.findByKey(
                        'bkm_main_tag', self.bkm_map[k]
                    ),
                    "ares_bkm_num": self.findByKeys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes"]
                        }
                    ),
                    "ares_coverage": self.weird(
                        self.findByKeys(
                            {
                                "bkm_main_tag": self.bkm_map[k],
                                **self.bkm_automated["yes_og"]
                            }
                        ),
                        self.findByKey('bkm_main_tag', self.bkm_map[k])
                    ),
                    "ares_auto_bkm_num": self.findByKeys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes_og"]
                        }
                    ),
                    "ares_auto_coverage": self.weird(
                        self.findByKeys(
                            {
                                "bkm_main_tag": self.bkm_map[k],
                                **self.bkm_automated["yes"]
                            }
                        ),
                        self.findByKeys(
                            {
                                "bkm_main_tag": self.bkm_map[k],
                                **self.bkm_automated["yes_og"]
                            }
                        )
                    )
                }
                for k in self.class_map["func"]
            },
            "cust": {
                k: {
                    f: {
                        "total_bkm_num": self.findByTags(k, f),
                        "ares_bkm_num" : self.findByTags(k, f, 'yes'),
                        "ares_coverage": self.weird(
                            self.findByTags(k, f, 'yes_og'),
                            self.findByTags(k, f)
                        ),
                        "ares_auto_bkm_num" : self.findByTags(k, f, 'yes_og'),
                        "ares_auto_coverage": self.weird(
                            self.findByTags(k, f, 'yes'),
                            self.findByTags(k, f, 'yes_og')
                        )
                    }
                    for f in self.functions + self.cust_func_map[k]
                } if k in self.cust_func_map
                else {
                    f: {
                        "total_bkm_num": self.findByTags(k, f),
                        "ares_bkm_num" : self.findByTags(k, f, 'yes'),
                        "ares_coverage": self.weird(
                            self.findByTags(k, f, 'yes_og'),
                            self.findByTags(k, f)
                        ),
                        "ares_auto_bkm_num" : self.findByTags(k, f, 'yes_og'),
                        "ares_auto_coverage": self.weird(
                            self.findByTags(k, f, 'yes'),
                            self.findByTags(k, f, 'yes_og')
                        )
                    }
                    for f in self.functions
                }
                for k in self.class_map["cust"]
            },
        }

        # for SV function
        for v, m in {
            'SV-computing':'Computing',
            'SV-network'  :'Network',
            'SV-system'   :'System',
            'SV-storage'  :'Storage'
        }.items():
            for k in self.class_map["cust"]:
                self.adata["cust"][k][v]= {
                    "total_bkm_num": self.findBy2Tags(k, 'SV', m),
                    "ares_bkm_num" : self.findBy2Tags(k, 'SV', m, 'yes'),
                    "ares_coverage": self.weird(
                        self.findBy2Tags(k, 'SV', m, 'yes_og'),
                        self.findBy2Tags(k, 'SV', m)
                    ),
                    "ares_auto_bkm_num" : self.findBy2Tags(k, 'SV', m, 'yes_og'),
                    "ares_auto_coverage": self.weird(
                        self.findBy2Tags(k, 'SV', m, 'yes'),
                        self.findBy2Tags(k, 'SV', m, 'yes_og')
                    )
                }

    def summary_sms(self) -> Dict[str, Any]:
        """
        Iterate BKMs and insert the value of coverage and summary.
        (Merge dict data between ARES summary and SMS summary)
        self.dfId: The BKM data using it's ID to be the main key.
        """
        sms_bkms = self.individualize_sms_bkm()
        ret = {
            "cust": self.adata["cust"],
            "func": {
                k: {
                    **self.adata["func"][k],
                    "sms_bkm_num": len([
                        a for a in [
                            (
                                self.dfId[int(b)]
                                if (self.dfId[int(b)]["bkm_main_tag"]
                                    in self.bkm_map[k])
                                else {}
                            )
                            for b in sms_bkms if int(b) in self.dfId
                        ] if a
                    ]),
                    "sms_coverage": self.weird(
                        len([
                            a for a in [
                                (
                                    self.dfId[int(b)]
                                    if (self.dfId[int(b)]["bkm_main_tag"]
                                        in self.bkm_map[k])
                                    else {}
                                )
                                for b in sms_bkms if int(b) in self.dfId
                            ] if a
                        ]),
                        self.adata["func"][k]["ares_auto_bkm_num"]
                    )
                }
                for k in self.class_map["func"]
            },
            "TRDC": {}
        }

        #add SV computing, network, system, storage, other
        for k,v in {
            'SVcomputing':'Computing',
            'SVnetwork'  :'Network',
            'SVsystem'   :'System',
            'SVstorage'  :'Storage'
        }.items():
            ret["func"][k] = {
                "total_bkm_num": self.findBy2Key(
                    'bkm_main_tag',
                    'bkm_sub_tag',
                    self.bkm_map['SV'],
                    [v], self.df
                ),
                "ares_bkm_num": self.findBy2Keys(
                    {
                        "bkm_main_tag": self.bkm_map['SV'],
                        **self.bkm_automated["yes"],
                        "bkm_sub_tag": [v]
                    },
                    "bkm_sub_tag", self.df
                ),
                "ares_coverage": self.weird(
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map['SV'],
                            **self.bkm_automated["yes_og"],
                            "bkm_sub_tag": [v]
                        },
                        "bkm_sub_tag", self.df
                    ),
                    self.findBy2Key(
                        'bkm_main_tag',
                        'bkm_sub_tag',
                        self.bkm_map['SV'],
                        [v], self.df)
                ),
                "ares_auto_bkm_num": self.findBy2Keys(
                    {
                        "bkm_main_tag": self.bkm_map['SV'],
                        **self.bkm_automated["yes_og"],
                        "bkm_sub_tag": [v]
                    },
                    "bkm_sub_tag", self.df
                ),
                "ares_auto_coverage": self.weird(
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map['SV'],
                            **self.bkm_automated["yes"],
                            "bkm_sub_tag": [v]
                        },
                        "bkm_sub_tag", self.df
                    ),
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map['SV'],
                            **self.bkm_automated["yes_og"],
                            "bkm_sub_tag": [v]
                        },
                        "bkm_sub_tag", self.df)
                ),
                "sms_bkm_num": len([
                    a for a in [
                        (
                            self.dfId[int(b)]
                            if (self.dfId[int(b)]["bkm_main_tag"]
                                in self.bkm_map['SV']
                                and self.dfId[int(b)]["bkm_sub_tag"]
                                in [v])
                            else {}
                        )for b in sms_bkms if int(b) in self.dfId
                    ] if a
                ]),
                "sms_coverage": self.weird(
                    len([
                        a for a in [
                            (
                                self.dfId[int(b)]
                                if (self.dfId[int(b)]["bkm_main_tag"]
                                    in self.bkm_map['SV']
                                    and self.dfId[int(b)]["bkm_sub_tag"]
                                    in [v])
                                else {}
                            )for b in sms_bkms if int(b) in self.dfId
                        ] if a
                    ]),
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map['SV'],
                            **self.bkm_automated["yes_og"],
                            "bkm_sub_tag": [v]
                        },
                        "bkm_sub_tag", self.df
                    )
                )
            }
        ### end SV function ###

        ##add TRDC function
        func_index = { e: True for e in [ 'BIOS', 'BMC', 'SV', 'SIT' ] }
        for k, v in func_index.items():
            ret["TRDC"][k] = {
                "total_bkm_num": self.findBy2Key(
                    'bkm_main_tag',
                    'bkm_belong_to_trdc',
                    self.bkm_map[k],
                    [v], self.TRDCdf
                ),
                "ares_bkm_num": self.findBy2Keys(
                    {
                        "bkm_main_tag": self.bkm_map[k],
                        **self.bkm_automated["yes"],
                        "bkm_belong_to_trdc": [v]
                    },
                    "bkm_belong_to_trdc", self.TRDCdf
                ),
                "ares_coverage": self.weird(
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes_og"],
                            "bkm_belong_to_trdc": [v]
                        },
                        "bkm_belong_to_trdc", self.TRDCdf
                    ),
                    self.findBy2Key('bkm_main_tag',
                                        'bkm_belong_to_trdc',
                                        self.bkm_map[k],
                                        [v], self.TRDCdf)
                ),
                "ares_auto_bkm_num": self.findBy2Keys(
                    {
                        "bkm_main_tag": self.bkm_map[k],
                        **self.bkm_automated["yes_og"],
                        "bkm_belong_to_trdc": [v]
                    },
                    "bkm_belong_to_trdc", self.TRDCdf
                ),
                "ares_auto_coverage": self.weird(
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes"],
                            "bkm_belong_to_trdc": [v]
                        },
                        "bkm_belong_to_trdc", self.TRDCdf
                    ),
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes_og"],
                            "bkm_belong_to_trdc": [v]
                        },
                        "bkm_belong_to_trdc", self.TRDCdf
                    )
                ),
                "sms_bkm_num": len([
                    a for a in [
                        (
                            self.TRDCdfId[int(b)]
                            if (self.TRDCdfId[int(b)]["bkm_main_tag"]
                                in self.bkm_map[k]
                                and self.TRDCdfId[int(b)]["bkm_belong_to_trdc"]
                                in [v])
                            else {}
                        ) for b in sms_bkms if int(b) in self.TRDCdfId
                    ] if a
                ]),
                "sms_coverage": self.weird(
                    len([
                        a for a in [
                            (
                                self.TRDCdfId[int(b)]
                                if (self.TRDCdfId[int(b)]["bkm_main_tag"]
                                    in self.bkm_map[k]
                                    and self.TRDCdfId[int(b)]["bkm_belong_to_trdc"]
                                    in [v])
                                else {}
                            )for b in sms_bkms if int(b) in self.TRDCdfId
                        ] if a
                    ]),
                    self.findBy2Keys(
                        {
                            "bkm_main_tag": self.bkm_map[k],
                            **self.bkm_automated["yes_og"],
                            "bkm_belong_to_trdc": [v]
                        },
                        "bkm_belong_to_trdc", self.TRDCdf
                    )
                )
            }
        ### end TRDC function ###
        return ret
