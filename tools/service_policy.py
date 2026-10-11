#!/usr/bin/env python3
"""Decide what policy each shipped init rc service needs.

For every service in the rc files, resolve its exec path against the platform
and tree file contexts and report the label, the exec type and the hal
attribute. The tree list is last because the build concatenates it last and the
last match wins.
"""

import os
import re
import sys

LIST = '/home/andrei/Downloads/Trees/device_nubia_Z2577/proprietary-files.txt'
TREE = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
AOSP = '/home/andrei/romtools/WORK/aosp_sepolicy'
STOCK = {
    'vendor': '/home/andrei/romtools/WORK/rom/src/stock/vendor',
    'odm': '/home/andrei/romtools/WORK/rom/src/stock/odm',
}

PLATFORM_CONTEXTS = (
    os.path.join(AOSP, 'private/file_contexts'),
    os.path.join(AOSP, 'system_ext/file_contexts'),
    os.path.join(AOSP, 'product/file_contexts'),
    os.path.join(AOSP, 'vendor/file_contexts'),
)
TREE_CONTEXTS = tuple(
    os.path.join(TREE, 'sepolicy', part, 'file_contexts')
    for part in ('public', 'system_ext', 'product', 'vendor')
)
CATCH_ALL = ('vendor_file', 'vendor_hal_file', 'vendor_configs_file')

SERVICE = re.compile(r'^\s*service\s+(\S+)\s+(\S+)')
PROPERTY = re.compile(r'^\s*(class|user|group|seclabel|socket|disabled|oneshot)\b')


def shipped():
    """Blob paths we ship, as /vendor/... and /odm/... absolute paths."""
    out = set()
    part = None
    for line in open(LIST, encoding='utf-8'):
        s = line.strip()
        if s.startswith('#'):
            if s == '# ODM':
                part = 'odm'
            continue
        if not s:
            continue
        src = s.split(';', 1)[0].lstrip('-').split(':', 1)[0]
        if part == 'odm' and src.startswith('odm/'):
            out.add('/' + src)
        elif src.startswith('vendor/'):
            out.add('/' + src)
    return out


def services():
    """(rc path, part, name, exec path, properties) for every shipped rc file."""
    rows = []
    have = shipped()
    for part, root in STOCK.items():
        base = os.path.join(root, 'etc/init')
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in sorted(filenames):
                if not name.endswith('.rc'):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                if '/' + part + '/' + rel.replace(os.sep, '/') not in have:
                    continue
                lines = open(os.path.join(dirpath, name), encoding='utf-8',
                             errors='ignore').read().split('\n')
                for i, line in enumerate(lines):
                    m = SERVICE.match(line)
                    if not m:
                        continue
                    props = []
                    for later in lines[i + 1:i + 16]:
                        if later.strip() and not later.startswith((' ', '\t')):
                            break
                        if PROPERTY.match(later):
                            props.append(later.strip())
                    rows.append((os.path.join(part, rel), part, m.group(1),
                                 m.group(2), props))
    return rows


def contexts(paths):
    """[(regex, label)] in file order."""
    out = []
    for path in paths:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding='utf-8', errors='ignore'):
            s = line.split('#', 1)[0].strip()
            if not s:
                continue
            bits = s.split()
            if len(bits) < 2:
                continue
            for field in bits[1:]:
                match = re.search(r'object_r:([A-Za-z0-9_-]+)', field)
                if match:
                    out.append((bits[0], match.group(1)))
                    break
    return out


def labels_for(exec_path, table):
    hit = None
    for regex, label in table:
        try:
            if re.match(regex, exec_path):
                hit = label
        except re.error:
            continue
    return hit


import genpolicy as gotree


