"""Ответы сервиса справок certificates/family: читаемые поля."""

from typing import Any

from diarysdk._wire.common import DT, Wire


class CertificateStatus(Wire):
    statusID: int | None = None
    statusDescription: str | None = None


class WireCertificate(Wire):
    id: Any = None
    statusID: int | None = None
    purpose: str | None = None
    requestDate: DT | None = None
    issueDate: DT | None = None
    holdDate: DT | None = None


class CertificatePage(Wire):
    certificates: list[WireCertificate] | None = None
    count: int | None = None
    limit: int | None = None
    offset: int | None = None
