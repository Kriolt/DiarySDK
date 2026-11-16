"""Подставные части для тестов: транспорт без сети."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter

from diarysdk._hosts import Hosts
from diarysdk._port import Ctx, StudentContext
from diarysdk._transport import DiaryResponse, Record, call_name, check_response

# Ученик из tests/fixtures/profile.json.
GUID = "00000000-0000-4000-8000-000000000001"
STUDENT = StudentContext(
    student_id=9001,
    person_guid=GUID,
    profile_id=7001,
    class_unit_id=4001,
    school_id=3001,
    expires_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    parallel_curriculum_id=1,
)
DIARY_TOKEN = "eyJ.diary.token"
CTX = Ctx(token=DIARY_TOKEN, student=STUDENT)
# Список аватарок, как его отдаёт avatarmanagement (форма — по сайту).
AVATARS = [
    {"id": 8801, "url": f"https://dnevnik.test/avatars/{GUID}?image_id=8801", "default": True}
]
HOSTS = Hosts(
    dnevnik="https://dnevnik.test",
    school_api="https://school-api.test",
    school="https://school.test",
)


@dataclass
class Sent:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    json: Any
    call: str

    def header(self, name: str) -> str | None:
        """Заголовок без учёта регистра: дневник и клиенты пишут их как придётся."""
        lowered = {key.lower(): value for key, value in self.headers.items()}
        return lowered.get(name.lower())


class FakeTransport:
    """Отдаёт заранее заданные ответы по пути URL и записывает, что у него просили.

    Коды ответов переводятся в исключения той же функцией, что и в настоящем
    транспорте.
    """

    def __init__(self, *, user_agent: str = "DiarySDK/test", recorder=None) -> None:
        self.user_agent = user_agent
        self.routes: dict[str, DiaryResponse | Exception] = {}
        self.sent: list[Sent] = []
        self.recorder = recorder

    def add(
        self,
        path: str,
        body: Any,
        *,
        status: int = 200,
        content_type: str | None = "application/json",
        cookies: dict[str, str] | None = None,
        location: str | None = None,
    ) -> None:
        if isinstance(body, bytes):
            raw = body
        elif isinstance(body, str):
            raw = body.encode()
        else:
            raw = json.dumps(body, ensure_ascii=False).encode()
        self.routes[path] = DiaryResponse(
            status=status,
            content_type=content_type,
            body=raw,
            cookies=cookies or {},
            location=location,
        )

    def fail(self, path: str, error: Exception) -> None:
        self.routes[path] = error

    async def send(
        self,
        method,
        url,
        *,
        headers,
        params=None,
        json=None,
        call=None,
        follow_redirects=True,
        record_body=True,
        retry=True,
        cookies=None,
        check_status=True,
    ):
        name = call or call_name.get()
        self.sent.append(Sent(method, url, dict(headers), dict(params or {}), json, name))
        path = urlsplit(url).path
        # Ответ на метод можно задать отдельно: add("PUT /путь", ...).
        key = next((k for k in (f"{method} {path}", path) if k in self.routes), None)
        if key is None:
            raise AssertionError(f"подставной дневник не знает путь {path}")
        response = self.routes[key]
        if self.recorder is not None:
            ok = isinstance(response, DiaryResponse)
            self.recorder(
                Record(
                    call=name,
                    status=response.status if ok else None,
                    elapsed_ms=1.0,
                    content_type=response.content_type if ok else None,
                    body=response.body if ok and record_body else b"",
                    attempts=1,
                    error=None if ok else type(response).__name__,
                )
            )
        if isinstance(response, Exception):
            raise response
        return check_response(url, response) if check_status else response


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def fixture(name: str) -> Any:
    return json.loads(fixture_text(name))


class FakeDiary:
    """Подставной Diary для сервисов и маршрутов.

    Ответы задаются по имени метода: значение возвращается, исключение
    поднимается. student_context по умолчанию — ученик из фикстур.
    """

    def __init__(self, **answers: Any) -> None:
        self.answers = {"student_context": STUDENT, **answers}
        self.calls: list[str] = []
        self.args: dict[str, tuple] = {}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def method(*args):
            self.calls.append(name)
            self.args[name] = args
            if name not in self.answers:
                raise AssertionError(f"подставному дневнику не задан ответ на {name}")
            answer = self.answers[name]
            if isinstance(answer, Exception):
                raise answer
            return answer

        return method


def add_diary_routes(fake: FakeTransport) -> None:
    """Все пути дневника, по которым ходят сервис, — на фикстурах."""
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add("/family/mobile/v1/subject_marks", fixture("subject_marks.json"))
    fake.add("/family/mobile/v1/marks", fixture("marks.json"))
    fake.add("/family/mobile/v1/marks/10001", fixture("mark_info.json"))
    fake.add("/family/mobile/v1/school_info", fixture("school_info.json"))
    fake.add("/family/mobile/v1/homeworks", fixture("homeworks.json"))
    fake.add(f"/api/persondata/v1/persons/{GUID}", fixture("person_data.json"))
    fake.add(f"/portfolio/app/persons/{GUID}/govexams/list/", fixture("govexams.json"))
    fake.add("/api/eventcalendar/v1/api/events", fixture("events.json"))
    fake.add("/family/mobile/v1/lesson_schedule_items/20001", fixture("lesson.json"))
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_class.json"))
    fake.add("/api/ej/rating/v1/rank/subjects", fixture("rating_subjects.json"))
    fake.add("/api/ej/rating/v1/rank/rankShort", fixture("rating_short.json"))
    fake.add(f"/api/avatarmanagement/v1/{GUID}", AVATARS)
    fake.add(f"/avatars/{GUID}", b"\x89PNG-avatar", content_type="image/png")
    fake.add("/api/family/web/v1/final_marks/v2", fixture("final_marks.json"))
    # Отметка ДЗ: дневник отвечает пустым телом.
    fake.add("/family/mobile/v1/homeworks/30001/done", b"")
    # Источники вне контракта — их спрашивают только тесты. Формы живых
    # ответов ещё нет, поэтому тела пустые, но проходят модели ответов.
    fake.add("/family/mobile/v1/profile", fixture("family_profile.json"))
    fake.add("/core/api/profiles", [])
    fake.add("/family/mobile/v1/notifications/search", [])
    fake.add("/family/mobile/v1/programs/parallel_curriculum/1", {})
    fake.add("/family/mobile/v1/periods_schedules", [])
    fake.add(
        "/family/mobile/v1/subject_marks/for_subject", fixture("subject_marks_for_subject.json")
    )
    fake.add("/family/mobile/v1/homeworks/short", {})
    fake.add("/v1/user/childrens", {"entities": []})
    fake.add("/acl/api/users/profile_info", [])
    fake.add("/api/usersettings/v1", fixture("user_settings.json"))
    fake.add("/api/meals/v1/clients", {})
    fake.add("/v3/userinfo", {})
    fake.add("/acl/api/system_messages", [])
    fake.add("/core/api/academic_years", [])
    fake.add("/acl/api/users", [])
    fake.add("/core/api/student_profiles", [])
    fake.add("/v1/roles/allGlobal/", [])
    fake.add("/v1/nsi/organisations", {})


DIARY_BASE = "https://diary.test"


def mock_diary(routes: FakeTransport) -> httpx.AsyncClient:
    """Клиент httpx, отвечающий ответами из FakeTransport: настоящий транспорт без сети."""

    def answer(request: httpx.Request) -> httpx.Response:
        response = routes.routes.get(request.url.path)
        if not isinstance(response, DiaryResponse):
            return httpx.Response(404)
        headers = []
        if response.content_type is not None:
            headers.append(("Content-Type", response.content_type))
        headers += [
            ("Set-Cookie", f"{name}={value}; Path=/") for name, value in response.cookies.items()
        ]
        if response.location is not None:
            headers.append(("Location", response.location))
        return httpx.Response(response.status, content=response.body, headers=headers)

    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


def wire_list(model, text: str) -> list:
    """JSON-список ответа дневника в модели _wire, как их разбирает _api."""
    return TypeAdapter(list[model]).validate_json(text)


def core_diary(gateway, **options):
    """Diary ядра, у которого шлюз подставной: сервер видит настоящие Student и LoginFlow."""
    from diarysdk.client import Diary

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    diary = Diary(http=http, **options)
    diary._gateway = gateway
    return diary
