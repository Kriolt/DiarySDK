"""Таблица ошибок: коды, статусы и обратимость ответа сервера в класс клиента."""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from diarysdk import errors
from diarysdk.errors import (
    BY_CODE,
    AuthError,
    BadApiKey,
    BadCaptcha,
    BadCode,
    BadCredentials,
    BadRequest,
    DiaryError,
    FlowExpired,
    ForbiddenScope,
    LoginBlocked,
    MultipleChildren,
    NetworkError,
    NoAvatar,
    NotForRole,
    NotFound,
    RateLimited,
    RemoteError,
    SettingError,
    SettingNotSet,
    SettingsMissing,
    SettingUnrestorable,
    TokenExpired,
    TokenInvalid,
    UnsupportedContact,
    UnsupportedStep,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
    WriteUncertain,
    from_response,
    retry_after_header,
    to_response,
)
from diarysdk.models.auth import LoginMfa, LoginStep

STEP = LoginStep(
    flow_id="f1",
    step="mfa",
    expires_at=datetime(2026, 11, 16, tzinfo=UTC),
    mfa=LoginMfa(kind="sms", ttl=300, attempts_left=2),
)

# Таблица из плана: класс -> (код, HTTP-статус).
TABLE = {
    DiaryError: ("diary_error", 502),
    AuthError: ("auth_error", 401),
    TokenInvalid: ("token_invalid", 401),
    TokenExpired: ("token_expired", 401),
    BadCredentials: ("bad_credentials", 401),
    BadCode: ("bad_code", 401),
    BadCaptcha: ("bad_captcha", 401),
    FlowExpired: ("flow_expired", 404),
    LoginBlocked: ("login_blocked", 409),
    UnsupportedStep: ("unsupported_step", 422),
    BadRequest: ("bad_request", 400),
    NotFound: ("not_found", 404),
    NoAvatar: ("no_avatar", 404),
    MultipleChildren: ("multiple_children", 422),
    NotForRole: ("not_for_role", 422),
    SettingError: ("setting_error", 409),
    SettingsMissing: ("settings_missing", 409),
    SettingNotSet: ("setting_unset", 409),
    SettingUnrestorable: ("setting_unrestorable", 409),
    UnsupportedContact: ("contact_not_email", 422),
    RateLimited: ("rate_limited", 429),
    UpstreamError: ("upstream_error", 502),
    UpstreamTimeout: ("upstream_timeout", 504),
    UpstreamFormat: ("upstream_format", 502),
    RemoteError: ("remote_error", 502),
    BadApiKey: ("bad_api_key", 403),
    ForbiddenScope: ("forbidden_scope", 403),
}


def _public_classes() -> list[type[DiaryError]]:
    found = [
        value
        for value in vars(errors).values()
        if isinstance(value, type) and issubclass(value, DiaryError)
    ]
    return [cls for cls in found if not cls.__name__.startswith("_")]


def test_table_matches_the_plan():
    for cls, (code, status) in TABLE.items():
        assert (cls.code, cls.http_status) == (code, status), cls.__name__


def test_every_public_class_is_in_the_table():
    assert set(_public_classes()) == {*TABLE, WriteUncertain, NetworkError}


def test_codes_unique():
    codes = [cls.code for cls in TABLE]
    assert len(codes) == len(set(codes))


def test_by_code_is_built_from_subclasses():
    assert {code: cls for cls, (code, _) in TABLE.items()} == {
        code: cls for code, cls in BY_CODE.items() if code != "token_missing"
    }
    assert BY_CODE["token_missing"] is TokenInvalid


def _instances() -> dict[type[DiaryError], DiaryError]:
    made = {cls: cls() for cls in TABLE}
    made[BadCode] = BadCode(step=STEP)
    made[BadCaptcha] = BadCaptcha(step=STEP)
    made[RateLimited] = RateLimited(retry_after=7)
    made[UpstreamError] = UpstreamError(upstream_status=500)
    made[UnsupportedStep] = UnsupportedStep(what="PUSH", hint="Подтвердите вход в приложении")
    made[SettingNotSet] = SettingNotSet(field="goal")
    made[SettingUnrestorable] = SettingUnrestorable(field="goal")
    made[UpstreamFormat] = UpstreamFormat(problems=["тело.0.id: int_parsing"])
    return made


@pytest.mark.parametrize(
    "cls", [c for c in TABLE if c not in (RemoteError, BadApiKey, ForbiddenScope)]
)
def test_roundtrip_every_class(cls):
    error = _instances()[cls]

    status, body = to_response(error)
    back = from_response(status, body, retry_after_header(error))

    assert status == cls.http_status
    assert type(back) is cls
    assert str(back) == str(error)
    assert back.status == status
    if cls is RateLimited:
        assert back.retry_after == 7
    if cls is UpstreamError:
        assert back.upstream_status == 500
    if cls in (BadCode, BadCaptcha):
        assert back.step == STEP


