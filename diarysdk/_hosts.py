"""Адреса хостов дневника и Госуслуг."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Hosts:
    dnevnik: str = "https://authedu.mosreg.ru"
    school_api: str = "https://authedu.mosreg.ru/api"
    school: str = "https://myschool.mosreg.ru"
    # Госуслуги: на них идёт только вход через ЕСИА (_login/esia.py).
    esia: str = "https://esia.gosuslugi.ru"
