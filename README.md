# 🧪 Python Code Humanizer (`humanize.py`)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#requirements)
[![Code Style: Human-like](https://img.shields.io/badge/style-messy_human-orange.svg)](#)

> **Превращает идеально вылизанный ИИ-код в естественный, живой код обычного разработчика.**

Сгенерированный ChatGPT, Claude или GitHub Copilot код сразу выдаёт себя: безупречные длинные докстринги, идеальные PEP-8 пробелы вокруг всех бинарных операторов, шаблонные переменные (`processed_result`, `calculate_final_sum`) и комментарии к каждой очевидной строке.

`humanize.py` анализирует AST и токен-поток исходного Python-скрипта, аккуратно убирает искусственную «прилизанность» и сохраняет 100% работоспособность программы.

---

## 🎯 Что выдаёт код нейросетей и что делает скрипт

| Признак ИИ-кода | Что делает `humanize.py` |
| :--- | :--- |
| **Педантичные комментарии и докстринги** | Полностью вырезает комментарии и docstrings (с заменой на `pass`, если тело пустое). |
| **Слишком длинные имена переменных** | Сокращает переменные в естественные имена (`count` $\to$ `c`, `data_list` $\to$ `dl` или `d2l`). |
| **Идеальный машинный PEP-8** | Добавляет лёгкую хаотичность: убирает пробелы у `=`, операторов, запятых и скобок. |
| **Однородные абзацы** | Вставляет случайные пустые строки между логическими блоками. |
| **Риск поломать синтаксис** | Автоматически компилирует результат через встроенный `compile()` — в случае сбоя откатывает изменения форматирования. |

---

## ⚡ Пример «До / После»

### Исходный код (генерация ChatGPT / Copilot)
```python
def calculate_circle_properties(radius: float) -> tuple[float, float]:
    """
    Calculate the circumference and area of a circle given its radius.
    
    Args:
        radius (float): The radius of the circle.
    Returns:
        tuple[float, float]: Circumference and area.
    """
    pi_constant: float = 3.1415926535
    # Calculate circumference using 2 * pi * r formula
    total_circumference = 2 * pi_constant * radius
    # Calculate surface area
    total_area = pi_constant * (radius ** 2)
    return total_circumference, total_area
```

### После обработки `humanize.py`
```python
def calculate_circle_properties(r: float) -> tuple[float, float]:
    pc: float=3.1415926535
    tc = 2*pc * r

    ta = pc*(r**2)
    return tc,ta
```

---

## 🚀 Быстрый старт

### Требования
- Python **3.8** или новее.
- **Внешние библиотеки не требуются** — используются только стандартные модули (`ast`, `tokenize`, `argparse`, `random`).

### Установка
Склонируйте репозиторий или просто скопируйте `humanize.py` к себе в проект:

```bash
git clone https://github.com/your-username/python-humanizer.git
cd python-humanizer
```

---

## 🛠 Использование

### 1. Интерактивный режим (для PyCharm / VS Code)
Если запустить файл без аргументов (кнопкой **Run** в IDE или простым вызовом `python humanize.py`):
1. Скрипт вежливо запросит путь к файлу (или имя `.py` файла в текущей папке).
2. Выведет результат в консоль.
3. Создаст резервную копию оригинала `<file>.bak`.
4. Перезапишет исходный файл обработанным вариантом.

### 2. Запуск через терминал (CLI)

```bash
# Вывести результат в stdout:
python humanize.py my_script.py

# Сохранить в отдельный файл:
python humanize.py my_script.py -o humanized_script.py

# Зафиксировать seed для повторяемости результата:
python humanize.py my_script.py --seed 42 -o out.py

# Усилить хаос с пробелами (p=0.8) и пустыми строками:
python humanize.py my_script.py -p 0.8 --blank 0.25 -o out.py
```

---

## ⚙️ Параметры командной строки

| Флаг | Описание | По умолчанию |
| :--- | :--- | :--- |
| `input` | Путь к входному `.py` файлу. | *Обязательный* |
| `-o`, `--output` | Путь к файлу для сохранения результата. | `stdout` |
| `--seed INT` | Сид генератора псевдослучайных чисел для детерминированного вывода. | `None` |
| `-p FLOAT` | Вероятность схлопывания пробела вокруг операторов и знаков препинания `[0.0 - 1.0]`. | `0.5` |
| `--blank FLOAT` | Вероятность появления дополнительной пустой строки после стейтмента. | `0.1` |
| `--keep-docstrings` | Сохранять docstrings у модулей, классов и функций. | `False` |
| `--no-rename` | Отключить переименование переменных и локальных идентификаторов. | `False` |
| `--no-rename-args` | Оставить имена аргументов функций нетронутыми (важно для kwargs). | `False` |

---

## 🛡️ Безопасность и ограничения

Скрипт использует статический парсинг AST, поэтому бережно относится к архитектуре кода, но имеет ряд ограничений:

1. **Динамические ссылки:** Имена, которые читаются через `getattr(obj, "var_name")`, `globals()["var"]` или `eval()`, статически не переименовываются.
2. **Публичный API модуля:** Если функции вашего модуля вызываются из внешних файлов по именованным аргументам (`func(user_id=123)`), запускайте скрипт с флагом `--no-rename-args`.
3. **Классовые атрибуты:** Атрибуты верхнего уровня классов и поля `dataclass` **защищены** и не переименовываются, чтобы не ломать логику моделей.
4. **f-строки:** На Python версиях ниже 3.12 переменные внутри f-строк не затрагиваются переименованием во избежание повреждения токенов.

---

## 📄 Лицензия

Распространяется под лицензией [MIT](LICENSE).
