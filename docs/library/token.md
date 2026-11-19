# `diarysdk.token` — токен дневника

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.token`

**Исходный код:** [`diarysdk/token.py`](../../diarysdk/token.py)

---

Токен — JWT дневника, по которому идут все запросы ученика или родителя. SDK
**не хранит токены**: это забота вашего приложения. `Token` лишь носит
значение и срок и не даёт значению случайно попасть в журнал.

`Token` импортируется и из корня: `from diarysdk import Token`.

<a id="diarysdk.Token"></a>

### *класс* `diarysdk.Token(value, expires_at=None, method="jwt")`

- **value** (`str`) — сам JWT.
- **expires_at** (`datetime` | `None`) — срок. Не задан — читается из поля
  `exp` самого токена. Срок без часового пояса считается UTC.
- **method** (`"jwt"` | `"password"` | `"esia"`) — как получен токен: из
  готовой строки, входом по паролю или через Госуслуги.

Подпись SDK не проверяет — её проверяет дневник; из токена читаются только
срок, субъект и роли.

```python
from datetime import UTC, datetime, timedelta

from diarysdk import Token

token = Token("eyJ...", datetime.now(UTC) + timedelta(hours=8), method="esia")
row = {"value": token.value, "expires_at": token.expires_at, "method": token.method}
restored = Token(row["value"], row["expires_at"], row["method"])
assert restored == token
```

<a id="diarysdk.Token.value"></a>

#### *атрибут* `value`

Значение JWT. Это единственный способ его получить: `str()` и `repr()` его не
показывают.

<a id="diarysdk.Token.expires_at"></a>

#### *атрибут* `expires_at`

`datetime` в UTC или **`None`**, если срок неизвестен: строка не JWT или в ней
нет `exp`. При создании `Token` это не ошибка, но перед первым запросом ядро
и сервис отвергнут такой токен
([`ensure_usable()`](#diarysdk.Token.ensure_usable) →
[`TokenInvalid`](errors.md#diarysdk.errors.TokenInvalid)).

<a id="diarysdk.Token.method"></a>

#### *атрибут* `method`

`"jwt"`, `"password"` или `"esia"`.

<a id="diarysdk.Token.subject_id"></a>

#### *свойство* `subject_id`

Субъект токена (`sub` из payload) строкой; нет или не разобрался — `None`.

<a id="diarysdk.Token.roles"></a>

#### *свойство* `roles`

Список id ролей дневника строками: `"1"` — ученик, `"2"` — родитель. Читаются
из `rls` (id роли — число в начале каждой группы), а без него — из `rol`
(строка через запятую или список) или `roles`. Ролей нет — пустой список.

*Изменено в версии 0.2.0:* роли читаются из `rls` настоящего JWT (раньше
список всегда был пустым).

<a id="diarysdk.Token.expires_in"></a>

#### *метод* `expires_in(now=None)`

Сколько осталось до истечения: `timedelta`, отрицательный, если токен уже
истёк; `None`, если срок неизвестен.

- **now** (`datetime` | `None`) — момент отсчёта с часовым поясом; по
  умолчанию — сейчас.

<a id="diarysdk.Token.is_expiring"></a>

#### *метод* `is_expiring(within=timedelta(minutes=5))`

`True`, если осталось не больше `within` или токен уже истёк. Срок неизвестен
— `False`.

<a id="diarysdk.Token.ensure_usable"></a>

#### *метод* `ensure_usable(now=None)`

Проверить, что токен годится для запроса, не спрашивая дневник. Нет срока —
[`TokenInvalid`](errors.md#diarysdk.errors.TokenInvalid) (это не токен
дневника); срок вышел — [`TokenExpired`](errors.md#diarysdk.errors.TokenExpired).

Ядро и сервис делают эту проверку сами перед каждым вызовом: токен без срока
или с вышедшим сроком отклоняется без обращения к дневнику.

### Сравнение и печать

- `repr(token)` и `str(token)` показывают метод, срок и первые 6 символов
  SHA-256 значения: `Token(method=esia, expires_at=..., sha256=1a2b3c)`. По
  метке видно, тот же это токен или новый, но значение по ней не восстановить.
- `==` сравнивает значения за постоянное время; токен можно класть в `set` и
  использовать ключом словаря.
