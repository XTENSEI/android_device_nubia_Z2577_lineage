#!/usr/bin/env python3
"""Parenthesis aware reader for the stock CIL policy.

Permissions and attributes are lists too, so every read goes through one
splitter that knows how deep it is.
"""

import re

RENAME = re.compile(r'^(.+?)_(\d+)_(\d+)$')


def split_top(text):
    """Split an s-expression body on whitespace at depth zero."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(''.join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        out.append(''.join(cur))
    return out


def parse(line):
    """Return (head, args) for one CIL line, or None."""
    line = line.strip()
    if not line or line.startswith(';') or not line.startswith('('):
        return None
    if not line.endswith(')'):
        return None
    head, _, rest = line[1:-1].partition(' ')
    args = split_top(rest.strip()) if rest else []
    return head, args


def inner(expr):
    """Strip one layer of parens from a nested list and split it."""
    expr = expr.strip()
    if expr.startswith('(') and expr.endswith(')'):
        expr = expr[1:-1]
    return split_top(expr)


def strip_version(name):
    """Drop a trailing _NN_NN from a type name. AOSP defines the mapping:
    private/compat/33.0/33.0.cil carries (typeattributeset init_33_0 (init))."""
    m = RENAME.match(name)
    if m and m.group(2).isdigit() and m.group(3).isdigit():
        return m.group(1)
    return name


def load(paths):
    """Yield (head, args, source path) for every statement."""
    for path in paths:
        with open(path, encoding='utf-8', errors='ignore') as fh:
            for line in fh:
                stmt = parse(line)
                if stmt:
                    yield stmt[0], stmt[1], path
