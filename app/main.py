#!/usr/bin/python3
# -*- coding: utf-8 -*-

from library.config import settings
from library.helpers import read_readme

from os.path import join, abspath
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html

# include routers
from routers import authorize, session, openldap, openai, utility, postman, project, scripts, reports, mission, logfilter, collection, automation

readme = read_readme('../README.md')

app = FastAPI(
    title        = ' '.join(readme.get('project_name').split('-')),
    description  = settings.desc,
    version      = readme.get('version'),
    openapi_tags = settings.openapi_tags,
    servers      = settings.servers[::-1] if settings.env == 'prod' else settings.servers,
    docs_url     = None,
    redoc_url    = None
)

app.mount('/static', StaticFiles(directory=join(abspath('..'), 'static/swagger-ui')), name='static')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

@app.get('/docs', include_in_schema=False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f'{app.title} - Swagger UI',
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url='/static/swagger-ui-bundle.js',
        swagger_css_url='/static/swagger-ui.css',
        swagger_favicon_url='/static/favicon.png'
    )

@app.get('/redoc', include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f'{app.title} - ReDoc',
        redoc_js_url='/static/redoc.standalone.js',
    )

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

# include router instance
routers = [ authorize, session, openldap, openai, utility, postman, project, scripts, reports, mission, logfilter, collection, automation ]
for router in routers:
    app.include_router(router.router)
