"""Сборка RemoteDiary поверх подставного транспорта."""

import httpx

from diarysdk.remote import RemoteDiary


def remote_diary(base_url: str, api_key: str, *, transport: httpx.AsyncBaseTransport, **options):
    http = httpx.AsyncClient(transport=transport)
    return RemoteDiary(base_url, api_key, http=http, **options)
