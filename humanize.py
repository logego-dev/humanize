
# !/usr/bin/env python3
"""
humanize.py - делает аккуратный питон-код "неаккуратным", чтобы он выглядел написанным вручную.

Что делает:
  1. Удаляет комментарии (и докстринги, если не указан --keep-docstrings).
  2. Переименовывает переменные и аргументы функций в короткие "человеческие" имена:
        count -> c,  count_output -> c2o,  MAX_SIZE -> M ...
  3. Случайно убирает/добавляет пробелы вокруг =, операторов, после запятых и двоеточий,
     возле скобок:  x = 5 -> x=5,  def f(a, b): -> def f(a,b) :,  foo(x) -> foo (x)
  4. Иногда вставляет пустые строки.
  5. В конце проверяет, что результат компилируется. Если нет - отдаёт версию без шага 3-4.

Использование:
    Запуск из PyCharm (без аргументов): скрипт спросит имя файла (из этой же папки)
    или полный путь, напечатает результат и перезапишет файл на месте
    (оригинал сохраняется рядом как <имя>.bak).

    Из командной строки:
    python humanize.py input.py -o output.py
    python humanize.py input.py --seed 42 -p 0.6 --blank 0.15

Ограничения (переименование делается статически):
  - имена, которые используются через строки (getattr, globals(), **{'name': 1}, eval) не отслеживаются;
  - если файл импортируется другими модулями и они вызывают функции по именам аргументов - 
    используйте --no-rename-args (имена, которые где-то встречаются как name=..., и так не трогаются);
  - публичные глобальные переменные тоже переименовываются.
"""
import argparse
import ast
import builtins
import io
import keyword
import os
import random
import re
import sys
import tokenize

T = tokenize
STRUCTURAL = {T.INDENT, T.DEDENT, T.NEWLINE, T.NL, T.COMMENT, T.ENDMARKER}
FSTART = getattr(T, "FSTRING_START", None)
FEND = getattr(T, "FSTRING_END", None)
FMID = getattr(T, "FSTRING_MIDDLE", None)

SOFT = {"match", "case", "type"}
LITERALS = {"None", "True", "False"}
BINOPS = {
    "=", "+=", "-=", "*=", "/=", "//=", "%=", "**=", ">>=", "<<=", "&=", "|=", "^=", "@=", ":=",
    "==", "!=", "<", ">", "<=", ">=", "+", "-", "*", "/", "//", "%", "**", "@", "&", "|", "^",
    "<<", ">>", "->",
}
SPACEABLE = {"=", "==", "!=", "<", ">", "<=", ">=", "+=", "-=", "*=", "/=", "+", "-", "*", "/", "%"}
OPEN = {"(", "[", "{"}
CLOSE = {")", "]", "}"}
KW_BEFORE_PAREN = {"if", "elif", "while", "return", "in", "and", "or", "not", "assert"}


# ---------------------------------------------------------------- helpers

def get_tokens(src):
    return list(tokenize.generate_tokens(io.StringIO(src).readline))


def get_lines(src):
    return io.StringIO(src).readlines()


def line_offsets(src):
    offs = [0]
    for line in get_lines(src):
        offs.append(offs[-1] + len(line))
    return offs


def is_kw(tok):
    if tok.type != T.NAME:
        return False
    s = tok.string
    return (keyword.iskeyword(s) and s not in LITERALS) or s in SOFT


def eol_of(line):
    return line[len(line.rstrip("\r\n")):]


# ---------------------------------------------------------------- 1. comments / docstrings

def strip_comments(src):
    lines = get_lines(src)
    kill, cut = set(), {}
    for t in get_tokens(src):
        if t.type == T.COMMENT:
            row, col = t.start
            if lines[row - 1][:col].strip() == "":
                kill.add(row - 1)
            else:
                cut[row - 1] = col
    out = []
    for i, line in enumerate(lines):
        if i in kill:
            continue
        if i in cut:
            line = line[:cut[i]].rstrip() + eol_of(line)
        out.append(line)
    return "".join(out)


def strip_docstrings(src):
    tree = ast.parse(src)
    lines = get_lines(src)
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                targets.append((b[0], len(b) == 1))
    for stmt, only in sorted(targets, key=lambda x: -x[0].lineno):
        a, b = stmt.lineno - 1, stmt.end_lineno
        # докстринг должен занимать строки целиком
        if lines[a].encode()[:stmt.col_offset].strip():
            continue
        if lines[b - 1].encode()[stmt.end_col_offset:].strip():
            continue
        if only:
            indent = re.match(r"\s*", lines[a]).group()
            lines[a:b] = [indent + "pass" + (eol_of(lines[b - 1]) or "\n")]
        else:
            del lines[a:b]
    return "".join(lines)


# ---------------------------------------------------------------- 2. rename

