"""Вход через Госуслуги (ЕСИА): свои шаги через наш транспорт.

Переадресации идём сами и только по своим хостам и ЕСИА, MFA выбираем по
явной таблице, а неожиданный ответ — UpstreamFormat, а не IndexError/AttributeError.
Получение капчи — в esia_captcha.py.

Логин, пароль, код и ответ на капчу живут только в теле (или адресе) одного
запроса и никуда больше не попадают: ни в EsiaState, ни в исключения, ни в
журнал, ни в запись вызовов. Ни один шаг не повторяется.

Живых ответов ЕСИА ещё не видели (форма не подтверждена): формы mfa_details, failed и
ответов капчи — по догадке, отмеченной у каждого места.
"""

import html
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Literal
from urllib.parse import urljoin

from diarysdk._hosts import Hosts
from diarysdk._login import captcha as captchas
from diarysdk._login.captcha import EsiaCaptcha
from diarysdk._login.password import (
    follow_redirects,
    get_step,
    has_token,
    origin,
    own_origins,
    token_from_cookie,
)
from diarysdk._port import CaptchaChallenge, EsiaStep, MfaChallenge, unsupported_step
from diarysdk._transport import DiaryResponse, FlowCookies, Transport
from diarysdk.errors import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    LoginBlocked,
    UpstreamError,
    UpstreamFormat,
)

# GRANT_SCOPE_ACCESS подряд: подтверждаем не больше трёх раз.
MAX_GRANTS = 3

# Пропуски подряд (MAX_QUIZ, CHANGE_PASSWORD): больше трёх — не бывает.
MAX_SKIPS = 3

# Шаг ЕСИА, который можно пропустить → путь пропуска.
_SKIPS = {
    "MAX_QUIZ": "quiz-max/skip",
    "CHANGE_PASSWORD": "change-password/skip",
}
_MAX_HINT = (
    "Войдите на gosuslugi.ru и настройте MAX или Госключ, затем повторите вход; "
    "либо отложите это предложение в личном кабинете"
)
_SKIP_HINT = "Не удалось пропустить предложение Госуслуг; зайдите на gosuslugi.ru и завершите его"

# Тип MFA ЕСИА → (наш kind, путь проверки кода). Шлём только то, что знаем.
# TTP — так, по нашим сведениям, ЕСИА называет код из приложения; TOTP — на
# случай прямого имени.
_MFA_KINDS: dict[str, tuple[Literal["sms", "totp", "max"], str]] = {
    "SMS": ("sms", "otp"),
    "MAX": ("max", "otp-max"),
    "TTP": ("totp", "totp"),
    "TOTP": ("totp", "totp"),
}
# Если ЕСИА не сказала.
DEFAULT_CODE_TTL = 300
DEFAULT_ATTEMPTS = 3

# Признак блокировки в failed. Догадка до живого ответа: у портала mes это
# pswd_method_temp_locked; у ЕСИА — что-то с BLOCK/LOCK. Сравниваем целые
# слова (по границам _ и не-букв), а не подстроку: иначе CLOCK_SKEW стал бы
# блокировкой входа.
_BLOCK_WORDS = frozenset({"BLOCK", "BLOCKED", "LOCK", "LOCKED"})
_WORD = re.compile(r"[A-Z]+")

# meta refresh страницы портала: <meta http-equiv="refresh" content="0;url=...">.
_META_REFRESH = re.compile(r"""content\s*=\s*["']?\s*\d+\s*;\s*url\s*=\s*([^"'>\s]+)""", re.I)

Stage = Literal["password", "code", "captcha"]


@dataclass
class _Mfa:
    path: str
    challenge: MfaChallenge


@dataclass
class EsiaState:
    """Поток входа между запросами потребителя (port.EsiaSession): куки
    esia и authedu и что ЕСИА попросила. Ни логина, ни пароля, ни кода."""

    cookies: FlowCookies = field(default_factory=FlowCookies)
    waiting: Literal["mfa", "captcha"] | None = None
    mfa: _Mfa | None = None
    captcha: EsiaCaptcha | None = None

    def close(self) -> None:
        self.cookies.clear()
        self.waiting = self.mfa = self.captcha = None


