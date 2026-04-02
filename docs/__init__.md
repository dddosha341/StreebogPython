# `src/__init__.py` — публичный API пакета

Модуль отвечает за экспорт «верхнего уровня» для пакета `src`.

## Что экспортируется

Всегда:
- `streebog_512`, `streebog_256`
- `create_hasher`, `hash_bytes`
- `HasherProtocol`

Опционально (если импорт `src/streebog_fast.py` проходит успешно):
- `streebog_512_fast`, `streebog_256_fast`

Экспорт задаётся через `__all__`, чтобы IDE и `from src import ...` видели ожидаемые имена.

