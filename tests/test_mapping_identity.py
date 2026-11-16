import json

from diarysdk._mapping.identity import identity
from diarysdk._wire.web import PersonData, WebFamilyProfile
from tests.fakes import fixture

PERSON = {
    "last_name": "Тестов",
    "first_name": "Тест",
    "middle_name": "Тестович",
    "birth_date": "2010-03-15",
    "sex": "male",
    "phone": "+7 000 000-00-01",
    "email": "student@example.invalid",
    "snils": "111-222-333 44",
    # Из профиля, в том числе поля, которых модель ответа не объявляет.
    "grade_book": {"number": "ЛД-0042", "date": "2016-09-01"},
    "health": {"pe_group_id": 2},
    "education_level_id": 3,
    "service_type_id": 1,
    "parallel_curriculum_id": 1,
    "specialty": {"code": None, "name": None},
    "user_id": 5001,
    "sudir_login": None,
    "sudir_account_exists": False,
    "is_legal_representative": False,
    "groups": [
        {"id": 6001, "name": "Алгебра 10-Ф ф.-м.", "subject_id": 101, "is_fake": False},
        {"id": 6002, "name": "Физика 10-Ф ф.-м.", "subject_id": 102, "is_fake": False},
        {"id": 6003, "name": "Английский язык 10-Ф гр. 1", "subject_id": 103, "is_fake": False},
    ],
    # Из карточки человека; без карточки — пусто.
    "birthplace": None,
    "citizenship_id": None,
    "documents": [],
    "addresses": [],
    "education": [],
    "contacts": [],
    "categories": None,
    "agents": None,
    "preventions": None,
    "citizenship": None,
    "children": None,
}


def profile(**child_changes):
    data = fixture("profile.json")
    data["children"][0].update(child_changes)
    return WebFamilyProfile.model_validate(data)


def card():
    return PersonData.model_validate(fixture("person_data.json"))


def test_identity_from_profile():
    result = identity(profile(), None).model_dump(mode="json")

    assert result == {
        "person": PERSON,
        "school": {
            "id": 3001,
            "name": "МБОУ «Гимназия № 0»",
            "short_name": "Гимназия № 0",
            "municipality": "г.о. Тестовый",
        },
        "class": {"id": 4001, "name": "10-Ф", "level": 10},
        "representatives": [
            {
                "type": "mother",
                "last_name": "Представителева",
                "first_name": "Мария",
                "middle_name": "Ивановна",
                "sex": "female",
                "birth_date": "1985-05-05",
                "phone": "+7 000 000-11-22",
                "email": "rep@example.invalid",
                "snils": "999-888-777 66",
                "guid": "00000000-0000-4000-8000-0000000000a1",
                "type_id": 1,
            }
        ],
    }


def test_profile_without_new_fields_has_null_objects():
    data = fixture("profile.json")
    child = data["children"][0]
    for key in ["grade_book_number", "grade_book_date", "physical_training_health_group_id"]:
        del child[key]
    child["groups"] = None

    person = identity(WebFamilyProfile.model_validate(data), None).model_dump(mode="json")["person"]

    assert person["grade_book"] == {"number": None, "date": None}
    assert person["health"] == {"pe_group_id": None}
    assert person["groups"] == []


def test_profile_snils_wins_over_card():
    assert identity(profile(), card()).person.snils == "111-222-333 44"


def test_empty_profile_snils_is_taken_from_card():
    assert identity(profile(snils=None), card()).person.snils == "555-666-777 88"


def test_phone_and_email_are_not_guessed_from_card_contacts():
    # Контакты карточки отдаются целиком в contacts; угадывать по коду типа,
    # какой из них телефон ученика, не будем.
    result = identity(profile(phone=None, email=None, snils=None), card())

    assert result.person.phone is None
    assert result.person.email is None


def test_nothing_anywhere_is_null():
    person = identity(profile(phone=None, email=None, snils=None), None).person

    assert (person.phone, person.email, person.snils) == (None, None, None)


