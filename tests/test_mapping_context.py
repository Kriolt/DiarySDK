import pytest

from diarysdk._mapping.context import student_context
from diarysdk._wire.web import WebFamilyProfile
from diarysdk.errors import MultipleChildren, UpstreamFormat
from tests.fakes import STUDENT, fixture


def profile(**child_changes):
    data = fixture("profile.json")
    data["children"][0].update(child_changes)
    return data


def test_context_takes_ids_from_profile_and_child():
    parsed = WebFamilyProfile.model_validate(profile())

    assert student_context(parsed, STUDENT.expires_at) == STUDENT


def test_parent_with_two_children_is_not_supported():
    data = profile()
    data["children"].append({**data["children"][0], "id": 9002})

    with pytest.raises(MultipleChildren):
        student_context(WebFamilyProfile.model_validate(data), STUDENT.expires_at)


def test_profile_without_children_is_format_error():
    data = profile()
    data["children"] = []

    with pytest.raises(UpstreamFormat):
        student_context(WebFamilyProfile.model_validate(data), STUDENT.expires_at)


@pytest.mark.parametrize("field", ["id", "contingent_guid", "class_unit_id", "school"])
def test_child_without_needed_id_is_format_error(field):
    data = profile(**{field: None})

    with pytest.raises(UpstreamFormat):
        student_context(WebFamilyProfile.model_validate(data), STUDENT.expires_at)


def test_profile_without_own_id_is_format_error():
    data = profile()
    data["profile"]["id"] = None

    with pytest.raises(UpstreamFormat):
        student_context(WebFamilyProfile.model_validate(data), STUDENT.expires_at)


def test_context_carries_curriculum_id():
    parsed = WebFamilyProfile.model_validate(profile(parallel_curriculum_id=555))

    assert student_context(parsed, STUDENT.expires_at).parallel_curriculum_id == 555


def test_context_without_curriculum_id_has_none_not_error():
    parsed = WebFamilyProfile.model_validate(profile(parallel_curriculum_id=None))

    assert student_context(parsed, STUDENT.expires_at).parallel_curriculum_id is None
