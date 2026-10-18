#!/usr/bin/env python3
"""Every module name a makefile defines twice, and every install path two
modules write.

kati rejects the second definition of a name (base_rules.mk:320) and the second
recipe for one target, and stops, so a build reports one per cycle. Soong
exports one block per module into out/soong/Android-<product>.mk and one per
installed module into out/soong/installs-<product>.mk, which hold the whole set,
so the whole list comes out of those files in a second.

Usage: make_dupes.py <file or dir>... [--ours <path prefix>] [--tree <root>]
                     [--paths] [--selftest]

--paths reads an installs-*.mk and reports two modules writing one file, which
is the other way kati stops: a rename keeps the name apart and still leaves both
recipes on one target. It is the default for a file named installs-*.mk.

With --tree the report also says what to do per name: whether the platform
module's own directory declares a <name>_vendor, which is the copy to take
instead of the stock one, or that ours needs a name of its own.
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


def blocks(path):
    """(name, body) for every module block in an Android.bp."""
    lines = open(path, errors='ignore').read().splitlines()
    out = []
    i = 0
    while i < len(lines):
        if not re.match(r'^[a-z_0-9]+\s*\{\s*$', lines[i]):
            i += 1
            continue
        depth = 1
        body = []
        i += 1
        while i < len(lines) and depth > 0:
            depth += lines[i].count('{') - lines[i].count('}')
            body.append(lines[i])
            i += 1
        text = '\n'.join(body)
        found = re.search(r'^\s*name:\s*"([^"]+)"', text, re.M)
        if found:
            out.append((found.group(1), text))
    return out


def platform_module(tree, local_path, name):
    """What the platform's own declaration says: (has _vendor copy, is vendor)."""
    vendor_copy = False
    if not tree or not local_path:
        return vendor_copy, False
    for fname in ('Android.bp', 'Android.mk'):
        path = os.path.join(tree, local_path, fname)
        if not os.path.exists(path):
            continue
        if fname == 'Android.bp':
            for other, body in blocks(path):
                if other == name + '_vendor':
                    vendor_copy = True
                if other != name:
                    continue
                if (re.search(r'(proprietary|vendor|vendor_available):\s*true',
                              body)):
                    return vendor_copy, True
        else:
            text = open(path, errors='ignore').read()
            if re.search(rf'LOCAL_MODULE\s*:=\s*{re.escape(name)}_vendor\b',
                         text):
                vendor_copy = True
    return vendor_copy, False


def advice(cls, name, vendor_copy, is_vendor):
    """What to do about one duplicate, from the class and the platform side."""
    if is_vendor:
        return ('both sides are vendor, so the platform copy wins and ours is '
                'not installed: nothing to do')
    if cls == 'SHARED_LIBRARIES':
        if vendor_copy:
            return f'drop the blob and add {name}_vendor to PRODUCT_PACKAGES'
        return (f'rename ours with ;MODULE_SUFFIX=_vendor and repoint the '
                f'dependants in lib_fixups')
    if cls == 'EXECUTABLES':
        if vendor_copy:
            return f'drop the blob and add {name}_vendor to PRODUCT_PACKAGES'
        return 'rename ours with ;MODULE=<name>_suffix, stem keeps the file'
    if cls == 'ETC':
        return 'install the stock file with ;MAKE_COPY_RULE_ONLY'
    return 'no rule for this class yet'


def scan(paths, ours=None):
    """Duplicate keys, and how many module blocks were read."""
    seen = {}
    total = 0
    for path in paths:
        for entry in read_blocks(path):
            total += 1
            seen.setdefault(key(entry), []).append(entry)
    dupes = {}
    for name, group in seen.items():
        # one module written once per arch is not two modules: same class, name
        # and package, so keep the distinct definers only
        distinct = sorted({(e[0], e[1], e[2]) for e in group})
        if len(distinct) > 1:
            dupes[name] = distinct
    if ours:
        dupes = {k: v for k, v in dupes.items()
                 if any((e[2] or '').startswith(ours) for e in v)
                 and any(not (e[2] or '').startswith(ours) for e in v)}
    return dupes, total


INSTALL_VARS = {
    'LOCAL_MODULE': VARS['LOCAL_MODULE'],
    'LOCAL_MODULE_CLASS': VARS['LOCAL_MODULE_CLASS'],
    'LOCAL_MODULE_PATH': re.compile(r'^\s*LOCAL_MODULE_PATH\s*:=\s*(\S+)\s*$'),
    'LOCAL_INSTALLED_MODULE_STEM':
        re.compile(r'^\s*LOCAL_INSTALLED_MODULE_STEM\s*:=\s*(\S+)\s*$'),
    'LOCAL_MODULE_SUFFIX':
        re.compile(r'^\s*LOCAL_MODULE_SUFFIX\s*:=\s*(\S+)\s*$'),
}
PRODUCT_OUT = re.compile(r'^out/target/product/[^/]+/')


