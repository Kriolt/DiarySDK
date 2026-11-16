from diarysdk.errors import UpstreamError
from diarysdk.models.notifications import Notification


async def test_notifications_list(api, fake_diary):
    fake_diary.answers["notifications"] = [Notification(event_type="create_mark")]

    response = await api.get("/v1/notifications")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [
        {
            "at": None,
            "event_type": "create_mark",
            "subject_name": None,
            "teacher_name": None,
            "author_profile_id": None,
            "lesson_date": None,
            "mark": None,
            "homework": None,
        }
    ]


async def test_diary_error_is_upstream_error(api, fake_diary):
    fake_diary.answers["notifications"] = UpstreamError(upstream_status=503)

    response = await api.get("/v1/notifications")

    assert response.status_code == 502
