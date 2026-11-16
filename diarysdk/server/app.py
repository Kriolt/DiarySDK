"""Сборка FastAPI-приложения: маршруты, зависимости края, обработчики ошибок."""

import asyncio
from collections.abc import Sequence
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, Depends, FastAPI, Response

from diarysdk import Hosts, __version__
from diarysdk.client import Diary
from diarysdk.server import routes
from diarysdk.server.config import Settings
from diarysdk.server.edge import auth, errors, openapi
from diarysdk.server.edge.access_log import AccessLogMiddleware
from diarysdk.server.edge.ratelimit import RateLimiter, enforce_rate_limit, login_limiter
from diarysdk.server.keys import KeyStore
from diarysdk.server.routes import auth as auth_routes
from diarysdk.server.services.login import LoginService
from diarysdk.server.services.login_flows import LoginFlows, sweep_forever


def _hosts(settings: Settings) -> Hosts:
    return Hosts(
        dnevnik=settings.dnevnik_url.rstrip("/"),
        school_api=settings.school_api_url.rstrip("/"),
        school=settings.school_url.rstrip("/"),
        esia=settings.esia_url.rstrip("/"),
    )


def create_app(
    settings: Settings,
    *,
    diary: Diary | None = None,
    routers: Sequence[APIRouter] | None = None,
) -> FastAPI:
    # Свой Diary закрывается вместе с приложением, переданный — остаётся хозяину.
    owned = diary is None
    if diary is None:
        diary = Diary(hosts=_hosts(settings))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Брошенные входы ЕСИА убираются по времени, а не только по
        # следующему запросу входа: куки живут не дольше TTL + 30 с.
        app.state.login_sweeper = asyncio.create_task(sweep_forever(flows))
        try:
            yield
        finally:
            app.state.login_sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await app.state.login_sweeper
            # Незаконченные входы ЕСИА закрываются вместе с сервисом.
            await app.state.login.close()
            if owned:
                await diary.aclose()

    app = FastAPI(title="DiarySDK", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.keys = KeyStore(settings.keys_file)
    app.state.limiter = RateLimiter(settings.rate_per_second, settings.rate_burst)
    app.state.login_limiter = login_limiter()
    app.state.diary = diary
    flows = LoginFlows()
    app.state.login_flows = flows
    app.state.login = LoginService(diary, flows=flows)
    errors.install(app)
    openapi.install(app)
    app.add_middleware(AccessLogMiddleware)

    @app.get("/healthz", include_in_schema=False)
    async def healthz(response: Response) -> dict[str, str]:
        # По этому заголовку выкатка и внешняя проверка развёртывания проверяют, что встала
        # нужная версия. В дневник не ходим.
        response.headers["X-App-Version"] = settings.version
        return {"status": "ok"}

    # Порядок важен: сначала ключ (кто спрашивает), потом его лимит, потом
    # токен. Маршруты, которым нужен сам токен, объявляют require_token ещё
    # раз — FastAPI считает зависимость один раз за запрос.
    v1 = APIRouter(
        prefix="/v1",
        dependencies=[
            Depends(auth.require_consumer),
            Depends(enforce_rate_limit),
            Depends(auth.require_token),
        ],
    )
    for router in routes.ALL if routers is None else routers:
        v1.include_router(router)
    app.include_router(v1)

    # Вход — вне v1: токена у входящего ещё нет. Ключ и общий лимит те же;
    # разрешение login и счётчик стартов маршруты входа ставят сами.
    login = APIRouter(
        prefix="/v1/auth",
        dependencies=[Depends(auth.require_consumer), Depends(enforce_rate_limit)],
    )
    login.include_router(auth_routes.router)
    app.include_router(login)
    return app
