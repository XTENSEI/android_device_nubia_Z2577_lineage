#!/usr/bin/env python3
"""Measure the stock rules that belong to the domains our services need."""

import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cil import load, strip_version  # noqa: E402
import service_policy as sp  # noqa: E402

STOCK = ('/home/andrei/romtools/WORK/rom/src/stock/vendor/etc/selinux'
         '/vendor_sepolicy.cil',
         '/home/andrei/romtools/WORK/rom/src/stock/odm/etc/selinux'
         '/odm_sepolicy.cil')

RULES = ('allow', 'allowx', 'dontaudit', 'auditallow', 'typetransition',
         'typechange', 'typeattribute', 'expandtypeattribute', 'roletype')


def targets():
    """Every service domain the audit says we need, plus the reuse set."""
    table = sp.contexts(sp.PLATFORM_CONTEXTS + sp.TREE_CONTEXTS)
    stock_table = sp.contexts([
        os.path.join(sp.STOCK['vendor'], 'etc/selinux/vendor_file_contexts'),
        os.path.join(sp.STOCK['odm'], 'etc/selinux/odm_file_contexts')])
    have = sp.shipped()
    domains, labels = set(), {}
    for _rc, _part, _name, exec_path, _props in sp.services():
        if not exec_path.startswith(('/vendor/', '/odm/')) or exec_path not in have:
            continue
        label = sp.labels_for(exec_path, table)
        if label and label not in sp.CATCH_ALL and label in sp.platform_types()[1] \
                and label[:-5] in sp.platform_types()[2]:
            domains.add(label[:-5])
            continue
        stock_label = sp.labels_for(exec_path, stock_table)
        if stock_label and stock_label.endswith('_exec'):
            domains.add(stock_label[:-5])
        labels[exec_path] = stock_label
    return domains, labels


def main():
    domains, labels = targets()
    print(f'domains: {len(domains)}')

    sources = Counter()
    members = defaultdict(set)
    unresolved = Counter()
    rule_rows = defaultdict(list)

    for head, args, _src in load(STOCK):
        if head not in RULES or not args:
            continue
        if head == 'typeattribute' and len(args) >= 2:
            # (typeattribute TYPE ATTR) or nested form
            pass
        if head == 'typeattribute' and args[0].startswith('('):
            inner = args[0].strip('()').split()
            if len(inner) == 2 and inner[1] in domains:
                members[inner[1]].add(inner[0])
            continue
        if head == 'typeattributeset':
            inner = args[1].strip('()') if len(args) > 1 else ''
            for name in re.findall(r'[A-Za-z0-9_]+', inner):
                if name in domains:
                    members[name].add(args[0])
            continue
        src = args[0].strip('()')
        if src not in domains:
            continue
        sources[src] += 1
        rule_rows[src].append((head, args))
        for arg in args[1:]:
            for name in re.findall(r'[A-Za-z0-9_]+', arg):
                pass

    print(f'domains with rules: {len(rule_rows)}')
    print(f'zero-rule domains:  {sorted(domains - set(rule_rows))}')
    print('\nbusiest:')
    for name, count in sources.most_common(12):
        print(f'  {count:5d}  {name}')

    print('\nattribute memberships (non hal_):')
    for name in sorted(members):
        extra = sorted(a for a in members[name] if not a.startswith('hal_'))
        if extra:
            print(f'  {name}: {extra}')

    print('\nattribute memberships (hal_):')
    for name in sorted(members):
        hal = sorted(a for a in members[name] if a.startswith('hal_'))
        if hal:
            print(f'  {name}: {hal}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
