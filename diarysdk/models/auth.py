"""Ответы входа /v1/auth/*: токен после входа, шаг входа через ЕСИА и
сведения о токене."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import Field

from diarysdk.models.common import Schema


class TokenResponse(Schema):
    token: str
    expires_at: datetime
    # Как получен: jwt — принесли готовый, password — логин и пароль портала,
    # esia — Госуслуги.
    method: Literal["jwt", "password", "esia"]


class TokenInfo(Schema):
    """Что видно из самого JWT, без похода в дневник."""

    expires_at: datetime
    # Секунд до истечения на момент ответа.
    expires_in: int
    subject_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class LoginMfa(Schema):
    """ЕСИА ждёт код: из SMS (sms), из приложения-аутентификатора (totp)
    или из мессенджера MAX (max)."""

    kind: Literal["sms", "totp", "max"]
    # Куда ушёл код, как его маскирует ЕСИА: «+7 *** ***-**-12». Для totp нет.
    contact: str | None = Field(default=None, repr=False)
    # Секунд живёт код.
    ttl: int
    attempts_left: int


class LoginCaptcha(Schema):
    """ЕСИА сочла вход подозрительным: картинка с символами или вопрос."""

    kind: Literal["image", "question"]
    # Картинка в base64 и её тип (image/png…) — для kind=image.
    image_base64: str | None = None
    image_type: str | None = None
    # Текст вопроса — для kind=question.
    question: str | None = None


@dataclass(frozen=True)
class Captcha:
    """Капча ЕСИА для потребителя: картинка (`image`, её тип в `image_type`) или вопрос."""

    kind: Literal["image", "question"]
    image: bytes | None = field(default=None, repr=False)
    image_type: str | None = None
    question: str | None = field(default=None, repr=False)


class LoginStep(Schema):
    """Вход через ЕСИА не закончен: ответ 202, дальше — шаг step потока flow_id."""

    flow_id: str
    step: Literal["mfa", "captcha"]
    # Поток живёт 5 минут с последнего шага.
    expires_at: datetime
    mfa: LoginMfa | None = None
    captcha: LoginCaptcha | None = None
