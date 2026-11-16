"""Общий клиент httpx к дневнику: таймауты, повтор, семафор, ошибки, запись.

Один клиент на процесс: соединения переиспользуются. Через этот модуль идут
все запросы к дневнику (_api).
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.cookiejar import DefaultCookiePolicy
from http.cookies import CookieError, Morsel, SimpleCookie
from json import dumps as _dumps
from typing import Any

import httpx

from diarysdk import _metrics
from diarysdk.errors import NotFound, TokenInvalid, UpstreamError, UpstreamFormat, UpstreamTimeout

log = logging.getLogger("diarysdk.transport")

# Имя текущего вызова (rating.class, marks…) для журнала, если оно не передано
# в send(call=...).
call_name: ContextVar[str] = ContextVar("diary_call_name", default="unnamed")

# Пока идёт наш запрос, httpx не пишет его в журнал: на INFO он выводит полный
# URL, а в нём одноразовый код входа, ID ученика и GUID. Чужие запросы
# приложения (тот же httpx) фильтр не трогает.
_in_diary_request: ContextVar[bool] = ContextVar("diary_in_request", default=False)


class _HideOwnRequests(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _in_diary_request.get()


logging.getLogger("httpx").addFilter(_HideOwnRequests())

RATING_DISABLED_MARKER = "Рейтинг не доступен"
_RETRY_STATUSES = {502, 503, 504}
# Предел размера ответа: тело читается потоком и обрывается на нём.
MAX_REDIRECTS = 10
_REDIRECTS = {301, 302, 303, 307, 308}
_BODY_HEADERS = {"content-type", "content-length"}
# На другой хост уходят только заголовки без секретов: токены лежат в
# Auth-Token, Profile-Id, Cookie и им подобных.
_PLAIN_HEADERS = {"accept", "accept-language", "accept-encoding", "user-agent"}
DEFAULT_MAX_BODY = 32 * 1024 * 1024


@dataclass(frozen=True)
class DiaryResponse:
    status: int
    content_type: str | None
    body: bytes = field(repr=False)
    charset: str | None = None
    # Куки, которые ставит этот ответ (Set-Cookie без стирающих: пустое
    # значение, Max-Age=0, прошедший Expires). Во входе в них приходит токен,
    # поэтому в repr их нет.
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)
    # Куда переадресует ответ 3xx (Location как есть, может быть относительным).
    location: str | None = field(default=None, repr=False)

    def text(self) -> str:
        return self.body.decode(self.charset or "utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.text())
        except ValueError:
            raise UpstreamFormat(problems=["тело: не JSON"]) from None


class FlowCookies:
    """Куки одного входа через ЕСИА: между его запросами живут сессии esia и
    authedu. Общая сессия транспорта кук не держит (её делят все ученики),
    поэтому у каждого потока входа своя банка. Хранится только в памяти и
    стирается clear(), когда поток закрыт."""

    def __init__(self) -> None:
        self._jar = httpx.Cookies()

    def clear(self) -> None:
        self._jar.clear()

    def __len__(self) -> int:
        return len(self._jar.jar)

    def __repr__(self) -> str:
        # Значения кук — сессии пользователя: в repr только их число.
        return f"FlowCookies({len(self)})"

    def header(self, url: str) -> str | None:
        request = httpx.Request("GET", url)
        self._jar.set_cookie_header(request)
        return request.headers.get("Cookie")

    def remember(self, raw: httpx.Response) -> None:
        self._jar.extract_cookies(raw)


@dataclass(frozen=True)
class Record:
    """Итоговый ответ одного вызова — для записи вызова."""

    call: str
    status: int | None
    elapsed_ms: float
    content_type: str | None
    body: bytes = field(repr=False)
    attempts: int
    error: str | None = None
    # Класс исходной ошибки httpx (например, ConnectError):
    # важно отличить сеть от сертификата. Текст ошибки не пишется.
    cause: str | None = None


class _RedirectRefused(Exception):
    pass


class _BodyTooLarge(Exception):
    pass


def _no_cookies(client: httpx.AsyncClient) -> None:
    """Клиент общий для всех пользователей: куки дневника одного ученика не
    должны уехать в запрос другого, поэтому его банка ничего не принимает."""
    client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))


class Transport:
    def __init__(
        self,
        *,
        user_agent: str,
        connect_timeout: float = 5.0,
        total_timeout: float = 15.0,
        concurrency: int = 8,
        retry_pause: float = 0.5,
        max_body: int = DEFAULT_MAX_BODY,
        recorder: Callable[[Record], None] | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self._total_timeout = total_timeout
        self._timeout = httpx.Timeout(total_timeout, connect=connect_timeout)
        # Не больше 8 одновременных запросов к дневнику на весь сервис: баг
        # потребителя не должен устроить порталу нагрузку и бан нашего IP.
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retry_pause = retry_pause
        self._max_body = max_body
        self._recorder = recorder
        # Чужой клиент (тесты) транспорт не закрывает.
        self._owns_http = http is None
        self._http = http
        if http is not None:
            _no_cookies(http)

    async def start(self) -> None:
        if self._http is None:
            # Проверка TLS не отключается: параметра для этого нет.
            self._http = httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False, verify=True
            )
            _no_cookies(self._http)

    async def close(self) -> None:
        if self._http is not None and self._owns_http:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> Transport:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        json: Any = None,
        call: str | None = None,
        follow_redirects: bool = True,
        record_body: bool = True,
        retry: bool = True,
        cookies: FlowCookies | None = None,
        check_status: bool = True,
    ) -> DiaryResponse:
        """follow_redirects=False — вернуть сам ответ 3xx с его куками (callback
        входа). record_body=False — не отдавать тело в запись вызовов: в ответах
        входа одноразовый код и контакты пользователя. retry=False — не
        повторять и GET: шаги входа одноразовые. cookies — банка потока входа:
        её куки уходят с запросом, куки ответа ложатся в неё (с
        follow_redirects=True — только куки последнего ответа). check_status=False
        — вернуть ответ с любым кодом как есть: ЕСИА объясняет отказ телом."""
        name = call or call_name.get()
        ours = {"user-agent", "accept-encoding"}
        headers = {
            **{key: value for key, value in headers.items() if key.lower() not in ours},
            # Постоянный UA.
            "User-Agent": self.user_agent,
            # Заголовки запросов просят ещё br, а httpx без доп. пакета его не
            # раскодирует.
            "Accept-Encoding": "gzip, deflate",
        }
        if cookies is not None and (cookie_header := cookies.header(url)):
            headers["Cookie"] = cookie_header
        retryable = retry and method.upper() == "GET"
        started = time.perf_counter()
        attempts = 0
        response: DiaryResponse | None = None
        failure: Exception | None = None
        cause: str | None = None
        outcome = "ok"

        while True:
            attempts += 1
            response, failure, cause, outcome = None, None, None, "ok"
            try:
                response = await self._attempt(
                    method, url, headers, params, json, follow_redirects, cookies
                )
            except httpx.ConnectTimeout as error:
                failure, cause, outcome = UpstreamTimeout(), type(error).__name__, "connect_timeout"
            except (TimeoutError, httpx.TimeoutException) as error:
                failure, cause, outcome = UpstreamTimeout(), type(error).__name__, "timeout"
            except _RedirectRefused:
                failure, cause, outcome = UpstreamError(), "RedirectRefused", "redirect_refused"
                retryable = False
            except _BodyTooLarge:
                failure, cause, outcome = UpstreamError(), "BodyTooLarge", "too_large"
                retryable = False
            except httpx.UnsupportedProtocol as error:
                failure, cause = UpstreamError(), type(error).__name__
                outcome = "client_error"
                retryable = False
            except httpx.TransportError as error:
                failure, cause, outcome = UpstreamError(), type(error).__name__, "network"
            except httpx.HTTPError as error:
                failure, cause = UpstreamError(), type(error).__name__
                outcome = "client_error"
                retryable = False

            again = (failure is not None and outcome in ("connect_timeout", "network")) or (
                response is not None and response.status in _RETRY_STATUSES
            )
            if retryable and again and attempts == 1:
                await asyncio.sleep(self._retry_pause)
                continue
            break

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        status = response.status if response is not None else None
        log.info(
            "diary_call",
            extra={
                "call": name,
                "status": status,
                "outcome": outcome,
                "cause": cause,
                "duration_ms": elapsed_ms,
                "attempts": attempts,
            },
        )
        if self._recorder is not None:
            self._recorder(
                Record(
                    call=name,
                    status=status,
                    elapsed_ms=elapsed_ms,
                    content_type=response.content_type if response else None,
                    body=response.body if response and record_body else b"",
                    attempts=attempts,
                    error=type(failure).__name__ if failure else None,
                    cause=cause,
                )
            )
        if response is None:
            raise failure or UpstreamError()
        return check_response(url, response) if check_status else response

    async def _attempt(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        json: Any,
        follow_redirects: bool,
        cookies: FlowCookies | None,
    ) -> DiaryResponse:
        if self._http is None:
            raise RuntimeError("транспорт не запущен: нужен start() или async with")
        _metrics.count_diary_call()
        if json is not None:
            # Тело как раньше (", " и ASCII-экранирование): на проводе ничего не меняется.
            content: bytes | None = _dumps(json).encode()
            headers = {"Content-Type": "application/json", **headers}
        else:
            content = None
        marker = _in_diary_request.set(True)
        try:
            return await self._request(
                method, url, headers, params, content, follow_redirects, cookies
            )
        finally:
            _in_diary_request.reset(marker)

    async def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        content: bytes | None,
        follow_redirects: bool,
        cookies: FlowCookies | None,
    ) -> DiaryResponse:
        """Переадресации ведём сами: httpx на другом хосте убирает только
        Authorization, а наши токены лежат в Auth-Token, Cookie и других
        заголовках."""
        assert self._http is not None  # noqa: S101 — проверено в _attempt
        async with self._semaphore, asyncio.timeout(self._total_timeout):
            for _ in range(MAX_REDIRECTS + 1):
                async with self._http.stream(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    content=content,
                    follow_redirects=False,
                    timeout=self._timeout,
                ) as raw:
                    target = raw.headers.get("Location")
                    if not (follow_redirects and raw.status_code in _REDIRECTS and target):
                        return await self._response(raw, cookies)
                    next_url = str(raw.url.join(target))
                    method, content, headers = _next_hop(
                        method, content, headers, raw.status_code, str(raw.url), next_url
                    )
                    url, params = next_url, None
            raise httpx.TooManyRedirects("слишком много переадресаций", request=raw.request)

    async def _response(self, raw: httpx.Response, cookies: FlowCookies | None) -> DiaryResponse:
        body = await self._read(raw)
        if cookies is not None:
            cookies.remember(raw)
        content_type = raw.headers.get("Content-Type")
        return DiaryResponse(
            status=raw.status_code,
            content_type=content_type.split(";")[0].strip() if content_type else None,
            body=body,
            charset=raw.charset_encoding,
            cookies=_set_cookies(raw),
            location=raw.headers.get("Location"),
        )

    async def _read(self, raw: httpx.Response) -> bytes:
        """Тело потоком: на пределе размера чтение обрывается."""
        declared = raw.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > self._max_body:
            raise _BodyTooLarge
        body = bytearray()
        async for chunk in raw.aiter_bytes():
            body += chunk
            if len(body) > self._max_body:
                raise _BodyTooLarge
        return bytes(body)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = httpx.URL(url)
    default = {"http": 80, "https": 443}.get(parsed.scheme)
    return parsed.scheme, parsed.host, parsed.port or default


def _next_hop(
    method: str,
    content: bytes | None,
    headers: Mapping[str, str],
    status: int,
    url: str,
    next_url: str,
) -> tuple[str, bytes | None, dict[str, str]]:
    """Метод, тело и заголовки следующего шага переадресации."""
    if (status == 303 and method != "HEAD") or (status in (301, 302) and method == "POST"):
        method, content = "GET", None
        headers = {k: v for k, v in headers.items() if k.lower() not in _BODY_HEADERS}
    if _origin(url) != _origin(next_url):
        if method not in ("GET", "HEAD"):
            # Тело записи на чужой хост не отдаём.
            raise _RedirectRefused
        headers = {k: v for k, v in headers.items() if k.lower() in _PLAIN_HEADERS}
    return method, content, dict(headers)


def _set_cookies(raw: httpx.Response) -> dict[str, str]:
    """Куки, которые ставит ответ, без стирающих."""
    result: dict[str, str] = {}
    for header in raw.headers.get_list("Set-Cookie"):
        parsed: SimpleCookie = SimpleCookie()
        try:
            parsed.load(header)
        except CookieError:
            continue
        for name, morsel in parsed.items():
            if _deletes(morsel):
                result.pop(name, None)
            else:
                result[name] = morsel.value
    return result


def _deletes(morsel: Morsel[str]) -> bool:
    """Set-Cookie, который стирает куку, а не ставит её."""
    if not morsel.value:
        return True
    max_age = morsel["max-age"]
    if max_age:
        try:
            return int(max_age) <= 0
        except ValueError:
            return False
    if morsel["expires"]:
        try:
            return parsedate_to_datetime(morsel["expires"]) <= datetime.now(UTC)
        except TypeError, ValueError:
            return False
    return False


class RatingOff(UpstreamError):
    """Рейтинг у школы выключен: не сбой, шлюз превращает его в пустой рейтинг.

    Внутренний класс: наружу не экспортируется, в BY_CODE не входит.
    """


def check_response(url: str, response: DiaryResponse) -> DiaryResponse:
    """Перевод кода ответа в наши исключения; общий для транспорта и его подмены в тестах."""
    # Выключенный рейтинг приходит объектом вместо списка, и модель
    # списка на нём упала бы как на поменявшемся формате.
    if "/ej/rating/" in url and _rating_disabled(response.text()):
        raise RatingOff()
    status = response.status
    if status in (401, 403):
        raise TokenInvalid(status=status)
    if status == 404:
        raise NotFound()
    # Любой код от 400 — ошибка.
    if status >= 400:
        raise UpstreamError(upstream_status=status)
    return response


def _rating_disabled(text: str) -> bool:
    if RATING_DISABLED_MARKER in text:
        return True
    # Кириллица в JSON может прийти экранированной (\u0420...), тогда в
    # сыром тексте маркера не видно: смотрим строки объекта.
    if not text.lstrip().startswith("{"):
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and any(
        isinstance(value, str) and RATING_DISABLED_MARKER in value for value in data.values()
    )
