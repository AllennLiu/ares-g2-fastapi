#!/usr/bin/python3
# -*- coding: utf-8 -*-

from openldap import LdapHandler
from library.config import GLOBAL_ROOT_PATH
from library.gitlabs import get_group_variable

from os import getenv
from mimetypes import MimeTypes
from pydantic import BaseModel, EmailStr
from starlette.datastructures import URL
from starlette.responses import JSONResponse
from fastapi import HTTPException, UploadFile
from fastapi.templating import Jinja2Templates
from typing import Any, Dict, List, Optional, Union
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

LDAP = LdapHandler()

EMAIL_ADMINS = [ e.mail for e in LDAP.get_members('Administrators', get_raw=True) ]
EMAIL_BODY_HTML = """
<html>
<body>
    <p style="color: royalblue;">Hi this test mail, thanks for using Fastapi-mail</p>
/body>
</html>
"""

EMAIL_NAME = 'ARES.NOTIFICATION.CENTER'
EMAIL_ADDRESS = f'{EMAIL_NAME}@inventec.com'
EMAIL_TEMPLATE_DIR = Jinja2Templates(directory='../templates/mail/')

EMAIL_LEVEL_NORMAL = {
    "X-Priority"       : "3",
    "X-MSMail-Priority": "Normal",
    "Importance"       : "Normal"
}

EMAIL_TEMPLATE = {
    "sender"  : f"ARES Notification Center <{EMAIL_ADDRESS}>",
    "subject" : "ARES Notification",
    "mailto"  : EMAIL_ADMINS,
    "cc"      : EMAIL_ADMINS,
    "bcc"     : EMAIL_ADMINS,
    "content" : EMAIL_BODY_HTML,
    "payload" : { "key": "value" },
    "response": {
        "success": JSONResponse(status_code=200, content={
            "message": "Sent E-mail Successfully"
        }),
        "failure": HTTPException(status_code=422, detail='Unexpectedly Exception')
    }
}

class Recipients(BaseModel):
    recipients : List[EmailStr]
    cc         : List[EmailStr]

class MailLogo(BaseModel):
    file         : UploadFile
    headers      : Dict[str, str]
    mime_type    : Optional[str] = 'image'
    mime_subtype : Optional[str] = 'png'

class EmailManager:

    def __init__(self) -> None:
        self.priority = {
            "P1": { "value": "1", "level": "High"   },
            "P2": { "value": "3", "level": "Normal" },
            "P3": { "value": "5", "level": "Low"    }
        }

    @classmethod
    def mailize(cls, members: List[str] = [], suffix: str = 'inventec.com'
    ) -> List[Union[EmailStr, str]]:
        return [ f'{name}@{suffix}' for name in set(members) if name.strip() ]

    @classmethod
    def render(cls, msg: MessageSchema, template: str, context: dict
    ) -> MessageSchema:
        cont = EMAIL_TEMPLATE_DIR.TemplateResponse(template, context=context)
        msg.html = cont.template.render(context)
        return msg

    @classmethod
    async def safety_send(cls, msg: MessageSchema, config: ConnectionConfig) -> None:
        try:
            mail = FastMail(config)
            await mail.send_message(msg)
        except Exception as err:
            print(f'ERROR: {err}')

    @classmethod
    def schema(cls, subject: str, recipients: List[Union[EmailStr, str]],
        cc: List[Union[EmailStr, str]], headers: Dict[str, Any] = EMAIL_LEVEL_NORMAL,
        bcc: List[Union[EmailStr, str]] = EMAIL_TEMPLATE["bcc"], subtype: str = 'html',
        attachments: List[UploadFile] = []
    ) -> MessageSchema:
        mime = MimeTypes()
        # including mail logo, e.g., "<img src='cid:logo_image'>"
        for name in [ 'gitlab', 'inventec' ]:
            f = f'{GLOBAL_ROOT_PATH}/static/image/logo_{name}.png'
            mime_type = mime.guess_type(f)
            attachments.append(
                MailLogo(
                    file = UploadFile(f'logo_{name}.png', open(f, mode='rb'), content_type=mime_type[0]),
                    headers = {
                        "Content-ID"         : f"<logo_{name}>",
                        "Content-Disposition": f"inline; filename=\"logo_{name}.png\""
                    }
                ).dict()
            )

        return MessageSchema(
            subject     = subject,
            recipients  = recipients,
            cc          = cc,
            bcc         = bcc,
            subtype     = subtype,
            headers     = headers,
            attachments = attachments
        )
        # test debug code:
        # return MessageSchema(
        #     subject=subject, recipients=EMAIL_TEMPLATE["bcc"], cc=EMAIL_TEMPLATE["bcc"], bcc=EMAIL_TEMPLATE["bcc"],
        #     subtype=subtype, headers=headers, attachments=attachments
        # )

    @classmethod
    def group_receiver(cls) -> Recipients:
        """Department E-mail group alias address.
        Such as: ``BU6-IPT-SIT@inventec.com`` or ``tao04cx@inventec.com``
        """
        addr = get_group_variable([ 'SIT_RECIPIENTS', 'SIT_RECIPIENTS_CC' ])
        return Recipients(
            recipients = addr.get('SIT_RECIPIENTS', '').split(';'),
            cc         = addr.get('SIT_RECIPIENTS_CC', '').split(';')
        )

    def get_header_by_priority(self, priority: str = 'P2') -> Dict[str, Any]:
        data = self.priority.get(priority)
        maps = data or self.priority.get('P2')
        return {
            "X-Priority"       : maps.get('value'),
            "X-MSMail-Priority": maps.get('level'),
            "Importance"       : maps.get('level')
        }

    def configure(
        self, base_url: Union[URL, str] = '', sender: Union[EmailStr, str] = EMAIL_ADDRESS
    ) -> ConnectionConfig:
        if not isinstance(base_url, str): base_url = str(base_url)

        # IPT Mail-relay settings
        conf = ConnectionConfig(
            MAIL_SERVER     = 'mailrelay-b.ies.inventec',
            MAIL_PORT       = 25,
            MAIL_SSL        = False,
            MAIL_TLS        = False,
            MAIL_FROM       = sender,
            MAIL_FROM_NAME  = EMAIL_TEMPLATE["sender"],
            MAIL_USERNAME   = '',
            MAIL_PASSWORD   = '',
            USE_CREDENTIALS = False,
            VALIDATE_CERTS  = False,

            # if no indicated SUPPRESS_SEND defaults to 0 (false) as below
            # SUPPRESS_SEND=1
        )

        # Google SMTP settings
        if getenv('FASTAPI_ENV') != 'prod':
            self._extracted_from_configure(conf)
        return conf

    # TODO Rename this here and in `configure`
    def _extracted_from_configure(self, conf) -> None:
        conf.MAIL_SERVER     = 'smtp.gmail.com'
        conf.MAIL_PORT       = 465
        conf.MAIL_SSL        = True
        conf.MAIL_USERNAME   = 'tom951086@gmail.com'
        conf.MAIL_PASSWORD   = '>>>>>><<<<<<'
        conf.USE_CREDENTIALS = True
