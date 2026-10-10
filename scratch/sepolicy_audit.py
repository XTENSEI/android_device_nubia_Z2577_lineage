#!/usr/bin/env python3
"""Check the vendor sepolicy in this tree against the AOSP policy.

Everything the local files reference has to resolve to something the build
already knows: a type or attribute from system/sepolicy, a macro, a class or a
permission. secilc is not available here, so this stands in for it.
"""

import os
import re
import sys
from collections import defaultdict

TREE = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
AOSP = '/home/andrei/romtools/WORK/aosp_sepolicy'
OURS = os.path.join(TREE, 'sepolicy')

CLASSES = {
    'file', 'dir', 'lnk_file', 'chr_file', 'blk_file', 'sock_file', 'fifo_file',
    'process', 'process2', 'security', 'system', 'capability', 'cap_userns',
    'capability2', 'cap2_userns', 'key', 'key_socket', 'property_service',
    'service_manager', 'unix_stream_socket', 'unix_dgram_socket', 'tcp_socket',
    'udp_socket', 'netlink_socket', 'packet_socket', 'rawip_socket',
    'netlink_route_socket', 'netlink_kobject_uevent_socket', 'node', 'netif',
    'fd', 'filesystem', 'binder', 'bpf', 'anon_inode', 'io_uring', 'memfd_file',
    'perf_event', 'user_namespace', 'debugfs', 'devpts', 'tmpfs', 'proc',
}

TYPEATTRS = {
    'dev_type', 'file_type', 'exec_type', 'data_file_type', 'sysfs_type',
    'fs_type', 'proc_type', 'vendor_file_type', 'system_file_type',
    'system_dlkm_file_type', 'domain', 'property_type', 'mlstrustedobject',
    'mlstrustedsubject', 'service_manager_type', 'r_dir_perms',
}

KEYWORDS = {
    'allow', 'neverallow', 'dontaudit', 'auditallow', 'type', 'typeattribute',
    'roletype', 'attribute', 'type_transition', 'type_change', 'self', 'role',
    'object_r', 'permissive', 'typealias', 'attribute_role', 'rolectx',
    'expandtypeattribute', 'genfscon', 'boolean', 'true', 'false',
}

TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_.\-]*')

# Filled from the AOSP access_vectors, i.e. every permission name there is.
permissions = set()


def collect_aosp():
    types, attrs, macros = set(), set(), set()
    for root, _, names in os.walk(AOSP):
        if 'prebuilts' in root or 'microdroid' in root or 'test' in root:
            continue
        for name in names:
            path = os.path.join(root, name)
            if name.endswith('.te'):
                text = open(path, encoding='utf-8', errors='replace').read()
                types.update(re.findall(r'^type ([^\s,;]+)', text, re.M))
                types.update(re.findall(r'^typealias ([^\s,;]+)', text, re.M))
                attrs.update(re.findall(r'^attribute ([^\s,;]+)', text, re.M))
                # hal_attribute(x), hal_server_domain(x, y) and friends generate the attributes.
                for macro in ('hal_attribute', 'hal_server_domain',
                              'hal_client_domain'):
                    for args in re.findall(rf'^{macro}\(([^)]*)\)', text, re.M):
                        attrs.update(a.strip() for a in args.split(','))
            elif name in ('attributes', 'te_macros', 'global_macros'):
                text = open(path, encoding='utf-8', errors='replace').read()
                attrs.update(re.findall(r'^attribute ([^\s,;]+)', text, re.M))
                macros.update(re.findall(r"define\(`([A-Za-z0-9_]+)'", text))
            elif name == 'access_vectors':
                text = open(path, encoding='utf-8', errors='replace').read()
                permissions.update(
                    re.findall(r'^\s*([a-z][a-z0-9_]*)\s*$', text, re.M))
    return types, attrs, macros


def ours_files():
    paths = []
    for root, _, names in os.walk(OURS):
        for name in sorted(names):
            paths.append(os.path.join(root, name))
    return paths


def main():
    aosp_types, aosp_attrs, aosp_macros = collect_aosp()
    known = (aosp_types | aosp_attrs | aosp_macros | CLASSES | TYPEATTRS
             | KEYWORDS | permissions)

    our_types = defaultdict(list)
    our_attrs = set()
    unknown = defaultdict(set)

    lines = []
    for path in ours_files():
        if not path.endswith('.te'):
            continue
        rel = os.path.relpath(path, TREE)
        for line in open(path, encoding='utf-8'):
            lines.append((rel, line))

    # Declarations first: a type used by one file is often declared by another.
    for rel, line in lines:
        line = line.split('#')[0].strip()
        if not line:
            continue
        for name in re.findall(r'^type ([^\s,;]+)', line, re.M):
            our_types[name].append(rel)
        for name in re.findall(r'^\s*attribute ([^\s,;]+)', line, re.M):
            our_attrs.add(name)
        for name in re.findall(r'^typeattribute ([^\s,;]+)', line, re.M):
            our_attrs.add(name)
        # Types the tree declares through a macro show up as call arguments instead.
        for name in re.findall(r'[a-z_]+_prop\(([a-z0-9_]+)\)', line):
            our_attrs.add(name)

    for rel, line in lines:
        line = line.split('#')[0].strip()
        if not line:
            continue
        for tok in TOKEN.findall(line):
            if tok in known or tok in our_attrs or tok in our_types:
                continue
            unknown[rel].add(tok)

    print(f'AOSP: {len(aosp_types)} types, {len(aosp_attrs)} attributes, '
          f'{len(aosp_macros)} macros, {len(permissions)} permissions')
    print(f'ours: {len(our_types)} declared types, {len(our_attrs)} extra names')

    print('\n== type collisions with AOSP ==')
    hits = {n: v for n, v in our_types.items() if n in aosp_types}
    print('none' if not hits else '\n'.join(f'  {n} in {v}' for n, v in hits.items()))

    print('\n== duplicate declarations in our tree ==')
    dupes = {n: v for n, v in our_types.items() if len(v) > 1}
    print('none' if not dupes else '\n'.join(f'  {n} in {v}' for n, v in dupes.items()))

    print('\n== tokens that resolve to nothing ==')
    if not unknown:
        print('none')
    for rel, toks in sorted(unknown.items()):
        print(f'  {rel}: {" ".join(sorted(toks))}')

    print('\n== file_contexts ==')
    ours = []
    for line in open(os.path.join(OURS, 'vendor', 'file_contexts'),
                     encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        ours.append(line.split()[0])
    aosp_paths = set()
    for root, _, names in os.walk(AOSP):
        if 'prebuilts' in root or 'microdroid' in root:
            continue
        for name in names:
            if 'file_contexts' in name:
                for line in open(os.path.join(root, name),
                                 encoding='utf-8', errors='replace'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    aosp_paths.add(line.split()[0])
    print(f'  {len(ours)} entries in ours')
    clash = [p for p in ours if p in aosp_paths]
    print('  exact path clashes: ' + ('none' if not clash else ', '.join(clash)))

    print('\n== property_contexts ==')
    for line in open(os.path.join(OURS, 'vendor', 'property_contexts'),
                     encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#'):
            print('  ' + line)

    return 0


if __name__ == '__main__':
    sys.exit(main())
