# Модульна контрольна робота, Щурик Євгеній N = 27

## Файли

| Файл | Опис |
|---|---|
| `gen_data.py` | попередньо наданий генератор даних (без змін) |
| `build_graph.py` | побудова графу graph.ttl для 1-го завдання|
| `q1.rq`, `q2.rq`, `q3.rq` | SPARQL-запити для 2-го завдання|
| `run_queries.py` | скрипт для виконання SPARQL-запитів |

## Запуск
### Завдання 1.
```
python gen_data.py --seed 27
python build_graph.py flights.csv params.json graph.ttl
```
### Завдання 2. Wikidata

```
pip install requests
python run_queries.py
```