def class_scope_names(cls):
    """Имена, присвоенные прямо в теле класса (поля dataclass, атрибуты класса) - их нельзя трогать."""
    out, stack = set(), list(cls.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        stack.extend(ast.iter_child_nodes(n))
    return out


def make_name(name, used, rng):
    up = name.isupper()
    parts = [x for x in name.split("_") if x] or ["v"]
    w = parts[0]
    if len(parts) == 1:
        cands = [w[0], w[:2], w[0] + w[-1], w[0] + w[1:2] + w[-1]]
    else:
        cands = [w[0] + str(len(parts)) + parts[-1][0],
                 "".join(x[0] for x in parts),
                 w[0] + parts[-1][0]]
    cands = [c.upper() if up else c.lower() for c in cands]

    def ok(c):
        return c.isidentifier() and not keyword.iskeyword(c) and c not in used

    free = []
    for c in cands:
        if ok(c) and c not in free:
            free.append(c)
    if free:
        return free[0] if rng.random() < 0.6 else rng.choice(free)
    base = w[0] if w[0].isidentifier() else "v"
    base = base.upper() if up else base.lower()
    n = 1
    while not ok(f"{base}{n}"):
        n += 1
    return f"{base}{n}"


def rename_identifiers(src, rng, rename_args=True):
    tree = ast.parse(src)
    cand = set()
    excl = set(dir(builtins)) | set(keyword.kwlist) | set(keyword.softkwlist) | {"self", "cls"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            cand.add(node.id)
        elif isinstance(node, ast.arg):
            if rename_args:
                cand.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            cand.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            cand.update(node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            excl.add(node.name)
        elif isinstance(node, ast.ClassDef):
            excl.add(node.name)
            excl |= class_scope_names(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                excl.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.keyword) and node.arg:
            excl.add(node.arg)
        elif isinstance(node, ast.JoinedStr) and sys.version_info < (3, 12):
            # до 3.12 f-строка - один токен, переименовать внутри нельзя
            for n in ast.walk(node):
                if isinstance(n, ast.Name):
                    excl.add(n.id)
        elif hasattr(ast, "MatchAs") and isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            cand.add(node.name)
        elif hasattr(ast, "MatchMapping") and isinstance(node, ast.MatchMapping) and node.rest:
            cand.add(node.rest)

    toks = get_tokens(src)
    cand = {n for n in cand
            if n not in excl and len(n) > 2 and not (n.startswith("__") and n.endswith("__"))}
    used = {t.string for t in toks if t.type == T.NAME} | excl

    order, seen = [], set()
    for t in toks:
        if t.type == T.NAME and t.string in cand and t.string not in seen:
            seen.add(t.string)
            order.append(t.string)
    mapping = {}
    for n in order:
        new = make_name(n, used, rng)
        used.add(new)
        mapping[n] = new

    offs = line_offsets(src)
    edits, prev_sig = [], None
    for t in toks:
        if t.type in (T.NL, T.COMMENT):
            continue
        if (t.type == T.NAME and t.string in mapping
                and not (prev_sig is not None and prev_sig.string == ".")):
            s = offs[t.start[0] - 1] + t.start[1]
            e = offs[t.end[0] - 1] + t.end[1]
            edits.append((s, e, mapping[t.string]))
        prev_sig = t
    for s, e, new in reversed(edits):
        src = src[:s] + new + src[e:]
    return src


# ---------------------------------------------------------------- 3. whitespace jitter

def pick_gap(prev, tok, nxt, gap, rng, p):
    """Вернуть новый пробел между prev и tok ('' / ' ') или None, если менять не надо."""
    ps, ts = prev.string, tok.string
    has = gap != ""
    r = rng.random
    prev_kw, tok_kw = is_kw(prev), is_kw(tok)

    # пробел ПЕРЕД оператором:  a = b  ->  a= b / a =b / a=b
    if tok.type == T.OP and ts in BINOPS:
        if has and not prev_kw:
            return "" if r() < p else None
        if (not has and ts in SPACEABLE
                and (prev.type in (T.NUMBER, T.STRING) or (prev.type == T.NAME and not prev_kw) or ps in CLOSE)):
            return " " if r() < 0.06 else None
        return None

    # пробел ПОСЛЕ оператора
    if prev.type == T.OP and ps in BINOPS:
        if has and not tok_kw:
            return "" if r() < p else None
        return None

    # после запятой
    if ps == ",":
        if has and not tok_kw:
            return "" if r() < p * 0.7 else None
        return None

    # перед двоеточием в конце строки:  def f(): -> def f() :
    if ts == ":" and not has:
        if nxt is not None and nxt.type == T.NEWLINE and r() < 0.10:
            return " "
        return None
    # после двоеточия (словари, аннотации, однострочники)
    if ps == ":" and has and not tok_kw:
        return "" if r() < p * 0.6 else None

    # возле скобок:  ( a, b )
    if ps in OPEN and not has and ts not in CLOSE:
        return " " if r() < 0.05 else None
    if ts in CLOSE and not has and ps not in OPEN:
        return " " if r() < 0.05 else None
    if ts == "(":
        if not has and prev.type == T.NAME and not prev_kw:
            return " " if r() < 0.04 else None  # print (x)
        if has and prev_kw and ps in KW_BEFORE_PAREN:
            return "" if r() < p * 0.5 else None  # if(x):
    return None


def jitter(src, rng, p, blank_p):
    toks = get_tokens(src)
    offs = line_offsets(src)
    out, last, depth = [], 0, 0
    prev, logical_first = None, None
    skip_next = {"else", "elif", "except", "finally"}

    for i, tok in enumerate(toks):
        s = offs[tok.start[0] - 1] + tok.start[1]
        e = offs[tok.end[0] - 1] + tok.end[1]
        gap = src[last:s]
        in_f = depth > 0

        if (prev is not None and not in_f
                and gap.strip(" ") == ""
                and tok.start[0] == prev.end[0]
                and tok.type not in STRUCTURAL and prev.type not in STRUCTURAL
                and tok.type != FMID and prev.type != FMID):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            new = pick_gap(prev, tok, nxt, gap, rng, p)
            if new is not None:
                gap = new

        out.append(gap)
        out.append(src[s:e])
        last = e

        if tok.type == FSTART:
            depth += 1
        elif tok.type == FEND:
            depth -= 1

        if tok.type not in STRUCTURAL and logical_first is None:
            logical_first = tok.string

        if tok.type == T.NEWLINE:
            if (tok.string.endswith("\n") and depth == 0 and prev is not None
                    and prev.string != ":" and logical_first != "@"
                    and rng.random() < blank_p):
                j = i + 1
                while j < len(toks) and toks[j].type in (T.NL, T.DEDENT, T.INDENT, T.COMMENT):
                    j += 1
                if j < len(toks) and toks[j].string not in skip_next:
                    out.append("\n")
            logical_first = None

        if tok.type not in (T.NL, T.COMMENT):
            prev = tok

    out.append(src[last:])
    return "".join(out)


# ---------------------------------------------------------------- main

def humanize(src, seed=None, p=0.5, blank_p=0.1, keep_docstrings=False,
             rename=True, rename_args=True):
    rng = random.Random(seed)
    ast.parse(src)  # сразу падаем, если исходник невалиден
    src = strip_comments(src)
    if not keep_docstrings:
        src = strip_docstrings(src)
    if rename:
        src = rename_identifiers(src, rng, rename_args)
    styled = jitter(src, rng, p, blank_p)
    try:
        compile(styled, "<humanized>", "exec")
    except SyntaxError as exc:
        print(f"[warn] после правки пробелов код не компилируется ({exc}), оставляю без неё",
              file=sys.stderr)
        styled = src
    return styled


def resolve_path(raw):
    """Найти файл: как введён, рядом со скриптом или в текущей папке (в т.ч. без .py)."""
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (raw, os.path.join(here, raw), os.path.join(os.getcwd(), raw)):
        for cand in (base, base + ".py"):
            if os.path.isfile(cand):
                return os.path.abspath(cand)
    return None


def interactive():
    raw = input("Имя файла (если он в этой же папке) или полный путь: ")
    path = resolve_path(raw)
    if path is None:
        print(f"Файл не найден: {raw!r}")
        return
    with open(path, encoding="utf-8") as f:
        src = f.read()
    try:
        res = humanize(src)
    except SyntaxError as exc:
        print(f"В исходном файле синтаксическая ошибка, ничего не изменено: {exc}")
        return

    print("=" * 20, "РЕЗУЛЬТАТ", "=" * 20)
    print(res)
    print("=" * 50)

    bak = path + ".bak"
    if not os.path.exists(bak):
        with open(bak, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"Оригинал сохранён: {bak}")
    else:
        print(f"Резервная копия уже есть ({bak}), не перезаписываю её")
    with open(path, "w", encoding="utf-8") as f:
        f.write(res)
    print(f"Файл заменён: {path}")


def main():
    if len(sys.argv) == 1:  # запуск без аргументов (например, кнопкой Run в PyCharm)
        interactive()
        return

    ap = argparse.ArgumentParser(description="Сделать питон-код похожим на написанный вручную.")
    ap.add_argument("input", help="входной .py файл")
    ap.add_argument("-o", "--output", help="выходной файл (по умолчанию - stdout)")
    ap.add_argument("--seed", type=int, help="seed для воспроизводимости")
    ap.add_argument("-p", type=float, default=0.5, help="вероятность убрать пробел (по умолчанию 0.5)")
    ap.add_argument("--blank", type=float, default=0.1, help="вероятность пустой строки после оператора")
    ap.add_argument("--keep-docstrings", action="store_true", help="не удалять докстринги")
    ap.add_argument("--no-rename", action="store_true", help="не переименовывать переменные")
    ap.add_argument("--no-rename-args", action="store_true", help="не переименовывать аргументы функций")
    a = ap.parse_args()

    with open(a.input, encoding="utf-8") as f:
        src = f.read()
    res = humanize(src, a.seed, a.p, a.blank, a.keep_docstrings,
                   rename=not a.no_rename, rename_args=not a.no_rename_args)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(res)
    else:
        sys.stdout.write(res)


if __name__ == "__main__":
    main()