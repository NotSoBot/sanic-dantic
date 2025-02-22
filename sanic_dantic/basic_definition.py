# !/usr/bin/env python
# -*- coding:utf-8 -*-
"""
FileName: basic_definition.py
Description:
Author: Connor Zhang
CreateTime:  2023-01-23
"""

import json

from copy import deepcopy
from inspect import getmro
from typing import Any, Callable, Type, Union


from pydantic import BaseModel, ValidationError
from sanic.exceptions import InvalidUsage, ServerError
from sanic.log import error_logger
from sanic.request import Request


class ParsedArgsObj(dict):
    """
    ParsedArgsObj inherits from dict and is used to store parsed parameters.
    When using, you can directly use the attribute to access the parameter.

    ParsedArgsObj 继承自 dict，用于存储解析后的参数。
    在使用时，可以直接使用属性访问参数。
    """

    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key, value):
        self.update({key: value})

    def __deepcopy__(self, memo=None):
        return ParsedArgsObj(deepcopy(dict(self), memo=memo))


class DanticModelObj:
    """
    Used to parse and judge the parameters of pydantic model,
    convenient for DanticView and parse_params to use.

    用于解析和判断 pydantic 模型的参数， 方便 DanticView 和 parse_params 使用。
    """

    def __init__(
            self,
            header: Type[BaseModel] = None,
            query: Type[BaseModel] = None,
            path: Type[BaseModel] = None,
            body: Type[BaseModel] = None,
            form: Type[BaseModel] = None,
            all: Type[BaseModel] = None,
            error: Union[Callable[[ValidationError], None], bool] = None,
    ) -> None:
        """
        :param header: pydantic model for header
        :param query: pydantic model for query
        :param path: pydantic model for path
        :param body: pydantic model for body
        :param form: pydantic model for form
        :param all: pydantic model for all
        :param error: error handler function

        When there are the same parameter name in the model,
        """

        try:

            self.header = header
            self.query = query
            self.path = path
            self.body = body
            self.form = form
            self.all = all
            self.error = error

            if body and form:
                raise AssertionError(
                    "sanic-dantic: " +
                    "body and form cannot be used at the same time."
                )

            for model in [header, path, query, form, body, all]:
                if model and BaseModel not in getmro(model):
                    raise AssertionError(
                        "sanic-dantic: " +
                        "model must inherited from Pydantic.BaseModel"
                    )

            if error and error is not True and not isinstance(error, Callable):
                raise AssertionError(
                    "sanic-dantic: " +
                    "the error handler must be a callable function or True"
                )

        except AssertionError as e:
            error_logger.error(e)
            raise ServerError(str(e))


def validate(request: Request, dmo: DanticModelObj) -> Any:
    """
    When there are the same parameter name in the model,
    the same parameter will be overwritten,
    to overwrite order is: body = form > query > path > header

    当不同的 model 中存在相同的参数名时，同名的参数会被覆盖，
    覆盖顺序为：body = form > query > path > header
    :param request: sanic request
    :param dmo: DanticModelObj
    :return: ParsedArgsObj
    """

    try:
        parsed_args = ParsedArgsObj()

        if dmo.header:
            parsed_args.update(dmo.header(**request.headers).dict())

        if dmo.path:
            parsed_args.update(dmo.path(**request.match_info).dict())

        if dmo.query:
            params = {
                key: val[0] if len(val) == 1 else val
                for key, val in request.args.items()
            }
            parsed_args.update(dmo.query(**params).dict())

        if dmo.form:
            form_data = {
                key: val[0] if len(val) == 1 else val
                for key, val in request.form.items()
            }
            if 'payload_json' in form_data:
                payload_json = form_data.pop('payload_json')
                try:
                    payload_json = json.loads(payload_json)
                except:
                    pass

                if isinstance(payload_json, dict):
                    parsed_args.update(dmo.form(**payload_json).dict())

            parsed_args.update(dmo.form(**form_data).dict())

        elif dmo.body:
            parsed_args.update(dmo.body(**request.json).dict())


        if dmo.all:
            query_params = {
                key: val[0] if len(val) == 1 else val
                for key, val in request.args.items()
            }
            body_params = {}
            try:
                body_params = request.json
                if not isinstance(body_params, dict):
                    body_params = {}
            except:
                body_params = {
                    key: val[0] if len(val) == 1 else val
                    for key, val in request.form.items()
                }

                if 'payload_json' in body_params:
                    payload_json = body_params.pop('payload_json')
                    try:
                        payload_json = json.loads(payload_json)
                    except:
                        pass

                    if isinstance(payload_json, dict):
                        body_params.update(**payload_json)

            params = {}
            params.update(request.headers)
            params.update(request.match_info)
            params.update(query_params)
            params.update(body_params)

            parsed_args.update(dmo.all(**params).dict())

    except ValidationError as e:
        if dmo.error == True:
            raise e

        # if dmo has error handler, use it, else use InvalidUsage error
        # 如果 dmo 有 error handler，使用它，否则使用 InvalidUsage 错误
        error_msg = e.errors()[0]
        message = f'{error_msg.get("loc")[0]} {error_msg.get("msg")}'
        if dmo.error:
            return dmo.error(request, e)
        else:
            error_msg = e.errors()[0]
            message = f'{error_msg.get("loc")[0]} {error_msg.get("msg")}'

            error_logger.error(message)
            raise InvalidUsage(message)
    except Exception as e:
        raise ServerError(str(e))
    request.ctx.params = parsed_args
    return parsed_args