def platform_types():
    """Types the platform declares, those declared exec_type, and the domains
    init enters, both for the platform dirs and for ours."""
    declared, exec_types, transitions, hal_attrs = set(), set(), set(), set()
    for root in (AOSP, os.path.join(TREE, 'sepolicy')):
        for dirpath, _dirnames, filenames in os.walk(root):
            if 'prebuilts' in dirpath or 'microdroid' in dirpath:
                continue
            for name in filenames:
                if not name.endswith('.te'):
                    continue
                path = os.path.join(dirpath, name)
                if root.endswith(os.path.join('device_nubia_Z2577', 'sepolicy')) \
                        and not os.environ.get('SEPOLICY_FULL_TREE'):
                    text = gotree.tree_text(path)
                else:
                    text = open(path, encoding='utf-8', errors='ignore').read()
                for m in re.finditer(r'^\s*type\s+([A-Za-z0-9_-]+)\s*,(.*)$', text, re.M):
                    declared.add(m.group(1))
                    if 'exec_type' in m.group(2):
                        exec_types.add(m.group(1))
                for m in re.finditer(r'init_daemon_domain\(\s*([A-Za-z0-9_-]+)\s*\)', text):
                    transitions.add(m.group(1))
                for m in re.finditer(r'hal_server_domain\(\s*\S+\s*,\s*([A-Za-z0-9_-]+)\s*\)', text):
                    hal_attrs.add(m.group(1))
    # The hal attributes the platform serves, from its compiled policy.
    for base, _dirs, files in os.walk(os.path.join(AOSP, 'prebuilts')):
        for name in files:
            if not name.endswith('plat_sepolicy.cil'):
                continue
            text = open(os.path.join(base, name), encoding='utf-8',
                        errors='ignore').read()
            hal_attrs.update(re.findall(r'\(typeattribute (hal_[a-z0-9_]+)_server\)', text))
    return declared, exec_types, transitions, hal_attrs


def main():
    table = contexts(PLATFORM_CONTEXTS + TREE_CONTEXTS)
    tree_table = contexts(TREE_CONTEXTS)
    declared, exec_types, transitions, hal_attrs = platform_types()
    stock_table = contexts([
        os.path.join(STOCK['vendor'], 'etc/selinux/vendor_file_contexts'),
        os.path.join(STOCK['odm'], 'etc/selinux/odm_file_contexts')])
    have = shipped()

    rows = services()
    reuse, own, declare, not_shipped, other = [], [], [], [], []
    for rc, part, name, exec_path, props in rows:
        if not exec_path.startswith(('/vendor/', '/odm/')):
            other.append((rc, name, exec_path, props))
            continue
        if exec_path not in have:
            not_shipped.append((rc, name, exec_path, props))
            continue
        label = labels_for(exec_path, table)
        tree_label = labels_for(exec_path, tree_table)
        stock_label = labels_for(exec_path, stock_table)
        rec = (rc, name, exec_path, label, stock_label, props)
        if label and label not in CATCH_ALL and label in exec_types \
                and label[:-5] in transitions:
            (own if tree_label else reuse).append(rec)
        else:
            declare.append(rec)

    # Second pass over what is stuck: the stock label decides the action.
    classify = {}
    for rc, name, exec_path, label, stock_label, props in declare:
        domain = stock_label[:-5] if (stock_label or '').endswith('_exec') else None
        attr = domain[:-len('_default')] if domain and domain.endswith('_default') else None
        if stock_label and stock_label in exec_types and domain in transitions:
            kind = 'reuse'
        elif attr and attr in hal_attrs:
            kind = 'hal'
        else:
            kind = 'daemon'
        classify[exec_path] = (kind, domain, attr, stock_label)

    print(f'services in the shipped rc files: {len(rows)}')
    print(f'  not under /vendor or /odm:  {len(other)}')
    print(f'  exec not shipped:           {len(not_shipped)}')
    print(f'  already labelled and typed: {len(own) + len(reuse)}')
    print(f'  needs a label or a domain:  {len(declare)}')
    for kind in ('reuse', 'hal', 'daemon'):
        n = sum(1 for v in classify.values() if v[0] == kind)
        print(f'    {kind:7s} {n}')

    print('\n# ours already, nothing to do')
    for rc, name, exec_path, label, stock_label, _p in own:
        print(f'  {label:34s} {exec_path}')

    print('\n# the platform domain fits, a file context line is enough')
    for rc, name, exec_path, label, stock_label, _p in declare:
        kind, domain, attr, stock = classify[exec_path]
        if kind == 'reuse':
            print(f'  {stock:34s} {exec_path}')

    print('\n# declare the domain on a platform hal attribute')
    for rc, name, exec_path, label, stock_label, _p in declare:
        kind, domain, attr, stock = classify[exec_path]
        if kind == 'hal':
            print(f'  {domain:38s} hal_server_domain({domain}, {attr})   {exec_path}')

    print('\n# nothing on the platform, declare the domain and its allows')
    for rc, name, exec_path, label, stock_label, props in declare:
        kind, domain, attr, stock = classify[exec_path]
        if kind == 'daemon':
            print(f'  {exec_path}')
            print(f'      rc {rc} service {name}  stock label {stock}  domain {domain}')
            for prop in props:
                print(f'      {prop}')

    print('\n# exec referenced but not shipped')
    for rc, name, exec_path, _p in not_shipped:
        print(f'  {rc} service {name} -> {exec_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
