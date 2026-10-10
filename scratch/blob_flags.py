#!/usr/bin/env python3
"""Show which extract-utils flags each reference tree uses in proprietary-files.txt."""

import glob
import os
import re
import sys

TREES = [
    ('Z2577 (ours)', '/home/andrei/Downloads/Trees/device_nubia_Z2577'),
    ('tecno_KJ5', '/home/andrei/romtools/WORK/rom/refs/android_device_tecno_KJ5'),
    ('tecno_LG8n', '/home/andrei/romtools/WORK/rom/refs/android_device_tecno_LG8n'),
    ('mt6768-common', '/home/andrei/romtools/WORK/rom/refs/android_device_xiaomi_mt6768-common'),
    ('infinix_X6837', '/home/andrei/romtools/WORK/rom/refs/device_infinix_X6837'),
    ('retroid_pocket2plus', '/home/andrei/romtools/WORK/rom/refs/android_device_retroid_pocket2plus'),
    ('retroid_t310-common', '/home/andrei/romtools/WORK/rom/refs/android_device_retroid_t310-common'),
    ('rmx3939_Device', '/home/andrei/romtools/WORK/refs/rmx3939_Device'),
    ('sunfish', '/home/andrei/romtools/WORK/rom/refs/android_device_google_sunfish'),
]

FLAG = re.compile(r'(?<!\S)(-[A-Za-z]+(?::[^\s|]+)?)')


def analyse(name, path):
    listing = os.path.join(path, 'proprietary-files.txt')
    if not os.path.exists(listing):
        print(f'{name:22} no proprietary-files.txt at {path}')
        return
    flags = {}
    fixups = 0
    pinned_hashes = 0
    total = 0
    for line in open(listing):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        total += 1
        if '|' in line:
            fixups += 1
        rest = line.split('|', 1)[0]
        parts = rest.split(' ', 1)
        if len(parts) > 1:
            for flag in FLAG.findall(parts[1]):
                flags.setdefault(flag, []).append(parts[0])
        if re.search(r'\s-P\s+[0-9a-f]{64}', line):
            pinned_hashes += 1
    print(f'{name:22} lines={total:5}  fixup lines={fixups:4}  sha256 pins={pinned_hashes:3}')
    for flag in sorted(flags):
        sample = flags[flag][0]
        print(f'{"":22} {flag:10} x{len(flags[flag]):4}  e.g. {sample}')
    print()


def main():
    for name, path in TREES:
        analyse(name, path)
    hits = glob.glob('/home/andrei/romtools/WORK/**/extract_utils', recursive=True)
    print('extract-utils checkouts found:')
    for hit in hits[:10]:
        print(' ', hit)


if __name__ == '__main__':
    main()
