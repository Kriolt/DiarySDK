"""Капча ЕСИА («аномалия» входа): получить картинку или вопрос и разобрать
ответ сервиса капчи.

Сам ответ на капчу отправляет login_esia.py: за ним идёт тот же разбор
action/failed, что и у остальных шагов входа. Здесь — только запросы без
данных пользователя: тип, новая сессия, картинка, текст вопроса.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from diarysdk._hosts import Hosts
from diarysdk._login.password import get_step
from diarysdk._port import CaptchaChallenge, unsupported_step
from diarysdk._transport import DiaryResponse, FlowCookies, Transport
from diarysdk.errors import UpstreamError, UpstreamFormat

# Типы капчи ЕСИА: картинка и вопрос. Буквы кириллические.
CAPTCHA_KINDS: dict[str, Literal["image", "question"]] = {
    "О.ЗД1": "image",
    "О.ЗИ1": "question",
}
DEFAULT_CAPTCHA_TYPE = "esiacaptcha"


@dataclass
class EsiaCaptcha:
    """Что поток помнит о капче между запросами: вид, guid реакции ЕСИА и
    сессия сервиса капчи. Самой картинки и ответа здесь нет."""

    kind: Literal["image", "question"]
    guid: str
    captcha_type: str = DEFAULT_CAPTCHA_TYPE
    session: str | None = field(default=None, repr=False)


def from_reaction(details: Any) -> EsiaCaptcha:
    """reaction_details ответа SOLVE_ANOMALY_REACTION."""
    if not isinstance(details, dict):
        raise UpstreamFormat(problems=["SOLVE_ANOMALY_REACTION: нет reaction_details"])
    kind = details.get("type")
    if kind not in CAPTCHA_KINDS:
        raise unsupported_step(kind, kind_of="капча")
    guid = details.get("guid")
    if not isinstance(guid, str) or not guid:
        raise UpstreamFormat(problems=["SOLVE_ANOMALY_REACTION: нет guid"])
    return EsiaCaptcha(CAPTCHA_KINDS[kind], guid)


async def challenge(
    transport: Transport,
    hosts: Hosts,
    cookies: FlowCookies,
    captcha: EsiaCaptcha,
    *,
    fresh: bool,
) -> CaptchaChallenge:
    """Капча для потребителя. fresh — новая вместо текущей: картинку
    обновляет renew, вопрос спрашиваем снова (renew для вопроса нет)."""
    if captcha.kind == "question":
        return await _question(transport, hosts, cookies, captcha)
    if fresh:
        url, call = f"{hosts.esia}/captcha/api/public/v2/renew", "login.esia.captcha_renew"
    else:
        url, call = f"{hosts.esia}/captcha/api/public/v2/type", "login.esia.captcha_type"
    await _session(transport, cookies, captcha, url, call=call)
    return await _image(transport, hosts, cookies, captcha)


def reject_redirect_or_server_error(response: DiaryResponse) -> None:
    """Общее начало разбора ответа ЕСИА и сервиса капчи: переадресация вместо
    ответа — сбой формата (за ней мы не идём), 5xx — сбой дневника. Остальное
    каждый разбирает по-своему."""
    if 300 <= response.status < 400:
        raise UpstreamFormat(problems=["ЕСИА: переадресация вместо ответа"])
    if response.status >= 500:
        raise UpstreamError(upstream_status=response.status)


def verify_token(response: DiaryResponse) -> str | None:
    """verify_token сервиса капчи на ответ картинке; None — ответ неверный.
    Догадка до живого ответа: на неверный ответ сервис отвечает без verify_token,
    в том числе с кодом 4xx."""
    reject_redirect_or_server_error(response)
    try:
        data = response.json()
    except UpstreamFormat:
        if response.status >= 400:
            return None
        raise
    token = data.get("verify_token") if isinstance(data, dict) else None
    return token if isinstance(token, str) and token else None


async def _session(
    transport: Transport, cookies: FlowCookies, captcha: EsiaCaptcha, url: str, *, call: str
) -> None:
    headers = {"captchasession": captcha.session} if captcha.session else None
    response = await get_step(transport, url, call=call, cookies=cookies, headers=headers)
    data = response.json()
    session = data.get("captchaSession") if isinstance(data, dict) else None
    if not isinstance(session, str) or not session:
        raise UpstreamFormat(problems=[f"{call}: нет captchaSession"])
    kind = data.get("captchaType")
    captcha.session = session
    captcha.captcha_type = kind if isinstance(kind, str) and kind else DEFAULT_CAPTCHA_TYPE


async def _image(
    transport: Transport, hosts: Hosts, cookies: FlowCookies, captcha: EsiaCaptcha
) -> CaptchaChallenge:
    response = await get_step(
        transport,
        f"{hosts.esia}/captcha/api/public/v2/image",
        call="login.esia.captcha_image",
        cookies=cookies,
        headers={"captchasession": captcha.session or "", "Accept": "image/*"},
    )
    content_type = response.content_type or ""
    if not response.body or not content_type.startswith("image/"):
        raise UpstreamFormat(problems=["login.esia.captcha_image: не картинка"])
    return CaptchaChallenge(kind="image", image=response.body, image_type=content_type)


async def _question(
    transport: Transport, hosts: Hosts, cookies: FlowCookies, captcha: EsiaCaptcha
) -> CaptchaChallenge:
    response = await get_step(
        transport,
        f"{hosts.esia}/anomaly-resolver/api/reaction/question",
        params={"guid": captcha.guid},
        call="login.esia.question",
        cookies=cookies,
    )
    data = response.json()
    text = data.get("question_text") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text:
        raise UpstreamFormat(problems=["login.esia.question: нет question_text"])
    return CaptchaChallenge(kind="question", question=text)
