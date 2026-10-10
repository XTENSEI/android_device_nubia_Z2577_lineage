#!/usr/bin/env python3
"""Resolve which names a stock vendor or odm rule may reference.

The build compiles device sepolicy with only four platform inputs:
plat_public_policy, system_ext and product public policy, reqd_mask, and
plat_vendor. So a name is usable by our tree if the platform declares it, and
has to be declared by us if the platform does not.

plat_pub_versioned.cil is the compiled public platform policy, which is the
namespace se_versioned_policy hands to vendor policy. Versions are stripped
because the build re-adds them from the device's PLATFORM_SEPOLICY_VERSION.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cil import load, strip_version  # noqa: E402

AOSP = '/home/andrei/romtools/WORK/aosp_sepolicy'
STOCK = {
    'vendor': ('/home/andrei/romtools/WORK/rom/src/stock/vendor/etc/selinux'
               '/vendor_sepolicy.cil'),
    'odm': ('/home/andrei/romtools/WORK/rom/src/stock/odm/etc/selinux'
            '/odm_sepolicy.cil'),
}
PUB_VERSIONED = ('/home/andrei/romtools/WORK/rom/src/stock/vendor/etc/selinux'
                 '/plat_pub_versioned.cil')

TYPE_DECL = re.compile(r'^\s*(?:type|typeattribute)\s+([A-Za-z0-9_]+)', re.M)
ATTR_DECL = re.compile(r'^\s*attribute\s+([A-Za-z0-9_]+)', re.M)
HAL_MACRO = re.compile(r'^hal_attribute(?:_hwservice|_service)?'
                       r'\(\s*[A-Za-z0-9_]+?[,\s]+([A-Za-z0-9_]+)\s*\)', re.M)


def declared(paths):
    """Type and attribute names from .te sources, macros expanded."""
    names = set()
    for path in paths:
        text = open(path, encoding='utf-8', errors='ignore').read()
        names.update(TYPE_DECL.findall(text))
        names.update(ATTR_DECL.findall(text))
        for base in HAL_MACRO.findall(text):
            for suffix in ('', '_client', '_server', '_hwservice', '_service'):
                names.add('hal_' + base + suffix)
        names.update(re.findall(r'hal_client_domain\(\s*\S+\s*,\s*'
                                r'([A-Za-z0-9_]+)\s*\)', text))
        for suffix in ('_exec',):
            names.update(n + suffix for n in
                         re.findall(r'init_daemon_domain\(\s*([A-Za-z0-9_]+)',
                                    text))
    return names


def aosp_files(*subdirs):
    out = []
    for sub in subdirs:
        base = os.path.join(AOSP, sub)
        for dirpath, _dirs, files in os.walk(base):
            out.extend(os.path.join(dirpath, f) for f in files if f.endswith('.te'))
    return sorted(out)


def main():
    # Names the platform owns: public policy (compiled) plus plat_vendor source.
    public = set()
    for head, args, _src in load([PUB_VERSIONED]):
        if head in ('type', 'typeattribute') and args:
            public.add(strip_version(args[0].strip('()')))
    plat_vendor = declared(aosp_files('vendor'))

    print(f'plat_pub_versioned.cil names: {len(public)}')
    print(f'plat_vendor .te names:        {len(plat_vendor)}')
    print(f'public sources:               {len(declared(aosp_files("public")))}')

    for part, path in STOCK.items():
        own = set()
        for head, args, _src in load([path]):
            if head in ('type', 'typeattribute') and args:
                own.add(args[0].strip('()'))
        shared = own & public
        vendor_shared = own & plat_vendor
        ours = own - public - plat_vendor
        print(f'\n{part}: {len(own)} names'
              f'  in public {len(shared)}  in plat_vendor {len(vendor_shared)}'
              f'  ours to declare {len(ours)}')
        print('  sample public overlap:', sorted(shared)[:8])
        print('  sample plat_vendor overlap:', sorted(vendor_shared)[:8])
        print('  sample ours:', sorted(ours)[:8])

    print('\nhal_light_default in public?', 'hal_light_default' in public)
    print('hal_light_default in plat_vendor?', 'hal_light_default' in plat_vendor)
    print('init in public?', 'init' in public)
    print('vendor_init in public?', 'vendor_init' in public)
    return 0


if __name__ == '__main__':
    sys.exit(main())