async def esia_start(
    transport: Transport, hosts: Hosts, login: str, password: str
) -> tuple[EsiaState, str | EsiaStep]:
    """Логин и пароль Госуслуг → JWT или следующий шаг (код, капча)."""
    state = EsiaState()
    async with _closing_on_failure(state):
        await _open_esia(transport, hosts, state)
        response = await _post(
            transport,
            state,
            f"{hosts.esia}/aas/oauth2/api/login",
            json={"login": login, "password": password},
            call="login.esia.password",
        )
        result = await _handle(transport, hosts, state, _answer(response, refused=True), "password")
    return state, result


async def esia_code(
    transport: Transport, hosts: Hosts, state: EsiaState, code: str
) -> str | EsiaStep:
    async with _closing_on_failure(state):
        if state.mfa is None:
            raise UpstreamFormat(problems=["поток не ждёт код"])
        response = await _post(
            transport,
            state,
            f"{hosts.esia}/aas/oauth2/api/login/{state.mfa.path}/verify",
            params={"code": code},
            call="login.esia.code",
        )
        return await _handle(transport, hosts, state, _answer(response), "code")


async def esia_captcha(
    transport: Transport, hosts: Hosts, state: EsiaState, answer: str
) -> str | EsiaStep:
    async with _closing_on_failure(state):
        captcha = _waiting_captcha(state)
        if captcha.kind == "question":
            response = await _post(
                transport,
                state,
                f"{hosts.esia}/aas/oauth2/api/anomaly/question/answer",
                json={"answer": answer, "guid": captcha.guid},
                call="login.esia.captcha",
            )
            return await _handle(transport, hosts, state, _answer(response), "captcha")

        checked = await _post(
            transport,
            state,
            f"{hosts.esia}/captcha/api/public/v2/verify",
            json={"answer": answer, "captchaType": captcha.captcha_type},
            headers={"captchaSession": captcha.session or ""},
            call="login.esia.captcha",
        )
        verify_token = captchas.verify_token(checked)
        if verify_token is None:
            # Сервис капчи не выдал verify_token — ответ неверный. Догадка до
            # так же он отвечает и 4xx.
            raise BadCaptcha(step=await _fresh_captcha(transport, hosts, state))
        response = await _post(
            transport,
            state,
            f"{hosts.esia}/aas/oauth2/api/anomaly/captcha/verify",
            params={"guid": captcha.guid, "verify_token": verify_token},
            json={"verify_token": verify_token, "guid": captcha.guid},
            call="login.esia.captcha_verify",
        )
        return await _handle(transport, hosts, state, _answer(response), "captcha")


async def esia_captcha_renew(transport: Transport, hosts: Hosts, state: EsiaState) -> EsiaStep:
    async with _closing_on_failure(state):
        return EsiaStep(captcha=await _fresh_captcha(transport, hosts, state))


@asynccontextmanager
async def _closing_on_failure(state: EsiaState) -> AsyncIterator[None]:
    """Любой исход, кроме «неверный код» и «неверная капча», закрывает поток:
    после сбоя потребитель начинает вход заново (спек, «Повтор и запись»)."""
    try:
        yield
    except BadCode, BadCaptcha:
        raise
    except BaseException:
        state.close()
        raise


def _waiting_captcha(state: EsiaState) -> EsiaCaptcha:
    if state.captcha is None:
        raise UpstreamFormat(problems=["поток не ждёт капчу"])
    return state.captcha


async def _open_esia(transport: Transport, hosts: Hosts, state: EsiaState) -> None:
    """Страница входа портала → авторизация ЕСИА → её конфиг: после этого в
    банке потока сессии портала и ЕСИА."""
    allowed = own_origins(hosts, hosts.esia)
    page_url = f"{hosts.dnevnik}/v3/auth/esia/login"
    page = await get_step(transport, page_url, call="login.esia.page", cookies=state.cookies)
    url = urljoin(page_url, _esia_link(page))
    if origin(url) not in allowed:
        raise UpstreamFormat(problems=["login.esia.page: ссылка на чужой хост"])
    response = await get_step(transport, url, call="login.esia.authorize", cookies=state.cookies)
    await follow_redirects(
        transport, allowed, url, response, call="login.esia.authorize", cookies=state.cookies
    )
    url = f"{hosts.esia}/aas/oauth2/config"
    response = await get_step(transport, url, call="login.esia.config", cookies=state.cookies)
    await follow_redirects(
        transport, allowed, url, response, call="login.esia.config", cookies=state.cookies
    )


def _esia_link(page: DiaryResponse) -> str:
    # Библиотека берёт адрес из meta refresh; переадресацию тоже примем.
    if 300 <= page.status < 400 and page.location:
        return page.location
    found = _META_REFRESH.search(page.text())
    if not found:
        raise UpstreamFormat(problems=["login.esia.page: нет ссылки на ЕСИА"])
    return html.unescape(found.group(1))


