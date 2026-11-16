"""Сценарии входа поверх `Diary` ядра и сведения о токене.

Логин, пароль, код и ответ на капчу проходят здесь насквозь: сервис их не
хранит и не пишет. Между шагами входа через ЕСИА держится только `LoginFlow`
ядра в реестре (services/login_flows.py); срок шага и проверки входа — в ядре.
"""

import asyncio
import base64
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from diarysdk.client import Diary, LoginFlow
from diarysdk.errors import BadCaptcha, BadCode, BadRequest, FlowExpired, UpstreamFormat
from diarysdk.models.auth import LoginCaptcha, LoginStep, TokenInfo, TokenResponse
from diarysdk.server.services.login_flows import Flow, LoginFlows
from diarysdk.token import Token

# Сколько второй запрос по одному потоку ждёт первого, секунд.
LOCK_WAIT = 20.0


def _now() -> datetime:
    return datetime.now(UTC)


class LoginService:
    def __init__(
        self,
        diary: Diary,
        *,
        flows: LoginFlows | None = None,
        lock_wait: float = LOCK_WAIT,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self._diary = diary
        self._flows = flows if flows is not None else LoginFlows()
        self._lock_wait = lock_wait
        self._now = now

    async def password(self, login: str, password: str) -> TokenResponse:
        return _token_response(await self._diary.login.password(login, password))

    async def esia_start(
        self, consumer: str, login: str, password: str
    ) -> TokenResponse | LoginStep:
        # Место — до похода в ЕСИА: сверх лимита пароль никуда не уходит.
        flow = await self._flows.reserve(consumer)
        try:
            result = await self._diary.login.esia(login, password)
        except BaseException:
            await self._flows.drop(flow)
            raise
        if isinstance(result, Token):
            await self._flows.drop(flow)
            return _token_response(result)
        await self._flows.activate(flow, result)
        return _login_step(flow.flow_id, result)

    async def esia_code(self, consumer: str, flow_id: str, code: str) -> TokenResponse | LoginStep:
        return await self._esia_step(consumer, flow_id, lambda login: login.submit_code(code))

    async def esia_captcha(
        self, consumer: str, flow_id: str, answer: str
    ) -> TokenResponse | LoginStep:
        return await self._esia_step(consumer, flow_id, lambda login: login.answer_captcha(answer))

    async def esia_captcha_renew(self, consumer: str, flow_id: str) -> LoginStep:
        result = await self._esia_step(consumer, flow_id, lambda login: login.renew_captcha())
        if not isinstance(result, LoginStep):
            raise TypeError("обновление капчи не даёт токена")
        return result

    async def esia_cancel(self, consumer: str, flow_id: str) -> None:
        """Отмена входа. Нет потока (или он чужой) — тоже успех: отменять нечего."""
        try:
            flow = await self._flows.find(consumer, flow_id)
        except FlowExpired:
            return
        # За идущим шагом ждёт не дольше lock_wait. Не дождалась — всё равно успех:
        # шаг сам закроет поток (при ошибке или успехе), иначе уберёт уборщик.
        try:
            async with self._locked(flow):
                await self._flows.drop(flow)
        except FlowExpired:
            return

    async def close(self) -> None:
        """Остановка сервиса: все незаконченные входы закрываются."""
        await self._flows.close_all()

    async def _esia_step(
        self,
        consumer: str,
        flow_id: str,
        step: Callable[[LoginFlow], Awaitable[Token | LoginFlow]],
    ) -> TokenResponse | LoginStep:
        flow = await self._flows.find(consumer, flow_id)
        # Шаги одного потока — по очереди: второй ждёт первого и смотрит, что
        # от потока осталось. Ждёт не дольше lock_wait: иначе вместе со своим
        # шагом он держал бы потребителя до ~40 с.
        async with self._locked(flow):
            if not self._flows.is_open(flow) or flow.login is None:
                raise FlowExpired()
            login = flow.login
            try:
                result = await step(login)
            except BadCode:
                # Вход жив: в теле ответа — тот же шаг, что и при старте.
                raise BadCode(step=_login_step(flow.flow_id, login)) from None
            except BadCaptcha:
                raise BadCaptcha(step=_login_step(flow.flow_id, login)) from None
            except BadRequest:
                # Вход ждёт другой шаг: он не тронут, потребитель может поправиться.
                raise
            except BaseException:
                # Ядро закрыло вход; здесь — забыть запись.
                await self._flows.drop(flow)
                raise
            if isinstance(result, Token):
                await self._flows.drop(flow)
                return _token_response(result)
            return _login_step(flow.flow_id, result)

    @asynccontextmanager
    async def _locked(self, flow: Flow) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(self._lock_wait):
                await flow.lock.acquire()
        except TimeoutError:
            # Первый шаг ещё идёт: этого запроса дождаться не вышло, но поток
            # не трогаем — первый шаг закончит его сам.
            raise FlowExpired() from None
        try:
            yield
        finally:
            flow.lock.release()

    def token_info(self, token: str) -> TokenInfo:
        """Срок и профиль из самого JWT. Подпись не проверяем — её проверит
        дневник при первом чтении."""
        parsed = Token(token)
        left = parsed.expires_in(self._now())
        if parsed.expires_at is None or left is None:
            raise UpstreamFormat(problems=["токен: нет срока"])
        return TokenInfo(
            expires_at=parsed.expires_at,
            # Просроченный токен сюда не доходит: require_token отвечает 401
            # token_expired раньше, поэтому expires_in не бывает отрицательным.
            expires_in=math.floor(left.total_seconds()),
            subject_id=parsed.subject_id,
            roles=parsed.roles,
        )


def _token_response(token: Token) -> TokenResponse:
    if token.expires_at is None:
        raise UpstreamFormat(problems=["токен: нет срока"])
    return TokenResponse(token=token.value, expires_at=token.expires_at, method=token.method)


def _login_step(flow_id: str, login: LoginFlow) -> LoginStep:
    captcha = login.captcha
    return LoginStep(
        flow_id=flow_id,
        step=login.kind,
        expires_at=login.expires_at,
        mfa=login.mfa,
        captcha=(
            LoginCaptcha(
                kind=captcha.kind,
                image_base64=base64.b64encode(captcha.image).decode() if captcha.image else None,
                image_type=captcha.image_type,
                question=captcha.question,
            )
            if captcha
            else None
        ),
    )
