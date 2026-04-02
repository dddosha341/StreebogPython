# `src/hasher_interface.py` — единый интерфейс хэшера

Модуль задаёт общий контракт для потоковых реализаций Стрибог и предоставляет удобные обёртки.

## Публичные сущности

- `HasherProtocol`
  - контракт для потокового хэшера с методами:
    - `update(data)`
    - `digest()`
    - `hexdigest()`
    - `copy()`

- `create_hasher(digest_size=512, impl="base" | "fast")`
  - фабрика, возвращающая экземпляр:
    - `src/streebog.py:Streebog` для `impl="base"`
    - `src/streebog_fast.py:StreebogFast` для `impl="fast"`

- `hash_bytes(data, digest_size=512, impl="base" | "fast") -> bytes`
  - одноразовое вычисление дайджеста для массива байтов.
  - Внутренне вызывает `create_hasher`, затем `update` и `digest`.

## Использование из других модулей

`collision_search.py` и `meaningful_collision.py` используют `hash_bytes`, а `meaningful_collision.py` также напрямую вызывает `create_hasher` для потоковой работы и `copy()` во время оптимизации поиска.

