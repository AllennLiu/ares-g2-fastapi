#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from routers.authorize import User, DEPENDS_USER
from library.params import validate_json, json_parse
from library.mailer import EMAIL_TEMPLATE, EMAIL_TEMPLATE_DIR, FastMail, MessageSchema, EmailManager

from jinja2 import Template
from pydantic import EmailStr
from typing import List, Annotated
from starlette.responses import JSONResponse
from jinja2.exceptions import TemplateNotFound
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form

router = APIRouter()
postman = EmailManager()

FORM_PAYLOADS = Form(default=EMAIL_TEMPLATE["payload"], description='Require `JSON Array`')
FOMR_PRIORITY = Form(default='P2', description='`Priority Mail Headers`', regex='^P[1-3]$')

@router.post('/api/v1/postman/html', tags=['E-mail'])
async def send_email_with_html_content(
    request   : Request,
    subject   : Annotated[str, Form(EMAIL_TEMPLATE["subject"])] = EMAIL_TEMPLATE["subject"],
    sender    : Annotated[str, Form(EMAIL_TEMPLATE["sender"])] = EMAIL_TEMPLATE["sender"],
    recipients: List[EmailStr] = Form(...),
    cc        : List[EmailStr] = Form(EMAIL_TEMPLATE["mailto"]),
    content   : Annotated[str, Form(EMAIL_TEMPLATE["content"])] = EMAIL_TEMPLATE["content"],
    priority  : Annotated[str, FOMR_PRIORITY] = FOMR_PRIORITY,
    attachment: Annotated[UploadFile, File(None)] = None) -> JSONResponse:
    recipients = map(EmailStr.validate, recipients)
    conf = postman.configure(request.base_url)
    msg  = MessageSchema(
        subject     = subject,
        recipients  = recipients,
        cc          = cc,
        html        = content,
        subtype     = 'html',
        headers     = postman.get_header_by_priority(priority),
        attachments = [ attachment ] if attachment else []
    )
    conf.MAIL_FROM = sender
    mail = FastMail(conf)
    await mail.send_message(msg)
    return EMAIL_TEMPLATE["response"]["success"]

@router.post('/api/v1/postman/template', tags=['E-mail'])
async def send_email_with_html_template(
    request   : Request,
    subject   : Annotated[str, Form(EMAIL_TEMPLATE["subject"])] = EMAIL_TEMPLATE["subject"],
    sender    : Annotated[str, Form(EMAIL_TEMPLATE["sender"])] = EMAIL_TEMPLATE["sender"],
    recipients: List[EmailStr] = Form(...),
    cc        : List[EmailStr] = Form(EMAIL_TEMPLATE["mailto"]),
    template  : Annotated[str, Form(..., description='`HTML Only`', regex='^\w+\.html$')] = 'test.html',
    payload   : Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS,
    priority  : Annotated[str, FOMR_PRIORITY] = FOMR_PRIORITY,
    attachment: Annotated[UploadFile, File(None)] = None,
    user      : Annotated[User, DEPENDS_USER] = DEPENDS_USER) -> JSONResponse:
    conf = postman.configure(request.base_url)
    msg = EmailManager.schema(
        subject,
        recipients,
        cc,
        postman.get_header_by_priority(priority),
        attachments=[ attachment ] if attachment else []
    )
    conf.MAIL_FROM = sender
    if not validate_json(payload):
        raise HTTPException(status_code=422, detail='Invalid Payload')
    payloads = json_parse(payload)
    try:
        content = EMAIL_TEMPLATE_DIR.TemplateResponse(
            template, context={ "request": request, **payloads, "user": user })
    except TemplateNotFound as err:
        raise HTTPException(status_code=404, detail=f'{err} Not Found') from err
    msg.html = content.template.render(payloads)
    mail = FastMail(conf)
    await mail.send_message(msg)
    return EMAIL_TEMPLATE["response"]["success"]

@router.post('/api/v1/postman/template/uploaded', tags=['E-mail'])
async def send_email_with_html_uploaded_template(
    request    : Request,
    subject    : Annotated[str, Form(EMAIL_TEMPLATE["subject"])] = EMAIL_TEMPLATE["subject"],
    sender     : Annotated[str, Form(EMAIL_TEMPLATE["sender"])] = EMAIL_TEMPLATE["sender"],
    recipients : List[EmailStr] = Form(...),
    cc         : List[EmailStr] = Form(EMAIL_TEMPLATE["mailto"]),
    template   : Annotated[UploadFile, File(...)] = File(...),
    payload    : Annotated[str, FORM_PAYLOADS] = FORM_PAYLOADS,
    priority   : Annotated[str, FOMR_PRIORITY] = FOMR_PRIORITY,
    attachment : Annotated[UploadFile, File(None)] = None) -> JSONResponse:
    conf = postman.configure(request.base_url)
    msg = EmailManager.schema(
        subject,
        recipients,
        cc,
        postman.get_header_by_priority(priority),
        attachments=[ attachment ] if attachment else []
    )
    conf.MAIL_FROM = sender
    if not validate_json(payload):
        raise HTTPException(status_code=422, detail='Invalid Payload')
    if template.content_type != 'text/html':
        raise HTTPException(status_code=422, detail='Unexpected HTML File')
    content = await template.read()
    temp = Template(content.decode('utf-8'))
    msg.html = temp.render(json_parse(payload))
    mail = FastMail(conf)
    await mail.send_message(msg)
    return EMAIL_TEMPLATE["response"]["success"]
