#!/usr/bin/env python3
"""Generate the vendor sepolicy the OEM init rc services need.

The rules come from the stock vendor_sepolicy.cil and odm_sepolicy.cil, which
hold the policy the device shipped with. They are ported with one rename: the
trailing _NN_NN the versioning applies to public platform names is dropped,
because the build re-adds it from PLATFORM_SEPOLICY_VERSION.

A name a rule references is usable if the platform declares it or the tree
declares it. Everything else the rules need is declared here too, and its
labels are taken from the stock contexts files.

Usage: genpolicy.py [--write]
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cil import inner, load, strip_version  # noqa: E402
import service_policy as sp  # noqa: E402

TREE = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
OUT = os.path.join(TREE, 'sepolicy/vendor')
AOSP = '/home/andrei/romtools/WORK/aosp_sepolicy'
SV = '/home/andrei/romtools/WORK/rom/src/stock/vendor/etc/selinux'
SO = '/home/andrei/romtools/WORK/rom/src/stock/odm/etc/selinux'
STOCK_CIL = (os.path.join(SV, 'vendor_sepolicy.cil'), os.path.join(SO, 'odm_sepolicy.cil'))
PUB_VERSIONED = os.path.join(SV, 'plat_pub_versioned.cil')

CONTEXTS = {
    'file': (os.path.join(SV, 'vendor_file_contexts'),
             os.path.join(SO, 'odm_file_contexts')),
    'property': (os.path.join(SV, 'vendor_property_contexts'),
                 os.path.join(SO, 'odm_property_contexts')),
    'service': (os.path.join(SV, 'vendor_service_contexts'),),
    'vndservice': (os.path.join(SV, 'vndservice_contexts'),),
    'hwservice': (os.path.join(SV, 'vendor_hwservice_contexts'),
                  os.path.join(SO, 'odm_hwservice_contexts')),
}
CONTEXT_FILES_HEAD = {
    'file': 'file_contexts',
    'property': 'property_contexts',
    'service': 'service_contexts',
    'vndservice': 'vndservice_contexts',
    'hwservice': 'hwservice_contexts',
}

ATTRIBUTES = (
    'file_type', 'dev_type', 'property_type', 'service_manager_type',
    'hwservice_manager_type', 'sysfs_type', 'fs_type', 'data_file_type',
    'mlstrustedobject', 'mlstrustedsubject', 'vendor_file_type',
    'domain', 'exec_type', 'tmpfs_type', 'proc_type', 'debugfs_type',
    'untrusted_app_all', 'appdomain', 'netdomain', 'bluetoothdomain',
    'core_data_file_type', 'vendor_data_file_type', 'proc_seclabel',
    'port_type', 'node_type', 'vendor_property_type', 'system_property_type',
)

PROP_SCOPE = {
    'vendor_internal_property_type': 'vendor_internal_prop',
    'vendor_restricted_property_type': 'vendor_restricted_prop',
    'vendor_public_property_type': 'vendor_public_prop',
    'system_internal_property_type': 'system_internal_prop',
}

TITLE = re.compile(r'^[A-Za-z0-9_-]+$')


def idents(text):
    return [t for t in re.findall(r'[A-Za-z0-9_.\-]+', text) if TITLE.match(t)]


def restrip(text):
    """Drop _NN_NN from every bare word in a rule body."""
    return re.sub(r'\b([A-Za-z0-9_]+?)_\d+_\d+\b', r'\1', text)


def build_platform():
    """Names the platform hands to vendor policy: public plus plat_vendor."""
    public = set()
    for head, args, _src in load([PUB_VERSIONED]):
        if head in ('type', 'typeattribute') and args:
            public.add(strip_version(args[0].strip('()')))
    vendor_src = []
    for dirpath, _dirs, files in os.walk(os.path.join(AOSP, 'vendor')):
        vendor_src.extend(os.path.join(dirpath, f) for f in files if f.endswith('.te'))
    plat_vendor = set()
    hal_macro = re.compile(r'hal_attribute(?:_hwservice|_service)?\(\s*'
                           r'[A-Za-z0-9_-]+?[,\s]+([A-Za-z0-9_-]+)\s*\)')
    for path in vendor_src:
        text = open(path, encoding='utf-8', errors='ignore').read()
        plat_vendor.update(re.findall(r'^\s*(?:type|attribute|typeattribute)\s+'
                                      r'([A-Za-z0-9_-]+)', text, re.M))
        for base in hal_macro.findall(text):
            for suffix in ('', '_client', '_server', '_hwservice', '_service'):
                plat_vendor.add('hal_' + base + suffix)
        plat_vendor.update(re.findall(r'init_daemon_domain\(\s*([A-Za-z0-9_-]+)\s*\)',
                                      text))
        plat_vendor.update(n + '_exec' for n in
                           re.findall(r'init_daemon_domain\(\s*([A-Za-z0-9_-]+)\s*\)',
                                      text))
    return public, plat_vendor


# Everything after one of these lines was written by emit.py, and is ignored here.
GENERATED_MARK = re.compile(r'^# (From the stock|Stock odm and vendor|Stock vendor|Vendor hal attribute)')


def tree_text(path):
    """The part of a tree policy file this tree wrote by hand."""
    out = []
    for line in open(path, encoding='utf-8', errors='ignore'):
        if GENERATED_MARK.match(line):
            break
        out.append(line)
    return ''.join(out)


def build_tree_names():
    names = set()
    for part in ('public', 'system_ext', 'product', 'vendor'):
        base = os.path.join(TREE, 'sepolicy', part)
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                if not name.endswith('.te'):
                    continue
                text = tree_text(os.path.join(dirpath, name))
                names.update(re.findall(r'^\s*(?:type|attribute|typeattribute)\s+'
                                        r'([A-Za-z0-9_-]+)', text, re.M))
                names.update(re.findall(r'init_daemon_domain\(\s*([A-Za-z0-9_-]+)\s*\)',
                                        text))
                names.update(re.findall(r'vendor_\w+_prop\(\s*([A-Za-z0-9_-]+)\s*\)',
                                        text))
    return names


def build_stock_kinds():
    """What each name in the stock policy is, read off the stock CIL."""
    kinds = defaultdict(set)
    attributes = set()
    rules = defaultdict(list)
    genfs = []
    for path in STOCK_CIL:
        for head, args, src in load([path]):
            if head == 'type' and args:
                kinds[args[0].strip('()')].add('type')
            elif head == 'typeattribute':
                if args[0].startswith('('):
                    body = inner(args[0])
                    if len(body) == 2:
                        kinds[body[1]].add('attr:' + body[0])
                else:
                    attributes.add(args[0])
                    kinds[args[0]].add('attribute')
            elif head == 'typeattributeset' and len(args) > 1:
                attr = args[0].strip('()')
                attributes.add(attr)
                for name in inner(args[1]):
                    kinds[name].add('attr:' + attr)
            elif head == 'genfscon':
                genfs.append((args, src))
    return kinds, attributes, rules, genfs


def domain_labels():
    """exec path -> (domain, action, label).

    extend  the path already carries a label whose domain the policy declares
    claim   it does not, but the stock label names a domain that already exists
    declare the domain has to come from this tree
    """
    table = sp.contexts(sp.PLATFORM_CONTEXTS + sp.TREE_CONTEXTS)
    stock_table = sp.contexts(list(CONTEXTS['file']))
    have = sp.shipped()
    _declared, exec_types, transitions, _hal = sp.platform_types()
    out = {}
    for _rc, _part, _name, exec_path, _props in sp.services():
        if not exec_path.startswith(('/vendor', '/odm')) or exec_path not in have:
            continue
        label = sp.labels_for(exec_path, table)
        stock_label = sp.labels_for(exec_path, stock_table)
        if label and label not in sp.CATCH_ALL and label in exec_types \
                and label[:-5] in transitions:
            out[exec_path] = (label[:-5], 'extend', label)
        elif stock_label and stock_label.endswith('_exec') \
                and stock_label in exec_types \
                and stock_label[:-5] in transitions:
            out[exec_path] = (stock_label[:-5], 'claim', stock_label)
        elif stock_label and stock_label.endswith('_exec'):
            out[exec_path] = (stock_label[:-5], 'declare', stock_label)
    return out


def main():
    write = '--write' in sys.argv
    public, plat_vendor = build_platform()
    tree_names = build_tree_names()
    kinds, attributes, _rules, genfs = build_stock_kinds()
    labels = domain_labels()

    domains = {}
    for exec_path, (domain, action, label) in labels.items():
        rec = domains.setdefault(domain, {'action': action, 'label': label,
                                          'exec': []})
        rec['exec'].append(exec_path)
        if action == 'declare':
            rec['action'] = 'declare'

    print(f'domains to port: {len(domains)}')
    for action in ('extend', 'claim', 'declare'):
        n = sum(1 for d in domains.values() if d['action'] == action)
        print(f'  {action:8s} {n}')
    if '--list' in sys.argv:
        for name in sorted(domains):
            d = domains[name]
            print(f'  {d["action"]:8s} {name:36s} {d["exec"][0]}')

    known = set(public) | set(plat_vendor) | set(tree_names)
    ported = set(domains)
    known |= ported

    # Collect the rules that belong to our domains.
    per_domain = defaultdict(list)
    referenced = defaultdict(set)
    for path in STOCK_CIL:
        for head, args, _src in load([path]):
            if head not in ('allow', 'allowx', 'dontaudit', 'auditallow',
                            'typetransition'):
                continue
            if not args:
                continue
            src = strip_version(args[0].strip('()'))
            if src not in ported:
                continue
            line = restrip(' '.join(args))
            for name in idents(args[1]):
                referenced[name].add(src)
            if head == 'typetransition':
                for name in idents(args[3]):
                    referenced[name].add(src)
            per_domain[src].append((head, args, line))

    total = sum(len(v) for v in per_domain.values())
    print(f'\nrules for those domains: {total}')
    print(f'  domains with rules:   {len(per_domain)}')

    wanted = set()
    for name, _srcs in referenced.items():
        n = strip_version(name)
        if n not in known and not n.isdigit():
            wanted.add(n)

    def kind_of(name):
        marks = kinds.get(name, set())
        if 'attribute' in marks:
            return 'attribute'
        if 'attr:file_type' in marks:
            return 'file'
        if 'attr:dev_type' in marks:
            return 'device'
        if 'attr:property_type' in marks:
            return 'property'
        if 'attr:service_manager_type' in marks:
            return 'service'
        if 'attr:hwservice_manager_type' in marks:
            return 'hwservice'
        if 'attr:sysfs_type' in marks:
            return 'sysfs'
        return 'plain'

    buckets = defaultdict(list)
    for name in sorted(wanted):
        buckets[kind_of(name)].append(name)
    print(f'\nnames to declare: {len(wanted)}')
    for kind in sorted(buckets):
        print(f'  {kind:10s} {len(buckets[kind]):4d}'
              f'  e.g. {", ".join(buckets[kind][:6])}')

    # Which of them carry a label in a stock contexts file, and where.
    ctx_lines = defaultdict(lambda: defaultdict(list))
    for kind, paths in CONTEXTS.items():
        for path in paths:
            for raw in open(path, encoding='utf-8', errors='ignore'):
                line = strip_version(raw.rstrip('\r\n'))
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                m = re.search(r'u:object_r:([A-Za-z0-9_-]+)', s)
                if not m:
                    continue
                if m.group(1) in wanted:
                    ctx_lines[m.group(1)][kind].append(s)

    labelled = set(ctx_lines)
    print(f'  with a stock label: {len(labelled)}')
    unlabelled = sorted(wanted - labelled)
    print(f'  unlabelled (pure policy types): {len(unlabelled)}')
    print(f'    {", ".join(unlabelled[:24])}')

    genfs_hits = []
    for args, _src in genfs:
        if len(args) < 3:
            continue
        if any(n in wanted for n in idents(args[2])):
            genfs_hits.append(args)
    print(f'  genfscon lines for them: {len(genfs_hits)}')

    if not write:
        for name in sorted(wanted):
            print(f'{name}\t{kind_of(name)}\t{",".join(sorted(ctx_lines[name]))}')
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