@pytest.mark.parametrize("cls", [RemoteError, BadApiKey, ForbiddenScope])
def test_roundtrip_remote_classes(cls):
    # Сервер выдаёт только ключевые коды; remote_error приходит разве что от чужого сервиса.
    status, body = to_response(cls())
    assert type(from_response(status, body)) is cls


def test_message_survives_roundtrip_and_defaults_are_russian():
    status, body = to_response(BadRequest("Период длиннее 31 дней"))

    assert from_response(status, body).message == "Период длиннее 31 дней"
    assert all(cls().message for cls in TABLE)


def test_step_goes_into_body_as_json():
    _, body = to_response(BadCode(step=STEP))

    assert body["step"]["flow_id"] == "f1"
    assert body["step"]["mfa"]["attempts_left"] == 2


def test_core_step_payload_stays_out_of_response():
    # Ядро кладёт в step свой вызов ЕСИА (не модель): наружу он не идёт.
    _, body = to_response(BadCode(step=object()))

    assert "step" not in body


def test_upstream_status_only_on_plain_upstream_error():
    assert to_response(UpstreamError())[1]["upstream_status"] is None
    assert "upstream_status" not in to_response(UpstreamTimeout())[1]
    assert "upstream_status" not in to_response(UpstreamFormat())[1]


def test_retry_after_header():
    assert retry_after_header(RateLimited(retry_after=2.2)) == "3"
    assert retry_after_header(RateLimited(retry_after=0)) == "1"
    assert retry_after_header(RateLimited()) is None


def test_unsupported_step_and_setting_texts():
    assert str(UnsupportedStep(what="MAX_QUIZ", hint="Настройте MAX")) == (
        "ЕСИА просит шаг, которого сервис не умеет: MAX_QUIZ. Настройте MAX"
    )
    assert str(SettingNotSet(field="goal")) == "Настройка в дневнике не задана: goal"
    assert str(SettingNotSet()) == "Настройка в дневнике не задана"


def test_upstream_format_problems_have_paths_and_types_only():
    class Row(BaseModel):
        id: int

    with pytest.raises(ValidationError) as caught:
        Row.model_validate({"id": "секретное-значение"})

    error = UpstreamFormat.from_validation(caught.value)

    assert error.problems == ["id: int_parsing"]
    assert "секретное-значение" not in repr(error.problems) + str(error)


def test_write_uncertain_status_from_cause():
    error = WriteUncertain(cause=UpstreamTimeout())

    assert (error.code, error.http_status) == ("upstream_timeout", 504)
    assert to_response(error)[0] == 504
    assert to_response(error)[1]["error"] == "upstream_timeout"


def test_write_uncertain_exposes_upstream_status_of_cause():
    assert WriteUncertain(cause=UpstreamError(upstream_status=403)).upstream_status == 403
    assert WriteUncertain(cause=NetworkError()).upstream_status is None


def test_network_error_is_remote_not_upstream():
    assert isinstance(NetworkError(), RemoteError)
    assert not isinstance(NetworkError(), UpstreamError)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, "Unauthorized", AuthError),
        (403, None, RemoteError),
        (404, {"error": "new_code"}, NotFound),
        (429, {"error": 5, "message": []}, RateLimited),
        (500, {"error": "new_code", "message": "m"}, UpstreamError),
        (418, {}, DiaryError),
    ],
)
def test_unknown_code_falls_back_to_status(status, body, expected):
    error = from_response(status, body)

    assert type(error) is expected
    assert error.status == status


def test_unknown_code_keeps_message_or_names_status():
    assert from_response(500, {"error": "x", "message": "сломалось"}).message == "сломалось"
    assert from_response(500, None).message == "HTTP 500"


def test_retry_after_of_proxy_is_parsed_defensively():
    assert from_response(429, {}, "7").retry_after == 7
    assert from_response(429, {}, "завтра").retry_after is None
    assert from_response(429, {}, "-1").retry_after is None


def test_unknown_future_code_is_kept_as_raw_code():
    error = from_response(500, {"error": "future_code", "message": "m"})

    assert type(error) is UpstreamError
    assert error.code == "upstream_error"
    assert error.raw_code == "future_code"


def test_raw_code_defaults_to_class_code_and_follows_known_code():
    assert BadRequest().raw_code == "bad_request"
    assert WriteUncertain(cause=UpstreamTimeout()).raw_code == "upstream_timeout"
    assert from_response(404, {"error": "no_avatar"}).raw_code == "no_avatar"


def test_not_for_role_keeps_role_out_of_wire_and_back_as_same_class():
    error = NotForRole(role="parent")
    assert error.role == "parent"
    status, body = to_response(error)
    assert (status, body["error"]) == (422, "not_for_role")
    assert "role" not in body
    back = from_response(status, body)
    assert type(back) is NotForRole
    assert back.message == error.message


def test_multiple_children_points_to_parent_api():
    assert "diary.parent" in MultipleChildren().message
