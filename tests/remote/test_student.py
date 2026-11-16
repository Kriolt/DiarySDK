from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from diarysdk import (
    Avatar,
    Token,
    TokenExpired,
    TokenInvalid,
)
from diarysdk.models.common import ClassUnit, SchoolBrief, Subject
from diarysdk.models.curriculum import Curriculum
from diarysdk.models.curriculum import Curriculum as ClientCurriculum
from diarysdk.models.homework import Homework
from diarysdk.models.identity import Identity, IdentityPerson
from diarysdk.models.identity import Identity as ClientIdentity
from diarysdk.models.lessons import Lesson
from diarysdk.models.lessons import Lesson as ClientLesson
from diarysdk.models.marks import Mark, MarkDetail
from diarysdk.models.marks import MarkDetail as ClientMarkDetail
from diarysdk.models.me import Me as ClientMe
from diarysdk.models.rating import Rating
from diarysdk.models.rating import Rating as ClientRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School
from diarysdk.models.school import School as ClientSchool
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.settings import Settings as ClientSettings
from diarysdk.models.subjects import SubjectDetail
from diarysdk.models.subjects import SubjectDetail as ClientSubjectDetail
from diarysdk.server.app import create_app
from tests.conftest import API_KEY
from tests.fakes import core_diary
from tests.remote.helpers import remote_diary
from tests.test_routes_me import sample_me
from tests.tokens import make_token, valid_token

D = date(2026, 10, 1)
E = date(2026, 10, 5)


def answers():
    return {
        "me": sample_me(),
        "avatar": Avatar(content=b"\x89PNG", content_type="image/png"),
        "school": School(),
        "marks": [Mark(id=11, date=D, subject=Subject(id=101, name="Алгебра"), value="9")],
        "final_marks": [],
        "subjects": [],
        "rating": Rating.disabled(),
        "rating_subjects": [],
        "rating_history": [],
        "schedule": [
            ScheduleItem(id=21, date=D, subject=Subject(id=101, name="Алгебра"), room="204")
        ],
        "lesson": Lesson(id=7),
        "homework": [Homework(id=31, due=E, text="№ 5", is_done=False)],
        "set_homework_done": None,
        "exams": [],
        "notifications": [],
        "periods": [],
        "mark": MarkDetail(id=7),
        "subject": SubjectDetail(subject_id=101),
        "curriculum": Curriculum(),
        "settings": Settings(),
        "update_settings": None,
        "identity": Identity(
            person=IdentityPerson(last_name="Тестов"), school=SchoolBrief(), class_=ClassUnit()
        ),
    }


# (метод клиента, аргументы, метод дневника, ожидаемый тип результата)
CASES = [
    ("me", (), "me", ClientMe),
    ("avatar", (), "avatar", Avatar),
    ("school", (), "school", ClientSchool),
    ("marks", (D, E), "marks", list),
    ("final_marks", (2025,), "final_marks", list),
    ("subjects", (), "subjects", list),
    ("rating", (D, 12), "rating", ClientRating),
    ("rating_subjects", (D,), "rating_subjects", list),
    ("rating_history", (D, E), "rating_history", list),
    ("schedule", (D, E), "schedule", list),
    ("lesson", (7,), "lesson", ClientLesson),
    ("homework", (D, E), "homework", list),
    ("homework_done", (555,), "set_homework_done", type(None)),
    ("homework_undone", (555,), "set_homework_done", type(None)),
    ("exams", (), "exams", list),
    ("notifications", (), "notifications", list),
    ("periods", (D, E), "periods", list),
    ("curriculum", (), "curriculum", ClientCurriculum),
    ("settings", (), "settings", ClientSettings),
    ("update_settings", (SettingsUpdate(goal=True),), "update_settings", type(None)),
    ("mark", (7,), "mark", ClientMarkDetail),
    ("subject", (101,), "subject", ClientSubjectDetail),
    ("identity", (), "identity", ClientIdentity),
]


@pytest.fixture
def app(settings, fake_diary, today):
    fake_diary.answers.update(answers())
    return create_app(settings, diary=core_diary(fake_diary))


@pytest.mark.parametrize(("name", "args", "diary_method", "kind"), CASES)
async def test_method_returns_model(app, fake_diary, name, args, diary_method, kind):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        result = await getattr(api.student(valid_token()), name)(*args)
    assert isinstance(result, kind)
    assert diary_method in fake_diary.calls


async def test_params_reach_the_service(app, fake_diary):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        student = api.student(valid_token())
        await student.marks(D, E)
        assert fake_diary.args["marks"][1:] == (D, E)
        await student.rating(D, 12)
        assert fake_diary.args["rating"][1:] == (D, 12)
        await student.final_marks(2025)
        assert fake_diary.args["final_marks"][1:] == (2025,)
        await student.homework_undone(555)
        assert fake_diary.args["set_homework_done"][1:] == (555, False)