def test_identity_card_fields():
    person = identity(profile(), card()).model_dump(mode="json")["person"]

    assert person["birthplace"] == "г. Тестовый"
    assert person["citizenship_id"] == 1
    assert person["documents"] == [
        {
            "type_id": 1,
            "type": "Свидетельство о рождении",
            "series": "I-ТС",
            "number": "000001",
            "issuer": "Отдел ЗАГС",
            "issued": "2010-03-20",
            "expiration": None,
            "subdivision_code": None,
            "act": {"number": "100", "date": "2010-03-20"},
            "comment": None,
            "attachments": [],
        }
    ]
    assert person["addresses"] == [
        {"type_id": 1, "type": "Регистрации", "address": "ул. Тестовая, д. 1", "flat": "1"}
    ]
    assert person["education"] == [
        {
            "organization_id": 3001,
            "class": {
                "id": 4001,
                "uid": "class-uid-1",
                "name": "10-Ф",
                "letter": "Ф",
                "parallel": "10",
                "academic_year_id": 13,
            },
            "form": "Очная",
            "financing": "Бюджет",
            "service_type": "Основное",
            "deduction_reason": None,
            "began": "2016-09-01",
            "ended": "2027-08-31",
            "notes": None,
        }
    ]
    assert person["contacts"] == [
        {"id": 1, "type_id": 1, "type": "Телефон", "value": "+7 000 000-00-02", "is_default": True}
    ]
    # Как пришли: форма по наблюдениям не видна.
    assert person["agents"] == [
        {"agent_person_id": "00000000-0000-4000-8000-0000000000a1", "agent_type_id": 1}
    ]
    assert person["categories"] is None


def test_card_metadata_never_leaves():
    text = json.dumps(identity(profile(), card()).model_dump(mode="json"), ensure_ascii=False)

    for service in ["служебное", "служебный-фиас", "validation", "actual_from"]:
        assert service not in text, service


def test_unconfirmed_profile_fields_tolerate_unexpected_types():
    # Эти поля в наблюдениях были null — тип угадан по смыслу. Неожиданный тип даёт
    # текст или null, а не 500 на всю карточку.
    data = fixture("profile.json")
    child = data["children"][0]
    child.update(
        grade_book_number=42,
        profession_specialty_code=90207,
        physical_training_health_group_id="основная",
    )
    child["representatives"][0]["type_id"] = "mother"

    result = identity(WebFamilyProfile.model_validate(data), None)

    assert result.person.grade_book.number == "42"
    assert result.person.specialty.code == "90207"
    assert result.person.health.pe_group_id is None
    assert result.representatives[0].type_id is None


def test_document_attachment_id_is_text():
    # id вложения — строка (скорее всего UUID).
    data = fixture("person_data.json")
    data["documents"][0]["attachments"] = [
        {"id": "5f0c1a2b-0000-4000-8000-000000000001", "name": "scan.pdf"}
    ]

    person = identity(profile(), PersonData.model_validate(data)).model_dump(mode="json")["person"]

    assert person["documents"][0]["attachments"] == [
        {"id": "5f0c1a2b-0000-4000-8000-000000000001", "name": "scan.pdf", "uploaded_at": None}
    ]


def test_card_section_our_schema_rejects_is_empty_not_an_error():
    # Библиотека приняла карточку, а наша схема — нет: этот раздел пуст,
    # остальное на месте, а не 500 на всю карточку.
    data = fixture("person_data.json")
    data["contacts"] = [{"data": "x", "default": "да"}]

    person = identity(profile(), PersonData.model_validate(data)).person

    assert person.contacts == []
    assert len(person.documents) == 1
    assert person.snils == "111-222-333 44"


def test_deduction_reason_is_its_name_without_metadata():
    # Ученик, сменивший школу: причина выбытия — справочник, как форма обучения.
    data = fixture("person_data.json")
    data["education"][0]["deduction_reason"] = {
        "id": 7,
        "name": "Перевод",
        "actual_from": "2000-01-01",
        "actual_to": "2100-01-01",
    }

    result = identity(profile(), PersonData.model_validate(data)).model_dump(mode="json")

    assert result["person"]["education"][0]["deduction_reason"] == "Перевод"
    assert "actual_from" not in json.dumps(result, ensure_ascii=False)


def test_odd_contacts_are_skipped():
    data = fixture("person_data.json")
    data["contacts"] = ["строка", {"data": "x"}]

    person = identity(profile(), PersonData.model_validate(data)).person

    assert [c.model_dump() for c in person.contacts] == [
        {"id": None, "type_id": None, "type": None, "value": "x", "is_default": None}
    ]
