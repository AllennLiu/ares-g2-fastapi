#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
sys.path.append('library')

from library.moment import Holiday
from library.helpers import catch_except_retry, version_increment, version_class

from PIL import Image
from io import BytesIO
from numpy import asarray
from typing import Annotated
from datetime import datetime
from pytesseract import pytesseract
from starlette.responses import JSONResponse, HTMLResponse
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from cv2 import COLOR_RGB2BGR, THRESH_BINARY_INV, threshold, cvtColor

router = APIRouter()

FILE_PICTURE = File(..., description='Require a `Picture`')
FORM_VERSION = Form('0.0.0', description='Increment `minor` version')
FORM_RELEASE = Form(False, description='Force to `release` version')

@catch_except_retry()
def utility_image_extract(file: UploadFile) -> str:
    binary = file.file.read()
    image = Image.open(BytesIO(binary))
    cvt_img = cvtColor(asarray(image), COLOR_RGB2BGR)
    _, bin_inv = threshold(cvt_img, 200, 130, THRESH_BINARY_INV)
    white_text = pytesseract.image_to_string(Image.fromarray(bin_inv))
    origin = pytesseract.image_to_string(image)
    return f'{white_text}\n{"-" * 80}\n{origin}'

@router.get('/api/v1/utility/calendar/holidays', tags=['Utility Tools'])
async def get_holidays_by_calendar(year: int = datetime.now().year,
    detail: bool = True, weekend: bool = True) -> JSONResponse:
    _exhausted, weekends = object(), [ 'Sunday', 'Saturday' ]
    _holidays, holidays = Holiday.getdates(year, instance=True), []
    if next(_holidays, _exhausted) is _exhausted:
        raise HTTPException(status_code=404, detail="Not Implemented")
    for holiday in _holidays:
        if not weekend and holiday.holiday_name in weekends: continue
        holidays.append(holiday.dict() if detail else holiday.date)
    return JSONResponse(status_code=200, content={ "holidays": holidays })

@router.post('/api/v1/utility/image/extract', tags=['Utility Tools'])
def image_to_text(file: Annotated[UploadFile, FILE_PICTURE] = FILE_PICTURE) -> HTMLResponse:
    return HTMLResponse(status_code=200, content=utility_image_extract(file))

@router.post('/api/v1/utility/version/increment', tags=['Utility Tools'])
async def let_version_increment(
    version: Annotated[str, FORM_VERSION] = FORM_VERSION,
    release: Annotated[bool, FORM_RELEASE] = FORM_RELEASE) -> JSONResponse:
    new = version_increment(version, release=release)
    detail = { "type_old": version_class(version), "type_new": version_class(new) }
    resp = { "version": new, "detial": detail }
    return JSONResponse(status_code=200, content=resp)
