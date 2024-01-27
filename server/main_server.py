from django.http import HttpResponse
import json


class XerenityError(Exception):

    def __init__(self, message, code):
        self.message = message
        self.code = code


def responseHttpError(message, code=400):
    return HttpResponse(json.dumps({"message": message}), content_type="application/json", status=code)


def responseHttpOk(body: dict, code=200):
    return HttpResponse(json.dumps(body), content_type="application/json", status=code)


class XerenityFunctionServer:

    def LoadRequest(self, body):
        pass
