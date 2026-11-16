import pytest

from diarysdk.errors import UpstreamError
from diarysdk.models.common import Subject
from diarysdk.models.subjects import SubjectSummary


async def test_subjects_list(api, fake_diary):
    fake_diary.answers["subjects"] = [SubjectSummary(subject=Subject(id=1, name="Алгебра"))]

    response = await api.get("/v1/subjects")

    assert response.status_code == 200
    assert response.json() == [
        {
            "subject": {"id": 1, "name": "Алгебра"},
            "average": None,
            "dynamic": None,
            "year_mark": None,
            "periods": [],
        }
    ]


async def test_diary_error_is_upstream_error(api, fake_diary):
    fake_diary.answers["subjects"] = UpstreamError(upstream_status=503)

    response = await api.get("/v1/subjects")

    assert response.status_code == 502
    assert response.json()["upstream_status"] == 503


async def test_subject_detail(api, fake_diary):
    from diarysdk.models.subjects import SubjectDetail

    fake_diary.answers["subject"] = SubjectDetail(subject_id=101, subject_name="Алгебра")

    response = await api.get("/v1/subjects/101")

    assert response.status_code == 200
    assert response.json()["subject_name"] == "Алгебра"
    assert response.json()["periods"] == []
    assert fake_diary.args["subject"][1] == 101


async def test_foreign_subject_is_not_found(api, fake_diary):
    from diarysdk.errors import NotFound

    fake_diary.answers["subject"] = NotFound()

    response = await api.get("/v1/subjects/999")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


@pytest.mark.parametrize("subject_id", ["abc", "-1", "0"])
async def test_bad_subject_id_is_bad_request(api, fake_diary, subject_id):
    response = await api.get(f"/v1/subjects/{subject_id}")

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []
