#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
VENDOR = HERE / '../../../vendor/nubia/Z2577'
VENDOR_BP = VENDOR / 'Android.bp'
BLOB_LIST = HERE / 'proprietary-files.txt'
PREFER = re.compile(r'^    prefer: true,\n', re.M)
SERVICE_SECTION = re.compile(r'^(service|on|import|subsys)\b')
SERVICE_LINE = re.compile(r'^\s*service\s+\S+')
USER_LINE = re.compile(r'^\s*user\s+')

DISPLACE = (
    'libwifi-hal',
    'camera.device@1.0-impl',
)

DROP_SHARED = {
    'android.hardware.graphics.mapper@4.0-impl-arm':
        ('libgralloctypes', 'libnativewindow'),
    'android.hardware.graphics.allocator@4.0-impl-arm':
        ('libgralloctypes', 'libnativewindow'),
    'libGLES_mali': (
        'libgralloctypes', 'libnativewindow',
        'android.hardware.graphics.common-V3-ndk',
    ),
    'android.hardware.neuralnetworks@aidl-service-armnn-gpu':
        ('libui', 'libnativewindow'),
}


def block_bounds(lines, name):
    """(name line, closing brace) of the module block called `name`."""
    for index, line in enumerate(lines):
        if line.strip() == f'name: "{name}",':
            end = index
            while end < len(lines) and lines[end].rstrip() != '}':
                end += 1
            return index, end
    return None, None


def drop_shared(lines, name, libs):
    """Remove named shared_libs entries from one module block."""
    name_line, end = block_bounds(lines, name)
    if name_line is None:
        raise SystemExit(f'no module named {name} in {VENDOR_BP}')
    names = {f'"{lib}",' for lib in libs}
    dropped = 0
    for index in range(end, name_line, -1):
        if lines[index].strip() in names:
            del lines[index]
            dropped += 1
    return dropped


def add_user_root():
    """Declare root on every shipped service block that leaves it out."""
    patched = 0
    for entry in BLOB_LIST.read_text().splitlines():
        entry = entry.strip()
        if not entry or entry.startswith('#'):
            continue
        path = entry.split('|')[0].split(';')[0].strip()
        if not path.endswith('.rc'):
            continue
        rc = VENDOR / 'proprietary' / path
        if not rc.is_file():
            continue
        lines = rc.read_text().splitlines(keepends=True)
        plain = [line.rstrip('\r\n') for line in lines]
        inserts = []
        index = 0
        while index < len(plain):
            if not SERVICE_LINE.match(plain[index]):
                index += 1
                continue
            end = index + 1
            while end < len(plain) and not SERVICE_SECTION.match(plain[end].strip()):
                end += 1
            block = plain[index:end]
            if not any(
                USER_LINE.match(line) for line in block
                if not line.lstrip().startswith('#')
            ):
                command_end = index
                while command_end < end and plain[command_end].rstrip().endswith('\\'):
                    command_end += 1
                inserts.append(command_end)
            index = end
        for position in reversed(inserts):
            lines.insert(position + 1, '    user root\n')
        if inserts:
            rc.write_text(''.join(lines))
            patched += len(inserts)
    return patched


def disable_elf_checks(lines):
    """Turn the ELF check off on every prebuilt.

    The check wants the soname to equal the installed name and every undefined
    symbol resolved by a declared lib. Stock was built against older platform
    ABIs and its names are what the device opens, neither of which a prebuilt
    can change. What is checkable without the platform built, the DT_NEEDED and
    soname halves, is tools/check_elf_prebuilts.py.
    """
    patched = 0
    at = 0
    while at < len(lines):
        if lines[at].strip() not in (
            'cc_prebuilt_library_shared {', 'cc_prebuilt_binary {'
        ):
            at += 1
            continue
        depth = 0
        end = at
        for end in range(at, len(lines)):
            depth += lines[end].count('{') - lines[end].count('}')
            if depth <= 0:
                break
        if not any('check_elf_files:' in line for line in lines[at:end]):
            insert_at = at + 1
            for index in range(at, end):
                if lines[index].strip().startswith('name:'):
                    insert_at = index + 1
                    break
            lines.insert(insert_at, '    check_elf_files: false,')
            patched += 1
            end += 1
        at = end + 1
    return patched


def add_prefer(lines, name):
    """Give one prebuilt the prefer flag, once."""
    name_line, end = block_bounds(lines, name)
    if name_line is None:
        raise SystemExit(f'no module named {name} in {VENDOR_BP}')
    if any('prefer:' in line for line in lines[name_line:end]):
        return False
    lines.insert(name_line + 1, '    prefer: true,')
    return True


subprocess.run(
    [str(HERE / 'extract-files.py'), '--regenerate_makefiles'],
    check=True,
)

bp = VENDOR_BP.resolve()
text, count = PREFER.subn('', bp.read_text())

lines = text.splitlines()
preferred = sum(add_prefer(lines, name) for name in DISPLACE)
unchecked = disable_elf_checks(lines)
dropped = sum(
    drop_shared(lines, name, libs) for name, libs in DROP_SHARED.items()
)
bp.write_text('\n'.join(lines) + '\n')
services = add_user_root()

if count:
    print(f'dropped {count} prefer: true lines from {bp}')
if preferred:
    print(f'{preferred} prefer flags put back in {bp}')
if dropped:
    print(f'{dropped} shared_libs entries dropped from {bp}')
if unchecked:
    print(f'{unchecked} ELF checks turned off in {bp}')
if services:
    print(f'user root added to {services} stock services')