def read_install_blocks(path):
    """(installed path, class, name) for every block in an installs makefile."""
    out = []
    current = {}
    with open(path, errors='ignore') as handle:
        for line in handle:
            if BLOCK_START.match(line):
                current = {}
                continue
            if BLOCK_END.match(line):
                entries = install_entry(current)
                if entries:
                    out.append(entries)
                current = {}
                continue
            for var, pattern in INSTALL_VARS.items():
                found = pattern.match(line)
                if found:
                    current[var] = found.group(1)
    return out


def install_entry(block):
    """One block to (path, class, name), or None when it installs no file."""
    name = block.get('LOCAL_MODULE', '')
    where = block.get('LOCAL_MODULE_PATH', '')
    if not name or not where or '$' in name or '$' in where:
        return None
    stem = block.get('LOCAL_INSTALLED_MODULE_STEM')
    if not stem:
        stem = name + block.get('LOCAL_MODULE_SUFFIX', '')
    if '$' in stem:
        return None
    target = PRODUCT_OUT.sub('', where).rstrip('/') + '/' + stem
    return target, block.get('LOCAL_MODULE_CLASS', 'UNKNOWN'), name


def scan_paths(paths, ours=None):
    """Install paths more than one module writes, and how many were read."""
    seen = {}
    total = 0
    for path in paths:
        for entry in read_install_blocks(path):
            total += 1
            seen.setdefault(entry[0], set()).add((entry[1], entry[2]))
    dupes = {}
    for target, group in seen.items():
        # one module writes one path from every arch variant it has
        if len({name for _, name in group}) > 1:
            dupes[target] = sorted(group)
    if ours:
        dupes = {k: v for k, v in dupes.items() if len(v) == 2}
    return dupes, total


def expand(args, installs=False):
    paths = []
    for arg in args:
        if os.path.isdir(arg):
            pattern = 'installs-*.mk' if installs else 'Android-*.mk'
            paths.extend(sorted(glob.glob(os.path.join(arg, pattern))))
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


INSTALLS_SELFTEST = """
include $(CLEAR_VARS)
LOCAL_PATH := device/nubia/Z2577
LOCAL_MODULE := android.hardware.wifi.hostapd.xml_vendor
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_PATH := out/target/product/Z2577/vendor/etc/vintf/manifest
LOCAL_INSTALLED_MODULE_STEM := android.hardware.wifi.hostapd.xml
include $(BUILD_SYSTEM)/soong_etx_xml.mk

include $(CLEAR_VARS)
LOCAL_PATH := external/wpa_supplicant_8/hostapd
LOCAL_MODULE := android.hardware.wifi.hostapd.xml
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_PATH := out/target/product/Z2577/vendor/etc/vintf/manifest
LOCAL_INSTALLED_MODULE_STEM := android.hardware.wifi.hostapd.xml
include $(BUILD_SYSTEM)/soong_etx_xml.mk

include $(CLEAR_VARS)
LOCAL_PATH := vendor/nubia/Z2577
LOCAL_MODULE := ai_engine-default.xml
LOCAL_MODULE_PATH := out/target/product/Z2577/vendor/etc/vintf/manifest
include $(BUILD_SYSTEM)/soong_etx_xml.mk

include $(CLEAR_VARS)
LOCAL_PATH := vendor/nubia/Z2577
LOCAL_MODULE := libboth
LOCAL_MODULE_CLASS := SHARED_LIBRARIES
LOCAL_MODULE_PATH := out/target/product/Z2577/vendor/lib64
LOCAL_MODULE_SUFFIX := .so
include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk

include $(CLEAR_VARS)
LOCAL_PATH := vendor/nubia/Z2577
LOCAL_MODULE := libboth
LOCAL_MODULE_CLASS := SHARED_LIBRARIES
LOCAL_MODULE_PATH := out/target/product/Z2577/vendor/lib64
LOCAL_MODULE_SUFFIX := .so
include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk
"""


