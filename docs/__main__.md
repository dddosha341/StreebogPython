# `src/__main__.py` — запуск через `python -m src`

Файл позволяет запускать проект как модуль Python:

```bash
python -m src <command> [options]
```

Внутри экспортируется и вызывается `main()` из `src/cli.py`.

