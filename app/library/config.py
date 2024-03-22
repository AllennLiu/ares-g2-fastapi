#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .description import MetaTags

from os import getenv
from json import loads
from os.path import join
from pathlib import Path
from functools import lru_cache
from pydantic import BaseSettings
from typing import Any, Dict, List, Type

GLOBAL_ROOT_PATH: str = '/usr/src'

@lru_cache
def get_app_config() -> Dict[str, Any]:
    return loads(Path(join(GLOBAL_ROOT_PATH, 'app/settings.json')).read_text())

APP_CONFIG = get_app_config()
ARES_ENDPOINT = f'{APP_CONFIG["service"]["ares_g2"]}.{APP_CONFIG["domain"]["prod"]}'
FASTAPI_ENV = getenv('FASTAPI_ENV') if getenv('FASTAPI_ENV') else 'prod'

def url_to_ares(name: str = '', type: str = 'create') -> str:
    """替換 root URL Link 為 ARES 的前端連結"""
    return f'http://{ARES_ENDPOINT}/mission/{type}/{name}/edit'

class Settings(BaseSettings):
    desc: str = f"""\
### Topic:
- The **separated `Backend API`** web service for
  **[ARES G2](http://{ARES_ENDPOINT})** new release.
- This service <u>is going to implement</u> that **`API's function`**
  similiar as **[SMS](http://{APP_CONFIG['service']['sms']}.{APP_CONFIG['domain'][FASTAPI_ENV]})**.
"""
    env: str = FASTAPI_ENV
    servers: List[Dict[str, str]] = [
        {
            # "url"        : f"http://{APP_CONFIG['service']['fastapi']}.{APP_CONFIG['domain']['stag']}",
            "url"        : f"http://10.99.104.251:8787",
            "description": "Staging environment"
        },
        {
            "url"        : f"http://{APP_CONFIG['service']['fastapi']}.{APP_CONFIG['domain']['prod']}",
            "description": "Production environment"
        }
    ]
    app_config: Dict[str, Any] = APP_CONFIG
    openapi_tags: List[Dict[str, str]] = MetaTags().__repr__()

class TemplatePath(BaseSettings):
    root    : str = join(GLOBAL_ROOT_PATH, 'templates')
    mail    : str = join(GLOBAL_ROOT_PATH, 'templates/mail')
    project : str = join(GLOBAL_ROOT_PATH, 'templates/project')

class AzureOpenAI(BaseSettings):
    openai_api_type       : str = 'azure'
    openai_api_version    : str = '2023-05-15'
    openai_api_model      : str = APP_CONFIG["openai"]["model"]
    azure_openai_endpoint : str = APP_CONFIG["openai"]["endpoint"]
    azure_openai_api_key  : str = APP_CONFIG["openai"]["api_key"]

@lru_cache
def get_settings() -> Settings:
    """Using lru cache to decrease frequency of file open"""
    return Settings()

settings: Type[Settings] = get_settings()
azure_openai = AzureOpenAI()
template_path = TemplatePath()
