#!/usr/bin/env python3
"""Write the ported vendor sepolicy, one subsystem at a time.

Reads the stock CIL and the stock contexts files through genpolicy, then writes
the tree files. Existing tree files are extended, never overwritten.

The work is grouped by subsystem. Every item the port produces, a domain file,
a type declaration, a label, a genfscon line, belongs to the group whose
domains first need it, and --upto writes the cumulative state up to and
including one group. Calling it once per group in order therefore yields a
series of commits where each one is complete on its own: a group's rules only
ever name types that an earlier group or the same group declared.

Usage: emit.py [--upto GROUP] [--list-groups] [--dry-run]
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cil import inner, load, strip_version  # noqa: E402
import genpolicy as gp  # noqa: E402

TREE = gp.TREE
RULES = ('allow', 'allowx', 'dontaudit', 'auditallow', 'typetransition')

ATTRS_FOR_DOMAIN = ('mlstrustedsubject', 'mlstrustedobject', 'netdomain',
                    'bpfdomain')

# The stock attributes worth re-declaring, in the reference trees' order.
TYPE_ATTRS = ('exec_type', 'file_type', 'vendor_file_type', 'data_file_type',
              'core_data_file_type', 'vendor_data_file_type', 'dev_type',
              'property_type', 'service_manager_type', 'hwservice_manager_type',
              'sysfs_type', 'fs_type', 'proc_type', 'debugfs_type',
              'mlstrustedobject', 'mlstrustedsubject', 'domain')

# Ordered by subsystem, one group per commit.
GROUPS = (
    ('tee', 'The TEE and key management domains',
     ['tee', 'hal_gatekeeper_default', 'hal_identity_default',
      'hal_keymint_unisoc', 'hal_trustyclientaidl_default']),
    ('boot', 'The kernel module and boot script domains',
     ['insmod_sh', 'create_spl_link', 'init-ssdaemon_vendor-sh',
      'start_rkptool', 'swappiness-sh', 'variantidBin', 'ufs_ffu',
      'cp_diskserver', 'uniber']),
    ('log', 'The logging and crash reporting domains',
     ['ylog_lite', 'slogmodem_vendor', 'hal_cplog_svcaidl_default',
      'hal_connmgr_default', 'refnotify', 'srtd', 'systemDebuggerd',
      'phasecheckserver']),
    ('eng', 'The engineering and vendor service domains',
     ['engpc', 'dcxsrv', 'sensor_cali_test', 'zte_ldd_test',
      'hal_toolaidl_default', 'hal_ai_engine_default', 'unionpnp_service',
      'hal_enhanceaidl_default', 'ssdaemon_vendor']),
    ('radio', 'The telephony and radio domains',
     ['rild', 'modem_control', 'hal_networkaidl_default',
      'hal_broadcastradio_ext']),
    ('conn', 'The connectivity and GNSS domains',
     ['hal_gnss_ext_default', 'gpsd', 'wcnd', 'wcn_chr', 'hal_wifi_default',
      'hal_wifi_supplicant_default', 'hal_wifi_hostapd_default',
      'hal_bluetooth_default']),
    ('power', 'The charging, power and thermal domains',
     ['charge', 'charged', 'thermald', 'hal_thermal_ext', 'sqc_daemon',
      'zte_battery_life', 'zte_thermal_daemon', 'battery_record_daemon',
      'hal_ldd_cmd_default', 'hal_power_default', 'hal_power_stats_default',
      'hal_health_default', 'hal_rebootescrow_default']),
    ('ui', 'The display, input and biometric domains',
     ['hal_light_default', 'hal_memtrack_default', 'hal_vibrator_default',
      'hal_usb_default', 'hal_nfc_default', 'hal_oemlock_default',
      'hal_fingerprint_default', 'hal_bootctrl_default', 'hal_audio_default',
      'hal_camera_default', 'hal_sensors_default',
      'hal_graphics_composer_default', 'hal_graphics_allocator_default']),
    ('media', 'The media, DRM and neural network domains',
     ['hal_codec2_unisoc', 'mediacodec', 'hal_drm_clearkey_aidl',
      'hal_drm_widevine', 'hal_cas_default', 'hal_hdcp_default',
      'hal_armnn-gpu_default', 'vendor_boringssl_self_test']),
)

GROUP_OF = {d: i for i, (_k, _s, ds) in enumerate(GROUPS) for d in ds}
GROUP_KEY = [k for k, _s, _d in GROUPS]

SECTIONS = {
    'attribute': ('types.te', '# Stock vendor attributes'),
    'device': ('device.te', '# Stock odm and vendor device types'),
    'file': ('file.te', '# Stock odm and vendor file types'),
    'hwservice': ('types.te', '# Stock vendor hwservice types'),
    'plain': ('types.te', '# Stock vendor policy types'),
    'property': ('property.te', '# Stock odm and vendor property types'),
    'service': ('types.te', '# Stock vendor service types'),
    'sysfs': ('types.te', '# Stock vendor sysfs types'),
}
PLACE = (('file', 'file_type'), ('device', 'dev_type'),
         ('property', 'property_type'), ('service', 'service_manager_type'),
         ('hwservice', 'hwservice_manager_type'), ('sysfs', 'sysfs_type'))
CONTEXTS_OUT = {
    'file': ('file_contexts', '# Stock odm and vendor file contexts'),
    'property': ('property_contexts', '# Stock odm and vendor property contexts'),
    'service': ('service_contexts', '# Stock vendor service contexts'),
    'vndservice': ('vndservice_contexts', '# Stock vendor vndservice contexts'),
    'hwservice': ('hwservice_contexts', '# Stock vendor hwservice contexts'),
}
PLATFORM_CONTEXTS = {
    'file': ('private/file_contexts', 'vendor/file_contexts'),
    'property': ('private/property_contexts', 'vendor/property_contexts'),
    'service': ('private/service_contexts', 'vendor/service_contexts'),
    'vndservice': ('vendor/vndservice_contexts',),
    'hwservice': ('private/hwservice_contexts', 'vendor/hwservice_contexts'),
}


def read_existing(rel):
    """The hand written part of a file. A previous run's block is dropped so
    that running this twice does not append it twice."""
    path = os.path.join(TREE, rel)
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding='utf-8', errors='ignore'):
        if gp.GENERATED_MARK.match(line):
            break
        out.append(line.rstrip('\n'))
    while out and not out[-1].strip():
        out.pop()
    return out


def unversion(text):
    return re.sub(r'\b([A-Za-z0-9_]+?)_\d+_\d+\b', r'\1', text)


def rule_to_te(head, args):
    """One CIL statement as one .te line, or None when a macro covers it."""
    if head in ('allow', 'dontaudit', 'auditallow'):
        src, tgt = unversion(args[0]), unversion(args[1])
        bits = inner(unversion(args[2]))
        cls, perms = bits[0], ' '.join(inner(bits[1]))
        if len(perms.split()) == 1:
            return f'{head} {src} {tgt}:{cls} {perms};'
        return f'{head} {src} {tgt}:{cls} {{ {perms} }};'
    if head == 'allowx':
        src, tgt = unversion(args[0]), unversion(args[1])
        bits = inner(unversion(args[2]))
        # checkpolicy collapses consecutive ioctl values into a CIL range
        ops = []
        for token in inner(bits[2]):
            m = re.fullmatch(r'\(range (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)\)', token)
            if m:
                lo, hi = int(m.group(1), 16), int(m.group(2), 16)
                ops.extend(hex(v) for v in range(lo, hi + 1))
            else:
                ops.append(token)
        return f'allowxperm {src} {tgt}:{bits[1]} ioctl {{ {" ".join(ops)} }};'
    if head == 'typetransition':
        src, tgt = unversion(args[0]), unversion(args[1])
        cls = unversion(args[2])
        if len(args) == 5:
            return f'type_transition {src} {tgt}:{cls} {args[3]} {unversion(args[4])};'
        if src == 'init' and cls == 'process':
            return None
        return f'type_transition {src} {tgt}:{cls} {unversion(args[3])};'
    raise SystemExit(f'unhandled {head}: {" ".join(args)}')


def normalize_path(line):
    """The platform writes vendor and odm paths with a symlink alternation,
    which matches both the mount point and the path under it."""
    for mount, alt in (('/vendor/', '/(vendor|system/vendor)/'),
                       ('/odm/', '/(odm|system/odm)/')):
        if line.startswith(mount):
            return alt + line[len(mount):]
    return line


def platform_contexts(kind):
    """(path regex, label) pairs the platform already ships for this kind."""
    out = set()
    for rel in PLATFORM_CONTEXTS[kind]:
        path = os.path.join(gp.AOSP, rel)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding='utf-8', errors='ignore'):
            line = line.split('#', 1)[0].strip()
            bits = line.split()
            if len(bits) < 2:
                continue
            m = re.search(r'object_r:([A-Za-z0-9_-]+)', bits[1])
            if m:
                out.add((bits[0], m.group(1)))
    return out


def main():
    dry = '--dry-run' in sys.argv
    if '--list-groups' in sys.argv:
        for i, (key, subject, ds) in enumerate(GROUPS):
            print(f'{i} {key:6s} {len(ds):3d} domains  {subject}')
        return 0
    # Declarations land before any rule, because the domains name each other both ways.
    stage = sys.argv[sys.argv.index('--stage') + 1] if '--stage' in sys.argv else 'all'
    rule_limit = -1
    if '--rules-upto' in sys.argv:
        rule_limit = GROUP_KEY.index(sys.argv[sys.argv.index('--rules-upto') + 1])
    label_kinds = {'none': (), 'file': ('file',),
                   'property': ('file', 'property'),
                   'all': tuple(sorted(CONTEXTS_OUT)) + ('genfs',)}[stage]

    public, plat_vendor = gp.build_platform()
    tree_names = gp.build_tree_names()
    kinds, _attributes, _rules, genfs = gp.build_stock_kinds()
    exec_labels = gp.domain_labels()

    domains = {}
    for exec_path, (domain, action, label) in exec_labels.items():
        rec = domains.setdefault(domain, {'action': action, 'label': label,
                                          'exec': []})
        rec['exec'].append(exec_path)
        if action == 'declare':
            rec['action'] = 'declare'

    ungrouped = sorted(set(domains) - set(GROUP_OF))
    if ungrouped:
        raise SystemExit(f'no group for: {ungrouped}')
    if len(GROUP_OF) != len(domains):
        raise SystemExit(f'groups name {len(GROUP_OF)} domains, audit found {len(domains)}')

    known = set(public) | set(plat_vendor) | set(tree_names) | set(domains)

    # (a) the rules, per domain, and every type they name
    per_domain = defaultdict(list)
    referrers = defaultdict(set)
    attr_members = defaultdict(set)
    for path in gp.STOCK_CIL:
        for head, args, _src in load([path]):
            if head == 'typeattributeset' and len(args) > 1:
                attr = args[0].strip('()')
                for name in inner(args[1]):
                    if name in domains:
                        attr_members[name].add(attr)
                continue
            if head not in RULES or not args:
                continue
            src = strip_version(args[0].strip('()'))
            if src not in domains:
                continue
            line = rule_to_te(head, args)
            if line and line not in per_domain[src]:
                per_domain[src].append(line)
            if head == 'typetransition':
                positions = (1, 4) if len(args) == 5 else (1, 3)
            else:
                positions = (1,)
            for pos in positions:
                if pos < len(args):
                    for name in re.findall(r'[A-Za-z0-9_-]+', args[pos]):
                        referrers[strip_version(name)].add(src)

    # (b) the hal attributes our declared domains serve
    hal_attrs, oem_hal_attrs = {}, set()
    for domain, rec in domains.items():
        if rec['action'] != 'declare':
            continue
        for attr in sorted(attr_members.get(domain, ())):
            if attr.endswith('_server') and attr.startswith('hal_'):
                base = attr[:-len('_server')]
                hal_attrs[domain] = base
                if base + '_client' not in public and base + '_client' not in plat_vendor:
                    oem_hal_attrs.add(base)

    # (c) which group first needs each name
    owner = {}
    for name, sources in referrers.items():
        owner[name] = min(GROUP_OF[s] for s in sources if s in GROUP_OF)
    owned_names = {}
    for domain, rec in domains.items():
        if rec['action'] == 'declare':
            owned_names[domain] = GROUP_OF[domain]
            owned_names[rec['label']] = GROUP_OF[domain]
    for base in oem_hal_attrs:
        base_owner = min(GROUP_OF[d] for d, b in hal_attrs.items() if b == base)
        for name in (base, base + '_client', base + '_server'):
            owned_names[name] = base_owner

    def owner_of(name):
        return owned_names.get(name, owner.get(name, 0))

    # (d) what is left to declare, minus the CIL keywords stock never declares.
    owned = set(owned_names)
    wanted = {n for n in referrers if n not in known and n not in owned
              and (n in kinds or n in oem_hal_attrs)}

    resolvable = known | wanted | owned

    def kind_of(name):
        marks = kinds.get(name, set())
        if 'attribute' in marks:
            return 'attribute'
        for kind, attr in PLACE:
            if 'attr:' + attr in marks:
                return kind
        return 'plain'

    def decl(name):
        if 'attribute' in kinds.get(name, set()):
            return f'attribute {name};'
        attrs = [a for a in TYPE_ATTRS if 'attr:' + a in kinds.get(name, set())]
        if not attrs:
            return f'type {name};'
        return f'type {name}, {", ".join(attrs)};'

    # (e) labels. Only what the platform does not already ship.
    ctx = defaultdict(list)
    for kind, paths in gp.CONTEXTS.items():
        skip = platform_contexts(kind)
        for path in paths:
            for raw in open(path, encoding='utf-8', errors='ignore'):
                s = unversion(raw.rstrip('\r\n')).strip()
                if not s or s.startswith('#'):
                    continue
                if kind == 'file':
                    s = normalize_path(s)
                m = re.search(r'object_r:([A-Za-z0-9_-]+)', s)
                if not m or m.group(1) not in resolvable:
                    continue
                if (s.split()[0], m.group(1)) in skip:
                    continue
                if s not in ctx[kind]:
                    ctx[kind].append(s)

    # (f) genfscon for the nodes the ported rules touch
    aosp_genfs = set()
    for rel in ('private/genfs_contexts', 'vendor/genfs_contexts'):
        path = os.path.join(gp.AOSP, rel)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding='utf-8', errors='ignore'):
            bits = line.split()
            if len(bits) >= 2 and bits[0] == 'genfscon':
                aosp_genfs.add((bits[1], bits[2].strip('"')))
    genfs_out = []
    for args, _src in genfs:
        if len(args) < 3:
            continue
        bits = inner(args[2])
        if len(bits) < 3 or bits[2] not in referrers:
            continue
        fs, path = args[0], args[1].strip('"')
        if (fs, path) in aosp_genfs:
            continue
        line = f'genfscon {fs} "{path}" u:object_r:{bits[2]}:s0'
        if line not in genfs_out:
            genfs_out.append(line)

    # (g) assemble. One block per file and section, so each commit only appends.
    plan = []
    lines_of = {}

    def key(rel, header):
        if (rel, header) not in lines_of:
            lines_of[(rel, header)] = []
            plan.append((rel, header))

    def add(rel, header, lines):
        if not lines:
            return
        key(rel, header)
        lines_of[(rel, header)].extend(lines)

    for kind in sorted(SECTIONS):
        key('sepolicy/vendor/' + SECTIONS[kind][0], SECTIONS[kind][1])
    for base in sorted(oem_hal_attrs):
        key(f'sepolicy/public/{base}.te', '# Vendor hal attribute')
    for kind in sorted(CONTEXTS_OUT):
        key('sepolicy/vendor/' + CONTEXTS_OUT[kind][0], CONTEXTS_OUT[kind][1])
    key('sepolicy/vendor/genfs_contexts', '# Stock odm and vendor genfs contexts')

    sources = ' and '.join(sorted(os.path.basename(p) for p in gp.STOCK_CIL))
    for group in range(len(GROUPS)):
        for domain in sorted(d for d in domains if GROUP_OF[d] == group):
            rec = domains[domain]
            body = []
            if rec['action'] == 'declare':
                body.append(f'type {domain}, domain;')
                if domain in hal_attrs:
                    body.append(
                        f'hal_server_domain({domain}, {hal_attrs[domain]})')
                for attr in sorted(attr_members.get(domain, ())):
                    if attr in ATTRS_FOR_DOMAIN:
                        body.append(f'typeattribute {domain} {attr};')
                body.append('')
                body.append(f'type {rec["label"]}, exec_type, vendor_file_type, '
                            f'file_type;')
                body.append(f'init_daemon_domain({domain})')
                body.append('')
            if group <= rule_limit:
                body.extend(per_domain.get(domain, ()))
            add(f'sepolicy/vendor/{domain}.te', f'# From the stock {sources}',
                body)


    # Declarations and labels land once, labels in the stock order they match in.
    for kind in sorted(SECTIONS):
        rel, header = SECTIONS[kind]
        add('sepolicy/vendor/' + rel, header,
            [decl(n) for n in sorted(wanted) if kind_of(n) == kind])
    for base in sorted(oem_hal_attrs):
        add(f'sepolicy/public/{base}.te', '# Vendor hal attribute',
            [f'attribute {base};', f'attribute {base}_client;',
             f'attribute {base}_server;'])
    for kind, ctx_lines in sorted(ctx.items()):
        if kind in label_kinds:
            rel, header = CONTEXTS_OUT[kind]
            add('sepolicy/vendor/' + rel, header, ctx_lines)
    if 'genfs' in label_kinds:
        add('sepolicy/vendor/genfs_contexts',
            '# Stock odm and vendor genfs contexts', genfs_out)

    written = {}
    for rel, header in plan:
        body = lines_of[(rel, header)]
        if not body:
            continue
        out = written.setdefault(rel, read_existing(rel))
        if out and out[-1] != '':
            out.append('')
        out.append(header)
        out.extend(body)
    total = sum(len(l) for l in written.values())
    tail = GROUP_KEY[rule_limit] if rule_limit >= 0 else 'no rules'
    print(f'stage {stage}, rules {tail}: {len(written)} files, {total} lines')

    if dry:
        return 0
    for rel, out in written.items():
        path = os.path.join(TREE, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(out) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
