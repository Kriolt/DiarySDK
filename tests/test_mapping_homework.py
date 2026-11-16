import pytest

from diarysdk._mapping.homework import homework
from diarysdk.errors import UpstreamFormat
from tests.fakes import fixture


def test_homework_from_fixture():
    result = [h.model_dump(mode="json") for h in homework(fixture("homeworks.json"))]

    assert result == [
        {
            "id": 40001,
            "due": "2026-10-22",
            "assigned_on": "2026-10-20",
            "subject": {"id": 101, "name": "Алгебра"},
            "text": "№ 1-5 стр. 10",
            "materials": [
                {
                    "title": "Задание.pdf",
                    "url": "https://dnevnik.test/files/zadanie.pdf",
                    "description": None,
                    "content_type": None,
                    "type_name": "Вложения",
                    "action_name": "Посмотреть",
                }
            ],
            "attachments": [
                {"name": "Решение.docx", "url": "https://dnevnik.test/files/reshenie.docx"}
            ],
            "is_done": False,
            "has_teacher_answer": False,
            "type": "OO",
            "group_id": 6001,
            "homework_id": 30000,
            "entry_id": 30001,
            # Время урока без пояса — по Москве.
            "lesson_at": "2026-10-22T08:30:00+03:00",
            "created_at": "2026-10-20T12:00:00+03:00",
            "updated_at": None,
            "comments": [],
            "written_answer": None,
        },
        {
            "id": 40002,
            "due": "2026-10-23",
            "assigned_on": "2026-10-21",
            "subject": {"id": 104, "name": "Литература"},
            "text": "Выучить стихотворение",
            "materials": [],
            "attachments": [],
            "is_done": True,
            "has_teacher_answer": None,
            "type": "OO",
            "group_id": None,
            "homework_id": None,
            "entry_id": None,
            "lesson_at": None,
            "created_at": None,
            "updated_at": None,
            "comments": None,
            "written_answer": None,
        },
    ]


def test_bare_list_answer_is_accepted():
    assert len(homework(fixture("homeworks.json")["payload"])) == 2


@pytest.mark.parametrize(
    "data", ["ДЗ", {"payload": "много"}, {"payload": [{"is_done": "может быть"}]}]
)
def test_wrong_shape_is_format_error(data):
    with pytest.raises(UpstreamFormat):
        homework(data)


def test_homework_is_sorted_by_due_date_then_subject():
    # Порядок дневника зависит от хоста (наблюдение: authedu.mosreg.ru/api и
    # api.myschool отдали те же ДЗ в разном порядке), поэтому сортируем сами.
    def item(entry_id, due, subject):
        return {
            "homework_entry_student_id": entry_id,
            "date_prepared_for": due,
            "subject_id": 1,
            "subject_name": subject,
        }

    result = homework(
        {
            "payload": [
                item(3, "2026-10-27", "Химия"),
                item(4, None, "Алгебра"),
                item(1, "2026-10-26", "Физика"),
                item(2, "2026-10-27", "Алгебра"),
            ]
        }
    )

    assert [h.id for h in result] == [1, 2, 3, 4]


def test_id_is_only_the_entry_student_id():
    # Запись (homework_done) принимает только id из пространства
    # homework_entry_student_id: другие id в `id` не подставляются.
    result = homework(
        {"payload": [{"homework_entry_id": 30001, "homework_id": 30000, "description": "x"}]}
    )

    assert result[0].id is None
    assert (result[0].entry_id, result[0].homework_id) == (30001, 30000)
