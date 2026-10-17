#!/usr/bin/env python3
"""Every module name a makefile defines twice.

kati rejects the second definition of a name (base_rules.mk:320) and stops, so a
build reports one name per cycle. Soong exports one block per module into
out/soong/Android-<product>.mk, which holds the whole set, so the whole list of
duplicates comes out of that one file in a second.

Usage: make_dupes.py <file or dir>... [--ours <path prefix>] [--selftest]
"""

import argparse
import glob
import os
import re
import sys
import tempfile

BLOCK_START = re.compile(r'^\s*include \$\(CLEAR_VARS\)')
BLOCK_END = re.compile(r'^\s*include \$\(BUILD_')
VARS = {
    'LOCAL_PATH': re.compile(r'^\s*LOCAL_PATH\s*:=\s*(\S+)\s*$'),
    'LOCAL_MODULE': re.compile(r'^\s*LOCAL_MODULE\s*:=\s*(\S+)\s*$'),
    'LOCAL_MODULE_CLASS': re.compile(r'^\s*LOCAL_MODULE_CLASS\s*:=\s*(\S+)\s*$'),
}


def read_blocks(path):
    """(class, name, LOCAL_PATH) for every module block in one makefile."""
    out = []
    current = {}
    with open(path, errors='ignore') as handle:
        for line in handle:
            if BLOCK_START.match(line):
                current = {}
                continue
            if BLOCK_END.match(line):
                out.append(current)
                current = {}
                continue
            for var, pattern in VARS.items():
                found = pattern.match(line)
                if found:
                    current[var] = found.group(1)
    entries = []
    for block in out:
        name = block.get('LOCAL_MODULE', '')
        if not name or '$' in name:
            continue
        entries.append((block.get('LOCAL_MODULE_CLASS', 'UNKNOWN'), name,
                        block.get('LOCAL_PATH')))
    return entries


def key(entry):
    return f'MODULE.TARGET.{entry[0]}.{entry[1]}'


def scan(paths, ours=None):
    """Duplicate keys, and how many module blocks were read."""
    seen = {}
    total = 0
    for path in paths:
        for entry in read_blocks(path):
            total += 1
            seen.setdefault(key(entry), []).append(entry)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if ours:
        dupes = {k: v for k, v in dupes.items()
                 if any((e[2] or '').startswith(ours) for e in v)}
    return dupes, total


def expand(args):
    paths = []
    for arg in args:
        if os.path.isdir(arg):
            paths.extend(sorted(glob.glob(os.path.join(arg, 'Android-*.mk'))))
        else:
            paths.append(arg)
    return paths


SELFTEST = """
include $(CLEAR_VARS)
LOCAL_PATH := vendor/nubia/Z2577
LOCAL_MODULE := awk
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := proprietary/vendor/bin/awk
include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk

include $(CLEAR_VARS)
LOCAL_PATH := external/one-true-awk
LOCAL_MODULE := awk
LOCAL_MODULE_CLASS := EXECUTABLES
include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk

include $(CLEAR_VARS)
LOCAL_PATH := vendor/nubia/Z2577
LOCAL_MODULE := sqc_daemon
LOCAL_MODULE_CLASS := EXECUTABLES
include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk
"""


def selftest():
    """The shape of the eleventh cycle: the stock awk against the platform's."""
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'Android-lineage_Z2577.mk')
        with open(path, 'w') as handle:
            handle.write(SELFTEST)
        dupes, total = scan([path])
        mine, _ = scan([path], ours='vendor/nubia/Z2577')
        other, _ = scan([path], ours='nothing/here')

    cases = (
        ('one duplicate among three blocks', len(dupes) == 1 and total == 3),
        ('keyed by class and name',
         'MODULE.TARGET.EXECUTABLES.awk' in dupes),
        ('both definers named',
         len(dupes.get('MODULE.TARGET.EXECUTABLES.awk', [])) == 2
         and {e[2] for e in dupes['MODULE.TARGET.EXECUTABLES.awk']}
         == {'vendor/nubia/Z2577', 'external/one-true-awk'}),
        ('--ours keeps the packages that are ours', len(mine) == 1),
        ('--ours drops the rest', not other),
    )
    for label, ok in cases:
        print(f'{"ok  " if ok else "FAIL"} {label}')
        bad += 0 if ok else 1
    print(f'{len(cases) - bad}/{len(cases)} cases')
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--ours', help='only names one of these packages defines')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    paths = expand(args.paths)
    if not paths:
        ap.error('no makefiles given; try out/soong')
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f'no such file: {missing[0]}', file=sys.stderr)
        return 2

    dupes, total = scan(paths, args.ours)
    for name in sorted(dupes):
        print(f'{name} defined {len(dupes[name])} times')
        for entry in dupes[name]:
            print(f'    {entry[2] or "?"}')
    print(f'\n{len(dupes)} duplicate names in {total} module blocks')
    return 1 if dupes else 0


if __name__ == '__main__':
    sys.exit(main())
