#!/usr/bin/env python3
"""Check the tree sepolicy against itself and against the platform.

Unique types, every name a rule or a label mentions resolved, lines shaped like
policy. The platform namespace is plat_pub_versioned.cil plus the plat_vendor
sources compiled into vendor policy alongside ours.
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cil import load, strip_version  # noqa: E402
import genpolicy as gp  # noqa: E402

RULE = re.compile(r'^(allow|dontaudit|auditallow)\s+(\S+)\s+(\S+):(\S+)')
XPERM = re.compile(r'^allowxperm\s+(\S+)\s+(\S+):(\S+)\s+ioctl')
TRANS = re.compile(r'^type_transition\s+(\S+)\s+(\S+):(\S+)\s+(.*)$')
DECL = re.compile(r'^type\s+([A-Za-z0-9_-]+)')
ATTRDECL = re.compile(r'^attribute\s+([A-Za-z0-9_-]+)')
TYPEATTR = re.compile(r'^typeattribute\s+(\S+)\s+(\S+)\s*;')
HALSERVER = re.compile(r'^hal_server_domain\(\s*([^,]+),\s*([^)]+)\)')
HALCLIENT = re.compile(r'^hal_client_domain\(\s*([^,]+),\s*([^)]+)\)')
DAEMON = re.compile(r'^init_daemon_domain\(\s*([^)]+)\)')
PROPMACRO = re.compile(r'^(vendor|system)_\w+_prop\(\s*([^)]+)\)')
MACRO_CALL = re.compile(r'^[A-Za-z0-9_-]+\(.*\)\s*;?$')
KEYWORDS = ('self', 'all')
MACROS = (HALSERVER, HALCLIENT, DAEMON, PROPMACRO)

CLASSES = None


def tree_te():
    out = []
    for part in ('public', 'vendor', 'system_ext', 'product', 'private'):
        base = os.path.join(gp.TREE, 'sepolicy', part)
        for dirpath, _dirs, files in os.walk(base):
            out.extend(os.path.join(dirpath, f) for f in sorted(files)
                       if f.endswith('.te'))
    return out


def main():
    public, plat_vendor = gp.build_platform()

    declared = defaultdict(list)     # name -> [file]
    referenced = defaultdict(list)   # name -> [where]
    problems = []

    for path in tree_te():
        rel = os.path.relpath(path, gp.TREE)
        for num, raw in enumerate(open(path, encoding='utf-8'), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            where = f'{rel}:{num}'
            m = DECL.match(line)
            if m:
                declared[m.group(1)].append(where)
                if not line.endswith(';'):
                    problems.append(f'{where}: declaration without ;')
                if line.count('{') != line.count('}'):
                    problems.append(f'{where}: unbalanced braces')
                continue
            m = ATTRDECL.match(line)
            if m:
                declared[m.group(1)].append(where)
                continue
            m = TYPEATTR.match(line)
            if m:
                referenced[m.group(1)].append(where)
                referenced[m.group(2)].append(where)
                continue
            m = HALSERVER.match(line) or HALCLIENT.match(line)
            if m:
                suffix = '_server' if line.startswith('hal_server') else '_client'
                referenced[m.group(1).strip()].append(where)
                referenced[m.group(2).strip() + suffix].append(where)
                continue
            m = DAEMON.match(line)
            if m:
                referenced[m.group(1).strip()].append(where)
                referenced[m.group(1).strip() + '_exec'].append(where)
                continue
            m = PROPMACRO.match(line)
            if m:
                declared[m.group(2).strip()].append(where)
                continue
            m = RULE.match(line)
            if m:
                referenced[m.group(2)].append(where)
                referenced[m.group(3)].append(where)
                if not line.endswith(';'):
                    problems.append(f'{where}: rule without ;')
                if line.count('{') != line.count('}'):
                    problems.append(f'{where}: unbalanced braces')
                continue
            m = XPERM.match(line)
            if m:
                referenced[m.group(1)].append(where)
                referenced[m.group(2)].append(where)
                if not line.endswith(';'):
                    problems.append(f'{where}: rule without ;')
                if line.count('{') != line.count('}'):
                    problems.append(f'{where}: unbalanced braces')
                continue
            m = TRANS.match(line)
            if m:
                referenced[m.group(1)].append(where)
                referenced[m.group(2)].append(where)
                rest = m.group(4)
                name = re.search(r'"([^"]+)"\s+([A-Za-z0-9_-]+)', rest)
                tail = name.group(2) if name else rest.rstrip(';').strip()
                referenced[tail].append(where)
                continue
            if MACRO_CALL.match(line):
                continue
            problems.append(f'{where}: unrecognised line: {line[:70]}')

    print(f'tree declarations: {len(declared)}')
    print(f'referenced names:  {len(referenced)}')

    # duplicate declarations, here and against the platform
    for name, places in sorted(declared.items()):
        if len(places) > 1:
            problems.append(f'declared twice: {name} in {places}')
        if name in public or name in plat_vendor:
            problems.append(f'declared here and by the platform: {name} '
                            f'({places[0]})')
    unresolved = sorted(n for n in referenced
                        if n not in declared and n not in public
                        and n not in plat_vendor and n not in KEYWORDS)
    for name in unresolved:
        problems.append(f'unresolved: {name} at {referenced[name][:3]}')

    # labels must point at a name the final policy has
    checked = 0
    for rel, kind in (('file_contexts', 'file'), ('genfs_contexts', 'genfs'),
                      ('property_contexts', 'property'),
                      ('service_contexts', 'service'),
                      ('hwservice_contexts', 'hwservice'),
                      ('vndservice_contexts', 'vndservice')):
        path = os.path.join(gp.TREE, 'sepolicy/vendor', rel)
        if not os.path.exists(path):
            continue
        for num, raw in enumerate(open(path, encoding='utf-8'), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            m = re.search(r'object_r:([A-Za-z0-9_-]+)', line)
            if not m:
                problems.append(f'{rel}:{num}: no label: {line[:60]}')
                continue
            checked += 1
            if m.group(1) not in declared and m.group(1) not in public \
                    and m.group(1) not in plat_vendor:
                problems.append(f'{rel}:{num}: unknown label {m.group(1)}')
            if kind == 'genfs':
                if not line.startswith('genfscon '):
                    problems.append(f'{rel}:{num}: not a genfscon: {line[:60]}')
            elif kind == 'file' and not line.startswith('/'):
                problems.append(f'{rel}:{num}: path does not start with /: '
                                f'{line[:60]}')

    print(f'labels checked: {checked}')

    # Names the platform declares but does not export to vendor. Informational.
    aosp_declared = set()
    for sub in ('public', 'private', 'vendor', 'system_ext', 'product'):
        base = os.path.join(gp.AOSP, sub)
        for dirpath, _dirs, files in os.walk(base):
            if 'compat' in dirpath or 'prebuilts' in dirpath:
                continue
            for fname in files:
                if not fname.endswith('.te'):
                    continue
                text = open(os.path.join(dirpath, fname), encoding='utf-8',
                            errors='ignore').read()
                aosp_declared.update(re.findall(
                    r'^\s*(?:type|attribute|typeattribute)\s+([A-Za-z0-9_-]+)',
                    text, re.M))
    shadow = sorted(n for n in declared
                    if n in aosp_declared and n not in public
                    and n not in plat_vendor)
    print(f'shadowed by the platform, declared here: {len(shadow)}')
    for name in shadow:
        print(f'  {name}')
    if not problems:
        print('\nOK: nothing unresolved, nothing declared twice')
        return 0
    print(f'\n{len(problems)} problems')
    for p in problems[:60]:
        print(' ', p)
    if len(problems) > 60:
        print(f'  ... and {len(problems) - 60} more')
    return 1


if __name__ == '__main__':
    sys.exit(main())