async def _post(
    transport: Transport,
    state: EsiaState,
    url: str,
    *,
    call: str,
    json: Any = None,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> DiaryResponse:
    # Код ответа не проверяет транспорт: отказ ЕСИА объясняет телом (failed),
    # его и читаем. Переадресацию POST не проходим: тело ушло бы чужому хосту.
    return await transport.send(
        "POST",
        url,
        headers={"Accept": "application/json", **(headers or {})},
        params=params,
        json=json,
        call=call,
        follow_redirects=False,
        record_body=False,
        retry=False,
        cookies=state.cookies,
        check_status=False,
    )


def _answer(response: DiaryResponse, *, refused: bool = False) -> dict[str, Any]:
    """Тело шага ЕСИА с action или failed. refused — 401/403 без такого тела
    значит неверный логин или пароль (как у портала, задача 5)."""
    status = response.status
    captchas.reject_redirect_or_server_error(response)
    try:
        data = response.json()
    except UpstreamFormat:
        data = None
    if isinstance(data, dict) and (status < 400 or "action" in data or "failed" in data):
        return data
    if status >= 400:
        if refused and status in (401, 403):
            raise BadCredentials()
        raise UpstreamError(upstream_status=status)
    raise UpstreamFormat(
        problems=["ЕСИА: тело не объект" if data is not None else "ЕСИА: тело не JSON"]
    )


async def _handle(
    transport: Transport, hosts: Hosts, state: EsiaState, data: dict[str, Any], stage: Stage
) -> str | EsiaStep:
    """failed важнее action."""
    grants = skips = 0
    while True:
        if failed := data.get("failed"):
            _failed(state, data, failed, stage)
            # Неверный ответ на капчу: новая капча и BadCaptcha с ней.
            raise BadCaptcha(step=await _fresh_captcha(transport, hosts, state))
        action = data.get("action")
        if action in _SKIPS:
            if action == "MAX_QUIZ" and _not_skippable(data):
                raise unsupported_step(action, hint=_MAX_HINT)
            if skips == MAX_SKIPS:
                # Не сбой формата: потребителю есть что сделать, как и при
                # отказе пропустить — тот же текст подсказки.
                raise unsupported_step(
                    action, hint=_MAX_HINT if action == "MAX_QUIZ" else _SKIP_HINT
                )
            skips += 1
            data = await _skip(transport, hosts, state, action)
            continue
        if action != "GRANT_SCOPE_ACCESS":
            break
        if grants == MAX_GRANTS:
            raise UpstreamFormat(problems=[f"ЕСИА: больше {MAX_GRANTS} GRANT_SCOPE_ACCESS подряд"])
        grants += 1
        response = await _post(
            transport, state, f"{hosts.esia}/aas/oauth2/api/scope/allow", call="login.esia.scope"
        )
        data = _answer(response)
    match action:
        case "DONE":
            return await _done(transport, hosts, state, data)
        case "ENTER_MFA":
            return _enter_mfa(state, data)
        case "SOLVE_ANOMALY_REACTION":
            return EsiaStep(captcha=await _new_captcha(transport, hosts, state, data))
        case None:
            raise UpstreamFormat(problems=["ЕСИА: нет action"])
        case other:
            raise unsupported_step(other)


def _not_skippable(data: dict[str, Any]) -> bool:
    details = data.get("max_details")
    # Поля skippable в живом ответе нет: пропускаем, пока ЕСИА не сказала False.
    return isinstance(details, dict) and details.get("skippable") is False


async def _skip(
    transport: Transport, hosts: Hosts, state: EsiaState, action: str
) -> dict[str, Any]:
    """Пропуск предложения (MAX_QUIZ, CHANGE_PASSWORD): один POST {} без повтора.
    Отказ или не-JSON — шаг для нас неподдерживаемый, поток закроется."""
    response = await _post(
        transport,
        state,
        f"{hosts.esia}/aas/oauth2/api/login/{_SKIPS[action]}",
        json={},
        call=f"login.esia.skip.{action.lower()}",
    )
    hint = _MAX_HINT if action == "MAX_QUIZ" else _SKIP_HINT
    if response.status >= 500:
        # Сбой ЕСИА — не отказ пропустить: подсказка про MAX тут ввела бы в заблуждение.
        raise UpstreamError(upstream_status=response.status)
    if not 200 <= response.status < 300:
        raise unsupported_step(action, hint=hint)
    try:
        data = _answer(response)
    except UpstreamFormat:
        raise unsupported_step(action, hint=hint) from None
    # failed — отказ на шаге пропуска, а не неверный пароль, код или капча.
    if data.get("failed"):
        raise unsupported_step(action, hint=hint)
    return data


def _failed(state: EsiaState, data: dict[str, Any], failed: Any, stage: Stage) -> None:
    """Отказ ЕСИА на шаге stage. Возвращается только для капчи: за новой
    капчей нужен ещё запрос."""
    if isinstance(failed, str) and _BLOCK_WORDS.intersection(_WORD.findall(failed.upper())):
        raise LoginBlocked()
    if stage == "password":
        raise BadCredentials()
    if stage == "captcha":
        return
    if state.mfa is None:
        raise UpstreamFormat(problems=["поток не ждёт код"])
    mfa = state.mfa.challenge
    # Сколько попыток осталось, скажет ЕСИА; не сказала — считаем сами.
    left = _attempts_left(data.get("mfa_details"), mfa.attempts_left - 1)
    if left <= 0:
        raise LoginBlocked()
    state.mfa.challenge = replace(mfa, attempts_left=left)
    raise BadCode(step=state.mfa.challenge)


async def _done(transport: Transport, hosts: Hosts, state: EsiaState, data: dict[str, Any]) -> str:
    """DONE: redirect_url ведёт на callback портала, токен — в куке aupd_token
    на нём или на шагах его переадресации."""
    redirect = data.get("redirect_url")
    if not isinstance(redirect, str) or not redirect:
        raise UpstreamFormat(problems=["DONE: нет redirect_url"])
    allowed = own_origins(hosts, hosts.esia)
    url = urljoin(f"{hosts.esia}/", redirect)
    if origin(url) not in allowed:
        raise UpstreamFormat(problems=["DONE: redirect_url на чужой хост"])
    response = await get_step(transport, url, call="login.esia.done", cookies=state.cookies)
    response = await follow_redirects(
        transport,
        allowed,
        url,
        response,
        call="login.esia.redirect",
        cookies=state.cookies,
        stop=has_token,
    )
    token = token_from_cookie(response)
    state.close()
    return token


def _enter_mfa(state: EsiaState, data: dict[str, Any]) -> EsiaStep:
    details = data.get("mfa_details")
    if not isinstance(details, dict):
        raise UpstreamFormat(problems=["ENTER_MFA: нет mfa_details"])
    kind = details.get("type")
    if kind not in _MFA_KINDS:
        raise unsupported_step(kind, kind_of="MFA")
    ours, path = _MFA_KINDS[kind]
    inner = _inner_details(details)
    contact = inner.get("phone")
    challenge = MfaChallenge(
        kind=ours,
        contact=contact if isinstance(contact, str) and 0 < len(contact) <= 64 else None,
        ttl=_positive(inner.get("verify_timeout_secs"), DEFAULT_CODE_TTL),
        attempts_left=_attempts_left(details, DEFAULT_ATTEMPTS),
    )
    state.mfa, state.captcha, state.waiting = _Mfa(path, challenge), None, "mfa"
    return EsiaStep(mfa=challenge)


def _inner_details(details: dict[str, Any]) -> dict[str, Any]:
    # Живой вход 16.11: подробности — в otp_details рядом с type.
    return next(
        (v for k, v in details.items() if k.endswith("_details") and isinstance(v, dict)), {}
    )


def _attempts_left(details: Any, default: int) -> int:
    if not isinstance(details, dict):
        return default
    inner = _inner_details(details)
    value = inner.get("verify_attempts_left")
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default
    )


def _positive(value: Any, default: int) -> int:
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default
    )


async def _new_captcha(
    transport: Transport, hosts: Hosts, state: EsiaState, data: dict[str, Any]
) -> CaptchaChallenge:
    captcha = captchas.from_reaction(data.get("reaction_details"))
    state.captcha, state.mfa, state.waiting = captcha, None, "captcha"
    return await captchas.challenge(transport, hosts, state.cookies, captcha, fresh=False)


async def _fresh_captcha(transport: Transport, hosts: Hosts, state: EsiaState) -> CaptchaChallenge:
    captcha = _waiting_captcha(state)
    return await captchas.challenge(transport, hosts, state.cookies, captcha, fresh=True)
