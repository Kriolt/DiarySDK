"""Вход через сервис: `RemoteLogin` и `RemoteLoginFlow`.

Те же имена и поведение, что у `Login` и `LoginFlow` ядра. Запросы описаны в
`_core`; здесь только превращение ответов в `Token` и состояние потока. Шаги
входа клиент не повторяет никогда, а сбой 502/504 или сети на шаге — это
`UpstreamError` или `NetworkError`, не `WriteUncertain`: поток закрыт, вход
нужно начать заново. Секретов (пароль, код, ответ на капчу) поток не хранит.
"""

from __future__ import annotations

import base64
import contextlib
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from diarysdk import _protocols as protocols
from diarysdk.errors import BadCaptcha, BadCode, DiaryError, UpstreamFormat
from diarysdk.models.auth import Captcha, LoginMfa, LoginStep
from diarysdk.models.auth import TokenResponse as TokenModel
from diarysdk.remote import _core
from diarysdk.token import Token

if TYPE_CHECKING:
    from diarysdk.remote.client import RemoteDiary


def _captcha(step: LoginStep) -> Captcha | None:
    raw = step.captcha
    if raw is None:
        return None
    image = None
    if raw.image_base64 is not None:
        try:
            image = base64.b64decode(raw.image_base64, validate=True)
        except ValueError:  # binascii.Error — его подкласс; не-ASCII даёт ValueError
            raise UpstreamFormat("Картинка капчи не в base64, обновите diarysdk") from None
    return Captcha(raw.kind, image, raw.image_type, raw.question)


def _token(model: TokenModel) -> Token:
    return Token(model.token, model.expires_at, model.method)


@protocols.documented(protocols.LoginFlowLike)
class RemoteLoginFlow:
    """Вход через ЕСИА не закончен. Один объект живёт весь вход: после неверного
    ответа его `.mfa` и `.captcha` обновляются, и повторить можно на нём же."""

    def __init__(self, diary: RemoteDiary, step: LoginStep) -> None:
        self._diary = diary
        self._flow_id = step.flow_id
        self.kind: Literal["mfa", "captcha"] = step.step
        self.mfa: LoginMfa | None = step.mfa
        self.captcha: Captcha | None = _captcha(step)
        self.expires_at: datetime = step.expires_at

    def __repr__(self) -> str:
        return f"RemoteLoginFlow(kind={self.kind!r}, expires_at={self.expires_at.isoformat()})"

    def _apply(self, step: LoginStep) -> None:
        # Сначала разбор (может упасть), потом присваивание: поток не остаётся наполовину новым.
        captcha = _captcha(step)
        self._flow_id = step.flow_id
        self.kind = step.step
        self.mfa = step.mfa
        self.captcha = captcha
        self.expires_at = step.expires_at

    async def _step(self, spec: _core.Request) -> Token | RemoteLoginFlow:
        try:
            result = await self._diary._send(spec)
        except (BadCode, BadCaptcha) as error:
            self._retry(error)
            raise
        if isinstance(result, LoginStep):
            try:
                self._apply(result)
            except UpstreamFormat:
                await self._cancel_quietly()
                raise
            return self
        return _token(result)

    def _retry(self, error: BadCode | BadCaptcha) -> None:
        """Неверный ответ: вход жив, новый шаг — в самом потоке и в ошибке."""
        step = error.step
        if isinstance(step, LoginStep):
            # Шаг с битой капчей не должен маскировать BadCode/BadCaptcha: ошибка важнее.
            with contextlib.suppress(UpstreamFormat):
                self._apply(step)
                error.step = self.mfa if isinstance(error, BadCode) else self.captcha
        error.flow = self

    async def _cancel_quietly(self) -> None:
        # Шаг не разобрали, а серверный поток ждёт до TTL: закрываем его. Сбой
        # самой отмены не подменяет исходную ошибку.
        with contextlib.suppress(DiaryError):
            await self._diary._send(_core.esia_cancel(self._flow_id))

    async def submit_code(self, code: str) -> Token | RemoteLoginFlow:
        return await self._step(_core.esia_code(self._flow_id, code))

    async def answer_captcha(self, answer: str) -> Token | RemoteLoginFlow:
        return await self._step(_core.esia_captcha(self._flow_id, answer))

    async def renew_captcha(self) -> RemoteLoginFlow:
        result = await self._step(_core.esia_renew(self._flow_id))
        if not isinstance(result, RemoteLoginFlow):
            raise TypeError("обновление капчи не даёт токена")
        return result

    async def close(self) -> None:
        await self._diary._send(_core.esia_cancel(self._flow_id))


@protocols.documented(protocols.LoginLike)
class RemoteLogin:
    """Вход: `diary.login`. Нужен ключ потребителя с разрешением login."""

    def __init__(self, diary: RemoteDiary) -> None:
        self._diary = diary

    def __repr__(self) -> str:
        return "RemoteLogin()"

    async def password(self, login: str, password: str) -> Token:
        return _token(await self._diary._send(_core.password_login(login, password)))

    async def esia(self, login: str, password: str) -> Token | RemoteLoginFlow:
        result = await self._diary._send(_core.esia_login(login, password))
        if not isinstance(result, LoginStep):
            return _token(result)
        try:
            return RemoteLoginFlow(self._diary, result)
        except UpstreamFormat:
            with contextlib.suppress(DiaryError):
                await self._diary._send(_core.esia_cancel(result.flow_id))
            raise
