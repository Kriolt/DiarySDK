"""Вход в дневник: свои запросы через наш транспорт.

Через общий транспорт идут его таймауты, семафор, перевод ошибок и
постоянный User-Agent. Логин и пароль живут только в теле одного запроса: в
исключения, журнал и запись вызовов они не попадают. Тела ответов входа в
запись тоже не идут — в них одноразовый код и контакты пользователя.

Шаги входа не повторяются (ни POST, ни GET с одноразовым кодом): после
сбоя потребитель начинает вход заново.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

from diarysdk import _jwt as jwt
from diarysdk._hosts import Hosts
from diarysdk._transport import DiaryResponse, FlowCookies, Transport
from diarysdk.errors import BadCredentials, NotFound, TokenInvalid, UpstreamError, UpstreamFormat

TOKEN_COOKIE = "aupd_token"  # noqa: S105 — имя куки, не секрет
# Куку токена берём с последнего ответа цепочки переадресаций callback;
# на каком шаге её ставит портал, живьём не видели.
# Поэтому идём сами, не дальше пяти шагов и только по своим хостам.
MAX_REDIRECTS = 5


async def password_login(transport: Transport, hosts: Hosts, login: str, password: str) -> str:
    """Логин и пароль портала → JWT дневника."""
    try:
        session = await transport.send(
            "POST",
            f"{hosts.dnevnik}/lms/api/sessions",
            headers={"Accept": "application/json"},
            json={"login": login, "password_plain": password},
            call="login.password",
            # По переадресации клиент на 307/308 повторил бы POST с тем же
            # телом на любой хост — логин и пароль уходят ровно один раз.
            follow_redirects=False,
            record_body=False,
        )
    except TokenInvalid:
        raise BadCredentials() from None
    except NotFound:
        raise UpstreamError(upstream_status=404) from None
    if 300 <= session.status < 400:
        raise UpstreamFormat(problems=["sessions: переадресация вместо ответа"])
    code = _authentication_token(session.json())
    url = f"{hosts.dnevnik}/v3/auth/kauth/callback"
    # Куки цепочки переадресаций callback живут в своей банке: общая банка
    # транспорта их не держит, а следующий шаг цепочки может ждать куку предыдущего.
    cookies = FlowCookies()
    try:
        response = await get_step(
            transport, url, params={"code": code}, call="login.callback", cookies=cookies
        )
        return await _token_after_redirects(transport, hosts, url, response, cookies)
    finally:
        cookies.clear()


def _authentication_token(data: Any) -> str:
    if not isinstance(data, dict):
        raise UpstreamFormat(problems=["тело: не объект"])
    code = data.get("authentication_token")
    if isinstance(code, str) and code:
        return code
    # Портал может ответить 200 с описанием ошибки вместо кода: это отказ во
    # входе, а не поменявшийся формат.
    if data.get("error") or data.get("errors"):
        raise BadCredentials()
    raise UpstreamFormat(problems=["authentication_token: нет в ответе"])


async def _token_after_redirects(
    transport: Transport, hosts: Hosts, url: str, response: DiaryResponse, cookies: FlowCookies
) -> str:
    """Первая кука aupd_token: на самом callback или на шагах его переадресации."""
    response = await follow_redirects(
        transport,
        own_origins(hosts),
        url,
        response,
        call="login.redirect",
        cookies=cookies,
        stop=has_token,
    )
    return token_from_cookie(response)


# Общие шаги входа: ими пользуется и вход через ЕСИА (login_esia.py).

_DEFAULT_PORTS = {"https": 443, "http": 80}


def origin(url: str) -> tuple[str, str, int | None]:
    """Схема, хост и порт — с портом по умолчанию, если он не указан явно:
    https://host и https://host:443 — один хост. Адрес с user@ не совпадает
    ни с каким своим."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port or _DEFAULT_PORTS.get(scheme)
    except ValueError:
        port = None
    host = (parts.hostname or "").lower()
    if parts.username is not None or parts.password is not None:
        host = "@" + host
    return scheme, host, port


def own_origins(hosts: Hosts, *extra: str) -> set[tuple[str, str, int | None]]:
    return {origin(host) for host in (hosts.dnevnik, hosts.school_api, hosts.school, *extra)}


def has_token(response: DiaryResponse) -> bool:
    return bool(response.cookies.get(TOKEN_COOKIE))


async def follow_redirects(
    transport: Transport,
    allowed: set[tuple[str, str, int | None]],
    url: str,
    response: DiaryResponse,
    *,
    call: str,
    cookies: FlowCookies | None = None,
    stop: Callable[[DiaryResponse], bool] = lambda _: False,
) -> DiaryResponse:
    """Идём по 3xx сами: не дальше MAX_REDIRECTS шагов и только по allowed.
    stop — остановиться раньше, если ответ уже дал нужное (куку токена)."""
    hops = 0
    while not stop(response) and 300 <= response.status < 400:
        if hops == MAX_REDIRECTS:
            raise UpstreamFormat(problems=[f"{call}: больше {MAX_REDIRECTS} переадресаций"])
        if not response.location:
            raise UpstreamFormat(problems=[f"{call}: переадресация без Location"])
        url = urljoin(url, response.location)
        # Чужой хост не получает от нас ничего: ни запроса, ни имени в ошибке.
        if origin(url) not in allowed:
            raise UpstreamFormat(problems=[f"{call}: переадресация на чужой хост"])
        hops += 1
        response = await get_step(transport, url, call=call, cookies=cookies)
    return response


async def get_step(
    transport: Transport,
    url: str,
    *,
    call: str,
    params: dict[str, str] | None = None,
    cookies: FlowCookies | None = None,
    headers: dict[str, str] | None = None,
) -> DiaryResponse:
    """GET шага входа, где 401/403/404 — сбой портала, а не «нужен новый
    токен» или «нет ученика»: токена у потребителя ещё нет."""
    try:
        return await transport.send(
            "GET",
            url,
            headers={"Accept": "application/json", **(headers or {})},
            params=params,
            call=call,
            follow_redirects=False,
            record_body=False,
            retry=False,
            cookies=cookies,
        )
    except TokenInvalid as error:
        raise UpstreamError(upstream_status=error.status) from None
    except NotFound:
        raise UpstreamError(upstream_status=404) from None


def token_from_cookie(response: DiaryResponse) -> str:
    token = response.cookies.get(TOKEN_COOKIE)
    if not token:
        raise UpstreamFormat(problems=[f"cookie {TOKEN_COOKIE}: нет в ответе"])
    try:
        jwt.expires_at(token)
    except jwt.InvalidToken:
        raise UpstreamFormat(problems=[f"cookie {TOKEN_COOKIE}: не JWT со сроком"]) from None
    return token
