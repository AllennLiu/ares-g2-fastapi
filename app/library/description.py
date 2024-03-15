#!/usr/bin/python3
# -*- coding: utf-8 -*-

from typing import Dict, List

class MetaTags:
    """如 API 新的路由描述可以在此添加"""
    DESC = [
        {
            "name"       : "Authenticate",
            "description": "**Sign in/out** your account with **`Inventec AD`**"
        },
        {
            "name"       : "OpenLDAP",
            "description": "Access `OpenLDAP` entiry **group by SIT**."
        },
        {
            "name"       : "OpenAI",
            "description": "**Azure `OpenAI`** util modules."
        },
        {
            "name"       : "Utility Tools",
            "description": "Including something `utility tools` or `useful APIs` here."
        },
        {
            "name"       : "E-mail",
            "description": "**Utility** sending **`E-mail`** common APIs"
        },
        {
            "name"       : "Scripts",
            "description": "**GitLab** `Script Project` management APIs."
        },
        {
            "name"       : "Reports",
            "description": "Summary **`TA-Team` work achievement** reports."
        },
        {
            "name"       : "Mission",
            "description": "Handling the **Script's Mission** **`create`** or **`update`** operation."
        },
        {
            "name"       : "Log Filter",
            "description": "Management of **Log Filter `Black/White`** list"
        },
        {
            "name"       : "Collection",
            "description": "**`Collection`** management for operating **`retrieve/download/upload/update`**"
        },
        {
            "name"       : "Automation",
            "description": "**ARES** `Automation Test` management APIs."
        }
    ]

    def __init__(self) -> None:
        self.tags_metadata = self.DESC

    def __call__(self, name: str = '', desc: str = '') -> None:
        print('Call this function with passing argument name and description.')
        if name and desc:
            self.tags_metadata.append({ "name": name, "desc": desc })

    def __repr__(self) -> List[Dict[str, str]]:
        return self.tags_metadata

    def __str__(self) -> str:
        return self.tags_metadata.__str__()
