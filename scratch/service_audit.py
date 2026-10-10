#!/usr/bin/env python3
"""Work out the labels and the domains the stock init rc services need.

Reads the service definitions out of the init rc files we ship, resolves each
exec path against the platform and the tree file contexts, and reports the ones
that end up on the vendor_file catch all, which is where a service never starts.

The platform list comes first and the tree list last, because the build
concatenates them in that order and the last match wins.
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

# In the order the build lays them down.
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
    for part, root in STOCK.items():
        base = os.path.join(root, 'etc/init')
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in sorted(filenames):
                if not name.endswith('.rc'):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                if '/' + part + '/' + rel.replace(os.sep, '/') not in shipped():
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
            label = None
            for field in bits[1:]:
                match = re.search(r'object_r:([A-Za-z0-9_]+)', field)
                if match:
                    label = match.group(1)
                    break
            if label:
                out.append((bits[0], label))
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


def declared_types():
    """Exec types the platform and the tree declare, and the domains init enters.

    Android names the exec type after the domain, hal_audio_default_exec for
    hal_audio_default, so the transition exists when the suffix matches.
    """
    declared, exec_types, transitions = set(), set(), set()
    for root in (AOSP, os.path.join(TREE, 'sepolicy')):
        for dirpath, _dirnames, filenames in os.walk(root):
            if 'prebuilts' in dirpath or 'microdroid' in dirpath:
                continue
            for name in filenames:
                if not name.endswith('.te'):
                    continue
                text = open(os.path.join(dirpath, name), encoding='utf-8',
                            errors='ignore').read()
                for m in re.finditer(r'^\s*type\s+([A-Za-z0-9_]+)\s*,(.*)$', text, re.M):
                    declared.add(m.group(1))
                    if 'exec_type' in m.group(2):
                        exec_types.add(m.group(1))
                for m in re.finditer(r'init_daemon_domain\(\s*([A-Za-z0-9_]+)\s*\)', text):
                    transitions.add(m.group(1))
    usable = {t for t in exec_types
              if t.endswith('_exec') and t[:-len('_exec')] in transitions}
    return declared, usable


def main():
    table = contexts(PLATFORM_CONTEXTS + TREE_CONTEXTS)
    tree_table = contexts(TREE_CONTEXTS)
    _declared, usable = declared_types()
    stock_table = contexts([os.path.join(STOCK['vendor'], 'etc/selinux/vendor_file_contexts'),
                            os.path.join(STOCK['odm'], 'etc/selinux/odm_file_contexts')])
    shipped_paths = shipped()

    rows = services()
    own, platform, stuck, not_shipped = [], [], [], []
    for rc, part, name, exec_path, props in rows:
        if not exec_path.startswith(('/vendor/', '/odm/')):
            continue
        if exec_path not in shipped_paths:
            not_shipped.append((rc, name, exec_path))
            continue
        label = labels_for(exec_path, table)
        tree_label = labels_for(exec_path, tree_table)
        stock_label = labels_for(exec_path, stock_table)
        record = (rc, name, exec_path, label, stock_label, props)
        if label and label not in CATCH_ALL and label in usable:
            (own if tree_label else platform).append(record)
        else:
            stuck.append(record)

    print(f'services under /vendor and /odm in the shipped rc files: {len(rows)}')
    print(f'  exec not shipped: {len(not_shipped)}')
    print(f'  label from the tree: {len(own)}')
    print(f'  label from the platform: {len(platform)}')
    print(f'  no usable label: {len(stuck)}')

    print('\n# labelled by the platform, nothing to do')
    for rc, name, exec_path, label, stock_label, _props in platform:
        print(f'  {label:42s} {exec_path}')

    print('\n# labelled by the tree already')
    for rc, name, exec_path, label, stock_label, _props in own:
        print(f'  {label:42s} {exec_path}')

    print('\n# needs policy')
    for rc, name, exec_path, label, stock_label, props in stuck:
        print(f'  {exec_path}')
        print(f'      rc {rc} service {name}')
        print(f'      platform label: {label}  stock label: {stock_label}')
        for prop in props:
            print(f'      {prop}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
