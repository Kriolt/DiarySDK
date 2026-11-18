"""Файл итоговых оценок и справки об обучении."""

import dataclasses
from datetime import date

import pytest

from diarysdk import errors
from diarysdk._gateway import DiaryGateway
from diarysdk._port import Ctx
from diarysdk.models import DiaryFile
from tests.fakes import GUID, HOSTS, STUDENT, FakeTransport, fixture

PARENT = dataclasses.replace(STUDENT, access="parent", parent_profile_id=STUDENT.profile_id)
FILE = "/api/family/web/v1/final_marks/file"
CERTS = "/api/certificates/family/v1/certificates"
STATUSES = "/api/certificates/family/v1/certificates/statuses"


@pytest.fixture
def fake():
    fake = FakeTransport()
    fake.add(FILE, b"%PDF-1.7 fake", content_type="application/octet-stream")
    fake.add(STATUSES, fixture("certificate_statuses.json"))
    fake.add(CERTS, fixture("certificates.json"))
    return fake


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS, today=lambda: date(2026, 11, 18))


async def test_final_marks_file_is_pdf(gateway, fake):
    result = await gateway.final_marks_file(Ctx(token="t.t.t", student=STUDENT), 2025, "landscape")

    assert isinstance(result, DiaryFile)
    assert (result.content, result.content_type) == (b"%PDF-1.7 fake", "application/pdf")
    assert result.filename == "final-marks-2025.pdf"
    assert fake.sent[0].params == {
        "student_id": str(STUDENT.student_id),
        "academic_year_id": "13",
        "orientation": "landscape",
    }


async def test_final_marks_file_not_pdf_is_format_error(gateway, fake):
    fake.add(FILE, b"<html>error</html>", content_type="text/html")

    with pytest.raises(errors.UpstreamFormat):
        await gateway.final_marks_file(Ctx(token="t.t.t", student=STUDENT), 2025, "portrait")


async def test_certificates_for_parent(gateway, fake):
    (cert,) = await gateway.certificates(Ctx(token="t.t.t", student=PARENT))

    assert (cert.id, cert.status_id, cert.status) == (77, 20, "Сформирована")
    assert (cert.requested_on, cert.issued_on, cert.valid_until) == (
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2027, 10, 2),
    )
    assert cert.purpose == "По месту требования"
    listing = next(r for r in fake.sent if r.url.endswith("/certificates"))
    assert listing.params == {
        "requestDateFrom": "2024-11-18",
        "requestDateTo": "2026-11-18",
        "studentId": GUID,
        "limit": "10",
        "offset": "0",
    }


async def test_certificates_null_list_is_empty(gateway, fake):
    fake.add(CERTS, {"certificates": None, "count": 0, "limit": 10, "offset": 0})

    assert await gateway.certificates(Ctx(token="t.t.t", student=PARENT)) == []


async def test_certificates_for_student_are_not_for_role_before_request(gateway, fake):
    with pytest.raises(errors.NotForRole) as error:
        await gateway.certificates(Ctx(token="t.t.t", student=STUDENT))

    assert error.value.role == "student"
    assert fake.sent == []
