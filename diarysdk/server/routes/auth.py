"""Маршруты /v1/auth: вход и сведения о токене.

Подключаются отдельно от /v1 (app.py): токена у входящего ещё нет, поэтому
общей проверки Bearer здесь нет. Ключ и общий лимит роутер ставит сам.

Вход через ЕСИА — несколько запросов: старт отвечает 200 TokenResponse или 202
LoginStep, дальше потребитель шлёт код или ответ на капчу в поток flow_id.
Счётчик стартов (5 в минуту) тратит только старт: шаги начатого входа его
не тратят (решение R3). И тратит его только старт с годным телом: счётчик
берётся в самом обработчике, после разбора тела, — запрос, отвергнутый по
форме, пароль в ЕСИА не несёт и лимит не съедает.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr, field_validator

from diarysdk.models.auth import LoginStep, TokenInfo, TokenResponse
from diarysdk.server.edge.auth import KeyFirstRoute, require_scope
from diarysdk.server.edge.ratelimit import enforce_login_rate_limit
from diarysdk.server.routes.deps import Consumer, Logins
from diarysdk.server.routes.deps import Token as UserToken

# KeyFirstRoute: ключ проверяется раньше разбора тела — без ключа битый JSON
# даёт 403 bad_api_key, а не 400.
router = APIRouter(tags=["вход"], route_class=KeyFirstRoute)

LOGIN_SCOPE = Depends(require_scope("login"))
# Ответ 202: вход не закончен, нужен следующий шаг.
STEP_RESPONSES: dict[int | str, dict] = {
    202: {"model": LoginStep, "description": "Нужен следующий шаг входа: код или капча"}
}
# Коды SMS и приложений — цифры; ASCII, а не любые Unicode-цифры.
_CODE = re.compile(r"[0-9]{4,8}")


class PasswordLogin(BaseModel):
    # Пароль — SecretStr: в repr и сообщения об ошибках он не попадёт.
    # Ответ 400 называет только поле, без значения (edge/errors.py).
    login: Annotated[str, Field(min_length=1, max_length=256)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=256)]

    @field_validator("login")
    @classmethod
    def _login_not_blank(cls, login: str) -> str:
        # Логин из одних пробелов проходит min_length. Значение не режем (портал
        # сам решает, что с краевыми пробелами), только не пускаем пустое.
        # Пароль не трогаем: пробелы в нём бывают настоящими.
        if not login.strip():
            raise ValueError("логин не может быть пустым")
        return login


class MfaCode(BaseModel):
    code: Annotated[SecretStr, Field(min_length=4, max_length=8, description="4–8 цифр")]

    @field_validator("code")
    @classmethod
    def _digits(cls, code: SecretStr) -> SecretStr:
        if not _CODE.fullmatch(code.get_secret_value()):
            raise ValueError("код — только цифры")
        return code


class CaptchaAnswer(BaseModel):
    answer: Annotated[SecretStr, Field(min_length=1, max_length=256)]


def _reply(result: TokenResponse | LoginStep) -> TokenResponse | JSONResponse:
    if isinstance(result, LoginStep):
        return JSONResponse(status_code=202, content=result.model_dump(mode="json"))
    return result


@router.post(
    "/password",
    summary="Вход по логину и паролю портала «Моя школа» — JWT дневника",
    dependencies=[LOGIN_SCOPE],
)
async def password_login(body: PasswordLogin, logins: Logins, request: Request) -> TokenResponse:
    await enforce_login_rate_limit(request)
    return await logins.password(body.login, body.password.get_secret_value())


@router.post(
    "/esia",
    summary="Вход через Госуслуги (ЕСИА): JWT или следующий шаг (код, капча)",
    response_model=TokenResponse,
    responses=STEP_RESPONSES,
    dependencies=[LOGIN_SCOPE],
)
async def esia_login(
    body: PasswordLogin, logins: Logins, consumer: Consumer, request: Request
) -> TokenResponse | Response:
    await enforce_login_rate_limit(request)
    result = await logins.esia_start(consumer, body.login, body.password.get_secret_value())
    return _reply(result)


@router.post(
    "/esia/{flow_id}/code",
    summary="Код из SMS или приложения для начатого входа через ЕСИА",
    response_model=TokenResponse,
    responses=STEP_RESPONSES,
    dependencies=[LOGIN_SCOPE],
)
async def esia_code(
    flow_id: str, body: MfaCode, logins: Logins, consumer: Consumer
) -> TokenResponse | Response:
    return _reply(await logins.esia_code(consumer, flow_id, body.code.get_secret_value()))


@router.post(
    "/esia/{flow_id}/captcha",
    summary="Ответ на капчу ЕСИА для начатого входа",
    response_model=TokenResponse,
    responses=STEP_RESPONSES,
    dependencies=[LOGIN_SCOPE],
)
async def esia_captcha(
    flow_id: str, body: CaptchaAnswer, logins: Logins, consumer: Consumer
) -> TokenResponse | Response:
    return _reply(await logins.esia_captcha(consumer, flow_id, body.answer.get_secret_value()))


@router.post(
    "/esia/{flow_id}/captcha/renew",
    summary="Новая капча вместо текущей",
    status_code=202,
    dependencies=[LOGIN_SCOPE],
)
async def esia_captcha_renew(flow_id: str, logins: Logins, consumer: Consumer) -> LoginStep:
    return await logins.esia_captcha_renew(consumer, flow_id)


@router.delete(
    "/esia/{flow_id}",
    summary="Отменить начатый вход через ЕСИА (нет потока — тоже 204)",
    status_code=204,
    dependencies=[LOGIN_SCOPE],
)
async def esia_cancel(flow_id: str, logins: Logins, consumer: Consumer) -> Response:
    await logins.esia_cancel(consumer, flow_id)
    return Response(status_code=204)


@router.get("/token", summary="Срок и профиль токена из самого JWT, без похода в дневник")
async def token_info(logins: Logins, token: UserToken) -> TokenInfo:
    return logins.token_info(token)