async def test_avatar_keeps_bytes_and_content_type(app):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        avatar = await api.student(valid_token()).avatar()
    assert avatar == Avatar(b"\x89PNG", "image/png")


# --- хук ---


def expired_client(hook, **kwargs):
    def handler(request):
        return httpx.Response(401, json={"error": "token_expired", "message": "m"})

    return remote_diary(
        "http://t", "k", transport=httpx.MockTransport(handler), on_token_expired=hook, **kwargs
    )


async def test_hook_called_once_with_token_then_raises():
    seen = []

    async def hook(token):
        seen.append(token)

    token = Token(valid_token())
    async with expired_client(hook) as api:
        with pytest.raises(TokenExpired):
            await api.student(token).me()
    assert seen == [token]


async def test_sync_function_hook_works_too():
    seen = []
    async with expired_client(seen.append) as api:
        with pytest.raises(TokenExpired):
            await api.student(valid_token()).me()
    assert len(seen) == 1


async def test_hook_not_called_for_other_errors():
    seen = []
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": "token_invalid", "message": "m"})
    )
    async with remote_diary(
        "http://t", "k", transport=transport, on_token_expired=seen.append
    ) as api:
        with pytest.raises(TokenInvalid):
            await api.student(valid_token()).me()
    assert seen == []


# --- Token ---


def test_token_from_jwt_knows_expiry():
    exp = datetime.now(UTC) + timedelta(minutes=30)
    token = Token(make_token(exp))
    assert abs(token.expires_at - exp) < timedelta(seconds=1)
    assert timedelta(minutes=29) < token.expires_in() <= timedelta(minutes=30)
    assert not token.is_expiring()
    assert token.is_expiring(within=timedelta(hours=1))


def test_expired_token_is_expiring():
    assert Token(make_token(datetime.now(UTC) - timedelta(seconds=1))).is_expiring()


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c", make_token(None)])
def test_not_a_diary_jwt_has_no_expiry(bad):
    token = Token(bad)
    assert token.expires_at is None
    assert token.expires_in() is None


def test_token_repr_has_no_secret():
    jwt = valid_token()
    token = Token(jwt)
    for text in (repr(token), str(token), f"{token}", repr([token])):
        assert jwt not in text
        assert jwt.split(".")[1] not in text
        assert "sha256=" in text


async def test_student_accepts_str_and_token(app):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        jwt = valid_token()
        assert api.student(jwt).token == api.student(Token(jwt)).token


# --- B5: сбой хука не затирает цепочку TokenExpired ---


async def test_failing_hook_keeps_original_context_of_token_expired():
    from diarysdk.remote._core import Request

    def broken(token):
        raise RuntimeError("секрет-в-тексте")

    async with expired_client(broken) as api:
        original = ValueError("исходная причина")

        async def send(spec, token=None):
            try:
                raise original
            except ValueError:
                raise TokenExpired("m", status=401) from None

        api._send = send
        with pytest.raises(TokenExpired) as caught:
            await api.student(valid_token())._call(Request("GET", "/v1/me"))
    assert caught.value.__context__ is original
    assert any("RuntimeError" in note for note in caught.value.__notes__)
    assert not any("секрет-в-тексте" in note for note in caught.value.__notes__)


# --- B6/B7: токен ---


def test_token_equality_by_value():
    jwt = valid_token()
    assert Token(jwt) == Token(jwt)
    assert Token(jwt) != Token(make_token(datetime.now(UTC) + timedelta(hours=1), sub="2"))
    assert Token(jwt) != jwt


@pytest.mark.parametrize("bad_exp", ["1893456000", True, False, None, [1], {"a": 1}])
def test_exp_must_be_a_number_like_on_the_server(bad_exp):
    import base64
    import json

    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    jwt = f"{part({'alg': 'none'})}.{part({'exp': bad_exp})}.c2ln"
    assert Token(jwt).expires_at is None


# --- B11: списки с данными доезжают до клиента ---


async def test_lists_with_data_reach_client_models(app):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        student = api.student(valid_token())
        marks = await student.marks(D, E)
        schedule = await student.schedule(D, E)
        homework = await student.homework(D, E)
    assert [(m.id, m.value, m.subject.name) for m in marks] == [(11, "9", "Алгебра")]
    assert [(i.id, i.room) for i in schedule] == [(21, "204")]
    assert [(h.id, h.text, h.is_done) for h in homework] == [(31, "№ 5", False)]


# --- B16: 404 новых методов — NotFound ---


@pytest.mark.parametrize(
    ("name", "arg", "diary_method"), [("subject", 101, "subject"), ("mark", 7, "mark")]
)
async def test_not_found_of_new_methods_is_not_found_error(
    app, fake_diary, name, arg, diary_method
):
    from diarysdk import NotFound

    fake_diary.answers[name] = NotFound()
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        with pytest.raises(NotFound) as caught:
            await getattr(api.student(valid_token()), name)(arg)
    assert caught.value.status == 404
