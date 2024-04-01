#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .description import MetaTags

from os import getenv
from os.path import join
from typing import Dict, List
from functools import lru_cache
from pydantic import BaseSettings
from starlette.config import Config
from starlette.datastructures import Secret

GLOBAL_ROOT_PATH: str = '/usr/src'
APP_CONFIG: Config = Config(join(GLOBAL_ROOT_PATH, 'app', '.env'))
ARES_ENDPOINT: str = f'{APP_CONFIG("SERVICE_ARES_G2")}.{APP_CONFIG("DOMAIN_PROD")}'
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
  similiar as **[SMS](http://{APP_CONFIG('SERVICE_SMS')}.{APP_CONFIG(f'DOMAIN_{FASTAPI_ENV.upper()}')})**.
"""
    env: str = FASTAPI_ENV
    servers: List[Dict[str, str]] = [
        {
            "url"        : f"http://{APP_CONFIG('SERVICE_FASTAPI')}.{APP_CONFIG('DOMAIN_STAG')}",
            # "url"        : f"http://10.99.104.251:8787",
            "description": "Staging environment"
        },
        {
            "url"        : f"http://{APP_CONFIG('SERVICE_FASTAPI')}.{APP_CONFIG('DOMAIN_PROD')}",
            "description": "Production environment"
        }
    ]
    app_config: Config = APP_CONFIG
    openapi_tags: List[Dict[str, str]] = MetaTags().__repr__()

class TemplatePath(BaseSettings):
    root    : str = join(GLOBAL_ROOT_PATH, 'templates')
    mail    : str = join(GLOBAL_ROOT_PATH, 'templates/mail')
    project : str = join(GLOBAL_ROOT_PATH, 'templates/project')

class AzureOpenAI(BaseSettings):
    openai_api_type       : str = 'azure'
    openai_api_version    : str = '2023-05-15'
    openai_api_model      : str = APP_CONFIG('OPENAI_MODEL')
    azure_openai_endpoint : str = APP_CONFIG('OPENAI_ENDPOINT')
    azure_openai_api_key  : Secret = APP_CONFIG('OPENAI_API_KEY', cast=Secret)

@lru_cache
def get_settings() -> Settings:
    """Using lru cache to decrease frequency of file open"""
    return Settings()

settings: Settings = get_settings()
azure_openai: AzureOpenAI = AzureOpenAI()
template_path: TemplatePath = TemplatePath()
