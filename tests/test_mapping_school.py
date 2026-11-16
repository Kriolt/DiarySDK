from diarysdk._mapping.school import school
from diarysdk._wire.mobile import SchoolInfo
from tests.fakes import fixture


def test_school_from_fixture():
    result = school(SchoolInfo.model_validate(fixture("school_info.json")))

    assert result.model_dump(mode="json") == {
        "name": "МБОУ «Гимназия № 0»",
        "type": "Гимназия",
        "principal": "Директорова Дарья Дмитриевна",
        "address": "г. Тестовый, ул. Школьная, д. 1",
        "phone": "+7 495 000-00-00",
        "email": "school@example.invalid",
        "website": "https://school.example.invalid",
        "classroom_teachers": [
            {"last_name": "Классная", "first_name": "Анна", "middle_name": "Петровна"}
        ],
        "teachers": [
            {
                "last_name": "Учителев",
                "first_name": "Иван",
                "middle_name": "Иванович",
                "subjects": ["Алгебра", "Геометрия"],
            },
            {"last_name": "Физикова", "first_name": "Ольга", "middle_name": None, "subjects": []},
        ],
        "branches": [
            {
                "name": "Основное здание",
                "address": "г. Тестовый, ул. Школьная, д. 1",
                "is_main": True,
                "building_id": 701,
                "is_student_building": True,
                "type": "main",
            },
            {
                "name": "Корпус 2",
                "address": "г. Тестовый, ул. Садовая, д. 2",
                "is_main": False,
                "building_id": 702,
                "is_student_building": False,
                "type": "branch",
            },
        ],
        "id": 3001,
        "county": "г.о. Тестовый",
        "district": None,
    }


def test_building_id_tolerates_unexpected_type():
    data = fixture("school_info.json")
    data["branches"][0]["building_id"] = "к-1"

    result = school(SchoolInfo.model_validate(data))

    assert result.branches[0].building_id is None
    assert result.branches[1].building_id == 702


def test_empty_school_is_all_null():
    result = school(SchoolInfo.model_validate({}))

    assert result.name is None
    assert result.address is None
    assert result.teachers == []


def test_response_models_are_strict_in_service_tests():
    # Клиент пропускает лишние поля, но сервис при сборке ответа опечаток не прощает
    # (tests/conftest.py включает extra="forbid" для всех тестов вне tests/remote).
    import pytest
    from pydantic import ValidationError

    from diarysdk.models.school import School

    with pytest.raises(ValidationError):
        School(nmae="x")
