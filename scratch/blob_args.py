#!/usr/bin/env python3
"""Report the proprietary-files.txt arg and pin usage of every reference tree."""

import os
import re
from collections import Counter

TREES = [
    ('Z2577 (ours)', '/home/andrei/Downloads/Trees/device_nubia_Z2577'),
    ('tecno_KJ5', '/home/andrei/romtools/WORK/rom/refs/android_device_tecno_KJ5'),
    ('tecno_LG8n', '/home/andrei/romtools/WORK/rom/refs/android_device_tecno_LG8n'),
    ('mt6768-common', '/home/andrei/romtools/WORK/rom/refs/android_device_xiaomi_mt6768-common'),
    ('infinix_X6837', '/home/andrei/romtools/WORK/rom/refs/device_infinix_X6837'),
    ('retroid_pocket2plus', '/home/andrei/romtools/WORK/rom/refs/android_device_retroid_pocket2plus'),
    ('rmx3939_Device (Unisoc)', '/home/andrei/romtools/WORK/refs/rmx3939_Device'),
    ('P671L', '/home/andrei/romtools/WORK/refs/P671L'),
    ('p65', '/home/andrei/romtools/WORK/refs/p65'),
    ('X668C', '/home/andrei/romtools/WORK/refs/X668C'),
]

ARGS = ['AB', 'CERTIFICATE', 'BOOT_JAR', 'DUMMY_SHARED_LIB', 'EXTRACT_ONLY',
        'MAKE_COPY_RULE', 'MAKE_COPY_RULE_ONLY', 'MODULE', 'MODULE_SUFFIX',
        'DISABLE_CHECKELF', 'DISABLE_DEPS', 'FIX_SONAME', 'FIX_XML',
        'STRIP_DEBUG_SECTIONS', 'OVERRIDES', 'PRESIGNED', 'REQUIRED',
        'SKIPAPKCHECKS', 'SYMLINK', 'TRYSRCFIRST', 'FILEGROUP',
        'RECOVERY_AVAILABLE']
ARG_RE = re.compile(r';(' + '|'.join(ARGS) + r')(?==|;|$|\|)', re.M)
HASH_RE = re.compile(r'\|[0-9a-f]{40,64}')


def analyse(name, path):
    listing = os.path.join(path, 'proprietary-files.txt')
    if not os.path.exists(listing):
        print(f'{name:24} no proprietary-files.txt')
        return
    text = open(listing, encoding='utf-8', errors='replace').read()
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
    args = Counter(ARG_RE.findall(text))
    pins = len(HASH_RE.findall(text))
    packed = sum(1 for l in lines if l.startswith('-'))
    dst = sum(1 for l in lines if ':' in l.split(';')[0].split('|')[0])
    sections = sum(1 for l in text.splitlines() if l.startswith('#'))
    print(f'{name:24} blobs={len(lines):5} sections={sections:3} pins={pins:4} '
          f'dash={packed:4} src:dst={dst:4}')
    if args:
        for arg, count in args.most_common():
            example = next((l for l in lines if f';{arg}' in l), '')
            print(f'{"":24} ;{arg:22} x{count:4}  {example[:78]}')
    print()


if __name__ == '__main__':
    for name, path in TREES:
        analyse(name, path)
