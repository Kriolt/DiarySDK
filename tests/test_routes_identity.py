from diarysdk.models.common import ClassUnit, SchoolBrief
from diarysdk.models.identity import Identity, IdentityPerson


async def test_identity(api, fake_diary):
    fake_diary.answers["identity"] = Identity(
        person=IdentityPerson(last_name="Тестов"), school=SchoolBrief(), class_=ClassUnit()
    )

    response = await api.get("/v1/identity")

    assert response.status_code == 200
    assert set(response.json()) == {"person", "school", "class", "representatives"}
    assert response.json()["person"]["snils"] is None
