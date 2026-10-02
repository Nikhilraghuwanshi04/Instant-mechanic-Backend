"""Ek hi jagah decide hota hai ki API error user ko kaise dikhega.

DRF aksar errors KHUD clean JSON banata hai (validation 400, 404, 409...).
Lekin koi ANJAANI exception (bug, DB problem) aaye to DRF use aage chhod
deta hai — Django phir HTML error page (DEBUG mein poora traceback!) dikhata
hai. API consumer ke liye ye bekaar hai, aur security ke liye risky.

Ye handler wahi aakhri gap band karta hai:
- Jo error DRF samajhta hai -> wahi response, jaisa tha waisa (kuch nahi badla).
- Jo nahi samajhta -> traceback SIRF server log mein, aur user ko ek
  generic friendly 500 JSON. Internal details kabhi bahar nahi jaatin.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    # Pehle DRF ka standard handler chalao — known errors (validation,
    # 404, 409, ParseError...) ka clean response wahi banata hai.
    response = exception_handler(exc, context)
    if response is not None:
        return response

    # Yahan sirf unhandled exceptions pahunchti hain. Poora traceback
    # server log mein (debugging ke liye), user ko sirf generic message.
    view = context.get('view') if isinstance(context, dict) else None
    request = context.get('request') if isinstance(context, dict) else None
    logger.exception(
        'Unhandled API exception in %s (%s %s)',
        view or 'unknown view',
        getattr(request, 'method', '?'),
        getattr(request, 'path', '?'),
    )
    return Response(
        {'detail': 'Something went wrong on our side. Please try again.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
