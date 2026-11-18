"""Справки → публичные модели."""

from typing import Any

from pydantic import TypeAdapter, ValidationError

from diarysdk._mapping.common import as_date
from diarysdk._wire.certificates import CertificatePage, CertificateStatus, WireCertificate
from diarysdk.errors import UpstreamFormat
from diarysdk.models.certificates import Certificate

_STATUSES = TypeAdapter(list[CertificateStatus])


def _parse[T](adapter: TypeAdapter[T], data: Any) -> T:
    try:
        return adapter.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None


def statuses(data: Any) -> dict[int, str]:
    return {
        s.statusID: s.statusDescription
        for s in _parse(_STATUSES, data)
        if s.statusID is not None and s.statusDescription
    }


def page(data: Any) -> CertificatePage:
    return _parse(TypeAdapter(CertificatePage), data)


def certificates(items: list[WireCertificate], names: dict[int, str]) -> list[Certificate]:
    return [
        Certificate(
            id=item.id if isinstance(item.id, int | str) else None,
            status_id=item.statusID,
            status=names.get(item.statusID) if item.statusID is not None else None,
            purpose=item.purpose,
            requested_on=as_date(item.requestDate),
            issued_on=as_date(item.issueDate),
            valid_until=as_date(item.holdDate),
        )
        for item in items
    ]