def selftest():
    """The shape of the eleventh cycle: the stock awk against the platform's."""
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'Android-lineage_Z2577.mk')
        with open(path, 'w') as handle:
            handle.write(SELFTEST)
        with open(os.path.join(tmp, 'multi.mk'), 'w') as handle:
            for arch in ('android_arm', 'android_arm64'):
                handle.write('include $(CLEAR_VARS)\n'
                             'LOCAL_PATH := vendor/nubia/Z2577\n'
                             'LOCAL_MODULE := libboth\n'
                             'LOCAL_MODULE_CLASS := SHARED_LIBRARIES\n'
                             f'LOCAL_MULTILIB := {arch}\n'
                             'include $(BUILD_SYSTEM)/soong_cc_rust_prebuilt.mk\n')
        dupes, total = scan([path])
        mine, _ = scan([path], ours='vendor/nubia/Z2577')
        other, _ = scan([path], ours='nothing/here')
        platform = os.path.join(tmp, 'external/one-true-awk')
        os.makedirs(platform)
        with open(os.path.join(platform, 'Android.bp'), 'w') as handle:
            handle.write('cc_binary {\n    name: "awk_vendor",\n}\n'
                         'cc_library {\n    name: "systemonly",\n}\n'
                         'cc_library_shared {\n    name: "owned",\n'
                         '    proprietary: true,\n}\n')
        with_vendor = platform_module(tmp, 'external/one-true-awk', 'awk')
        without = platform_module(tmp, 'external/one-true-awk', 'sqc_daemon')
        owned = platform_module(tmp, 'external/one-true-awk', 'owned')
        multi, _ = scan([os.path.join(tmp, 'multi.mk')])
        installs_path = os.path.join(tmp, 'installs-lineage_Z2577.mk')
        with open(installs_path, 'w') as handle:
            handle.write(INSTALLS_SELFTEST)
        by_path, read = scan_paths([installs_path])
        alone, _ = scan_paths([installs_path], ours='vendor/nubia/Z2577')
        chosen = expand([installs_path])

    fragment = 'vendor/etc/vintf/manifest/android.hardware.wifi.hostapd.xml'
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
        ('a platform _vendor is found in its own directory',
         with_vendor == (True, False)),
        ('and only for the name it declares', without == (False, False)),
        ('a proprietary module is vendor, so ours is hidden',
         owned == (False, True)),
        ('the advice follows the class and the platform side',
         'PRODUCT_PACKAGES' in advice('EXECUTABLES', 'awk', True, False)
         and 'lib_fixups' in advice('SHARED_LIBRARIES', 'libx', False, False)
         and 'MAKE_COPY_RULE_ONLY' in advice('ETC', 'x.xml', False, False)
         and 'nothing to do' in advice('SHARED_LIBRARIES', 'libx', False, True)),
        ('one module written once per arch is not a duplicate', not multi),
        ('one install path written by two modules is found',
         list(by_path) == [fragment] and read == 5),
        ('both producers are named with their class',
         by_path.get(fragment) == [
             ('ETC', 'android.hardware.wifi.hostapd.xml'),
             ('ETC', 'android.hardware.wifi.hostapd.xml_vendor')]),
        ('a path one module writes is not reported',
         len(by_path) == 1),
        ('--ours keeps the path ours takes part in',
         list(alone) == [fragment]),
        ('an installs file is read without being told',
         chosen == [installs_path]),
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
    ap.add_argument('--tree', help='android tree, to read the platform side')
    ap.add_argument('--paths', action='store_true',
                    help='read an installs-*.mk: one file written twice')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    if args.paths or any(os.path.basename(p).startswith('installs-')
                         for p in args.paths):
        return report_paths(args)

    paths = expand(args.paths)
    if not paths:
        ap.error('no makefiles given; try out/soong')
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f'no such file: {missing[0]}', file=sys.stderr)
        return 2

    dupes, total = scan(paths, args.ours)
    for name in sorted(dupes):
        entries = dupes[name]
        print(f'{name} defined {len(entries)} times')
        for entry in entries:
            print(f'    {entry[2] or "?"}')
        if args.tree:
            cls, mod = entries[0][0], entries[0][1]
            other = [e for e in entries
                     if not (e[2] or '').startswith(args.ours or '\0')]
            named = [platform_module(args.tree, e[2], mod) for e in other]
            vendor_copy = any(copy for copy, _ in named)
            is_vendor = any(vendor for _, vendor in named)
            print(f'    {advice(cls, mod, vendor_copy, is_vendor)}')
    print(f'\n{len(dupes)} duplicate names in {total} module blocks')
    return 1 if dupes else 0


def report_paths(args):
    """The other kati stop: one installed file, two modules writing it."""
    paths = expand(args.paths, installs=True)
    if not paths:
        print('no installs makefile given', file=sys.stderr)
        return 2
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f'no such file: {missing[0]}', file=sys.stderr)
        return 2

    dupes, total = scan_paths(paths, args.ours)
    for target in sorted(dupes):
        print(f'{target} written by {len(dupes[target])} modules')
        for cls, name in dupes[target]:
            print(f'    {name} ({cls})')
    print(f'\n{len(dupes)} install paths written twice in {total} modules')
    return 1 if dupes else 0


if __name__ == '__main__':
    sys.exit(main())
