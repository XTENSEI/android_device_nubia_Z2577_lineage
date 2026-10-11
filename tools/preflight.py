#!/usr/bin/env python3
"""Everything a build would reject, checked offline before it runs.

  P1  module names legal for Soong
  P2  duplicate module names, within a file and between the two bp files
  P3  every source path in an Android.bp exists on disk
  P4  every PRODUCT_COPY_FILES source exists on disk
  P5  every PRODUCT_PACKAGES name in the vendor repo is one of its modules
  P6  proprietary-files.txt and the vendor repo agree, both ways
  P7  every blob lands somewhere: a module src or a copy rule
  P8  every install_symlink target resolves
  P9  every $(DEVICE_PATH)/... reference in the makefiles exists
  P10 copy-file destination collisions
  P11 prebuilts whose name AOSP also uses, which the platform now provides
  P12 prebuilt prefer flags, which regeneration has to drop
  P13 a shared prebuilt whose AOSP namesake is static only
  P14 frozen AIDL versions a module can reach, the platform ones included

Usage: preflight.py [--aosp <tree> ...] [--stock <mount>] [--selftest]
"""

import argparse
import os
import re
import sys
import tempfile
from collections import defaultdict

DEVICE = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
VENDOR = '/home/andrei/Downloads/Trees/vendor_nubia_Z2577_lineage'

LEGAL_NAME = re.compile(r'^[A-Za-z0-9_.@+-]+$')
MODULE_OPEN = re.compile(r'^([a-z_0-9]+) \{$')
BACKENDS = 'ndk|cpp|java|rust|ndk_platform'
VERSIONED = re.compile(r'^(?P<iface>.+?)-V(?P<version>\d+)'
                       r'-(?P<lang>' + BACKENDS + r')$')
# the `:module` reference a srcs entry can carry, the -source copy of a backend
SOURCE = re.compile(r'^(?P<iface>.+?)-V(?P<version>\d+)'
                    r'-(?P<lang>' + BACKENDS + r')-source$')
LANGS = tuple(BACKENDS.split('|'))
LIBS = ('shared_libs', 'static_libs', 'whole_static_libs')
SRC_PROP = re.compile(r'^\s*srcs?: (\[(.*?)\]|"([^"]+)"),?$', re.M | re.S)

findings = []
notes = []


def fail(check, message):
    findings.append((check, message))


def note(check, message):
    notes.append((check, message))


def read(path):
    with open(path) as f:
        return f.read()


ASSIGN = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', re.M)
COMMENT = re.compile(r'//[^\n]*')


def split_elements(text):
    """Split a Blueprint list body on the commas outside quotes."""
    out, current, quoted = [], '', False
    for char in text:
        if char == '"':
            quoted = not quoted
        if char == ',' and not quoted:
            out.append(current)
            current = ''
        else:
            current += char
    out.append(current)
    return [element.strip() for element in out if element.strip()]


def resolve_value(expr, variables):
    """The string a Blueprint expression evaluates to, or None.

    Read character by character: splitting on `+` tears a path that contains one.
    """
    parts, i = [], 0
    while i < len(expr):
        char = expr[i]
        if char.isspace() or char == '+':
            i += 1
        elif char == '"':
            end = expr.find('"', i + 1)
            if end < 0:
                return None
            parts.append(expr[i + 1:end])
            i = end + 1
        else:
            word = re.match(r'[A-Za-z_][A-Za-z0-9_]*', expr[i:])
            if not word or word.group(0) not in variables:
                return None
            parts.append(variables[word.group(0)])
            i += len(word.group(0))
    return ''.join(parts)


def bp_variables(text):
    """Top level `name = "value"` assignments, concatenations resolved."""
    raw = dict(ASSIGN.findall(COMMENT.sub('', text)))
    resolved = {}
    for _ in range(3):
        for name, value in raw.items():
            got = resolve_value(value, resolved)
            if got is not None:
                resolved[name] = got
    return resolved


def bp_list(text, prop, variables):
    """The strings in a `prop: [...]` list, variables and concatenations resolved."""
    found = re.search(prop + r':\s*\[(.*?)\]', text, re.S)
    if not found:
        return []
    body = COMMENT.sub('', found.group(1))
    return [value for value in
            (resolve_value(element, variables) for element in split_elements(body))
            if value]


def parse_bp(path, quiet=False):
    """Return {module_name: {type, srcs, defaults, vendor, ...}}."""
    modules = {}
    variables = bp_variables(read(path))
    lines = read(path).splitlines()
    i = 0
    while i < len(lines):
        m = MODULE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        mtype = m.group(1)
        depth = 1
        i += 1
        body = []
        while i < len(lines) and depth > 0:
            depth += lines[i].count('{') - lines[i].count('}')
            if depth > 0:
                body.append(lines[i])
            i += 1
        text = '\n'.join(body)
        found = re.search(r'name: "([^"]+)"', text)
        if not found:
            continue
        name = found.group(1)
        # srcs: [ ... ] for multi arch, src: "..." and srcs: "..." for single
        srcs = []
        for array, single in re.findall(
                r'^\s*(?:srcs?|jars): (?:\[(.*?)\]|"([^"]+)")', text, re.M | re.S):
            if array:
                srcs += [value for value in
                         (resolve_value(element, variables)
                          for element in split_elements(COMMENT.sub('', array)))
                         if value]
            else:
                srcs.append(single)
        libs = {prop: bp_list(text, prop, variables)
                for prop in LIBS + ('header_libs',)}
        info = {
            'type': mtype,
            'srcs': srcs,
            **libs,
            'defaults': bp_list(text, 'defaults', variables),
            'imports': bp_list(text, 'imports', variables),
            'langs': bp_list(text, 'langs', variables),
            'vendor': bool(re.search(
                r'^\s*(vendor|proprietary|soc_specific): true,?$', text, re.M)),
            'vendor_available': 'vendor_available: true' in text,
            'installed_location': (
                re.search(r'installed_location: "([^"]+)"', text) or [None, None]
            )[1],
            'symlink_target': (
                re.search(r'symlink_target: "([^"]+)"', text) or [None, None]
            )[1],
        }
        if name in modules and not quiet:
            fail('P2', f'{path}: module "{name}" defined twice')
        modules[name] = info
    return modules


def prop_flag(modules, name, prop, seen=None):
    """Is a boolean property set, on the module or on a defaults it inherits?"""
    if name not in modules:
        return False
    seen = seen if seen is not None else set()
    if name in seen:
        return False
    seen.add(name)
    if modules[name][prop]:
        return True
    return any(prop_flag(modules, d, prop, seen) for d in modules[name]['defaults'])


def vendor_flag(modules, name, seen=None):
    """Is a module vendor specific, directly or through its defaults chain?"""
    return prop_flag(modules, name, 'vendor', seen)


def lib_versions(modules, lib, cache=None, stack=None):
    """What declaring one library pulls in, its own frozen version included."""
    for pattern in (VERSIONED, SOURCE):
        found = pattern.match(lib)
        if not found:
            continue
        iface = found.group('iface')
        reach = {(iface, found.group('lang')): {found.group('version')}}
        # the interface's own imports are baked into every version of it
        base = modules.get(iface)
        if base and base['type'] == 'aidl_interface':
            for key, versions in aidl_versions(modules, iface, cache, stack).items():
                reach.setdefault(key, set()).update(versions)
        return reach
    return aidl_versions(modules, lib, cache, stack)


def imported_versions(info):
    """A versioned `imports` entry, expanded over the backends it applies to."""
    if info['type'] != 'aidl_interface':
        return
    for entry in info['imports']:
        found = re.match(r'^(?P<iface>.+)-V(?P<version>\d+)$', entry)
        if not found:
            continue
        for lang in info['langs'] or LANGS:
            yield found.group('iface'), lang, found.group('version')


def aidl_versions(modules, name, cache=None, stack=None):
    """Every frozen AIDL version a module can reach, keyed interface and backend.

    Soong stores the version under `interface-backend`, so V1-cpp beside V2-ndk
    is legal and V1-ndk beside V2-ndk is not. The libs, the defaults chain, an
    `imports` entry and a `srcs: [":module"]` reference all carry it.
    """
    cache = {} if cache is None else cache
    stack = set() if stack is None else stack
    if name in cache:
        return cache[name]
    if name in stack or name not in modules:
        return {}
    stack.add(name)
    found = {}
    info = modules[name]
    for iface, lang, version in imported_versions(info):
        found.setdefault((iface, lang), set()).add(version)
    for dep in ([l for prop in LIBS for l in info[prop]] + info['defaults']
                + [s[1:] for s in info['srcs'] if s.startswith(':')]):
        for key, versions in lib_versions(modules, dep, cache, stack).items():
            found.setdefault(key, set()).update(versions)
    stack.discard(name)
    cache[name] = found
    return found


TEST_TYPES = ('cc_test_library', 'android_test', 'cc_benchmark', 'cc_test')
MERGED_PROPS = ('shared_libs', 'static_libs', 'whole_static_libs', 'defaults',
                'srcs')


def prebuilt_union(ours, theirs):
    """What Soong checks when a prebuilt merges into the module of its name."""
    merged = dict(ours)
    for prop in MERGED_PROPS:
        merged[prop] = list(dict.fromkeys(ours[prop] + theirs[prop]))
    return merged


def check_p14(device_mods, vendor_mods, aosp_mods):
    """The aidl_interface version rule, as system/tools/aidl enforces it."""
    if not aosp_mods:
        note('P14', 'needs --aosp: which version a platform library links is '
                    'only knowable from the tree that builds it')
        return
    merged = {**aosp_mods, **device_mods, **vendor_mods}
    collisions = set()
    for name in set(device_mods) | set(vendor_mods):
        if name in aosp_mods:
            collisions.add(name)
            merged[name] = prebuilt_union(merged[name], aosp_mods[name])
    cache = {}
    for name in sorted(set(vendor_mods) | set(device_mods)):
        if merged[name]['type'] in TEST_TYPES:
            continue
        reached = aidl_versions(merged, name, cache)
        for (iface, lang), versions in sorted(reached.items()):
            if len(versions) < 2:
                continue
            direct = []
            for lib in merged[name]['shared_libs'] + merged[name]['whole_static_libs']:
                here = lib_versions(merged, lib, cache).get((iface, lang), set())
                if here:
                    direct.append(f'{lib}=V{"/V".join(sorted(here, key=int))}')
            note_merge = (f', merging with the platform module of the same name'
                          if name in collisions else '')
            fail('P14', f'"{name}" reaches {iface} ({lang}) at '
                        f'V{" and V".join(sorted(versions, key=int))} at once, '
                        f'through {", ".join(direct) or "its own libs"}{note_merge}')


def aosp_counterpart(name, aosp_mods):
    """The AOSP module a Soong module name was generated from, if any.

    aidl_interface and hidl_interface blocks generate the cc modules Soong
    sees, so a name like android.hardware.security.keymint-V1-ndk appears in no
    Android.bp while the block it comes from does.
    """
    if name in aosp_mods:
        return name
    m = re.match(r'(.+?)(-V[0-9]+)?-(cpp|ndk|rust|java)$', name)
    if m:
        for candidate in (m.group(1), m.group(1) + '_interface'):
            if candidate in aosp_mods:
                return candidate
    return None


def parse_blob_list(path):
    """Blob entries, their SYMLINK targets, and the copy-rule-only ones."""
    files, symlinks, copy_only = {}, {}, set()
    for line in read(path).splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(';')
        blob = parts[0].lstrip('-')
        files[blob] = line
        for arg in parts[1:]:
            if arg.startswith('SYMLINK='):
                for target in arg[len('SYMLINK='):].split(','):
                    if target in symlinks:
                        fail('P6', f'{path}: symlink target "{target}" declared twice')
                    symlinks[target] = blob
            elif arg == 'MAKE_COPY_RULE_ONLY':
                copy_only.add(blob)
    return files, symlinks, copy_only


def parse_product_vars(path, var):
    """The entries of a PRODUCT_<var> += block."""
    out = []
    collecting = False
    for line in read(path).splitlines():
        stripped = line.strip()
        if not collecting:
            if stripped.startswith(f'PRODUCT_{var} +='):
                collecting = True
                stripped = stripped.split('+=', 1)[1].strip()
                if not stripped:
                    continue
            else:
                continue
        if not stripped:
            collecting = False
            continue
        if stripped.endswith('\\'):
            stripped = stripped[:-1].strip()
        if stripped and not stripped.startswith('$'):
            out.append(stripped)
    return out


def parse_copy_files(path, var='COPY_FILES'):
    pairs = []
    for entry in parse_product_vars(path, var):
        if ':' not in entry:
            fail('P4', f'{path}: copy entry without a colon: {entry}')
            continue
        src, dst = entry.split(':', 1)
        pairs.append((src.strip(), dst.strip()))
    return pairs


def vendor_path(repo, blob):
    """A blob list path is <partition>/<subpath> and is extracted to proprietary/."""
    return os.path.join(repo, 'proprietary', blob)


def main():
    global DEVICE, VENDOR
    ap = argparse.ArgumentParser()
    ap.add_argument('--aosp', action='append', default=[])
    ap.add_argument('--stock', default='/tmp/sysmnt')
    ap.add_argument('--device', default=DEVICE, help='override, for older revisions')
    ap.add_argument('--vendor', default=VENDOR, help='override, for older revisions')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    DEVICE, VENDOR = args.device, args.vendor

    dev_bp = os.path.join(DEVICE, 'Android.bp')
    ven_bp = os.path.join(VENDOR, 'Android.bp')
    ven_mk = os.path.join(VENDOR, 'Z2577-vendor.mk')
    dev_mk = os.path.join(DEVICE, 'device.mk')
    blob_list = os.path.join(DEVICE, 'proprietary-files.txt')

    device_mods = parse_bp(dev_bp)
    vendor_mods = parse_bp(ven_bp)

    for path in (dev_bp, ven_bp):
        for name in parse_bp(path, quiet=True):
            if not LEGAL_NAME.match(name):
                fail('P1', f'{path}: illegal module name "{name}"')

    for name in sorted(set(device_mods) & set(vendor_mods)):
        fail('P2', f'module "{name}" defined in both Android.bp files')

    for repo, mods in ((DEVICE, device_mods), (VENDOR, vendor_mods)):
        for name, info in mods.items():
            for src in info['srcs']:
                if not os.path.exists(os.path.join(repo, src)):
                    fail('P3', f'{name}: source "{src}" missing in {repo}')

    # the AOSP corpus, read once, used by P5 and P11
    aosp_mods, paths = {}, {}
    for root_dir in args.aosp:
        for root, dirs, names in os.walk(root_dir):
            if 'Android.bp' not in names:
                continue
            path = os.path.join(root, 'Android.bp')
            for name, info in parse_bp(path, quiet=True).items():
                if name not in aosp_mods:
                    aosp_mods[name] = info
                    paths[name] = path

    # P4, copy sources
    dev_copies = parse_copy_files(dev_mk)
    ven_copies = parse_copy_files(ven_mk)
    for src, dst in dev_copies + ven_copies:
        if src.startswith('$(LOCAL_PATH)'):
            real = src.replace('$(LOCAL_PATH)', DEVICE)
        elif src.startswith('$(DEVICE_PATH)'):
            real = src.replace('$(DEVICE_PATH)', DEVICE)
        elif src.startswith('vendor/nubia/Z2577/'):
            real = os.path.join(VENDOR, src[len('vendor/nubia/Z2577/'):])
        else:
            real = os.path.join(VENDOR, src)
        if not os.path.exists(real):
            fail('P4', f'copy source missing: {src}')

    # P5, the vendor repo must resolve; device.mk against the corpus, a miss is a note.
    for entry in parse_product_vars(ven_mk, 'PACKAGES'):
        if entry not in vendor_mods:
            fail('P5', f'PRODUCT_PACKAGES entry "{entry}" is not a module in '
                        f'the vendor repo')
    for entry in parse_product_vars(dev_mk, 'PACKAGES'):
        if entry in vendor_mods or entry in device_mods or entry in aosp_mods:
            continue
        note('P5', f'device.mk names "{entry}", not in the AOSP corpus here')

    # P6, blob list against the vendor repo, both directions
    files, symlinks, copy_only = parse_blob_list(blob_list)
    for blob in files:
        if not os.path.exists(vendor_path(VENDOR, blob)):
            fail('P6', f'blob list entry has no file: {blob}')
    on_disk = set()
    root_dir = os.path.join(VENDOR, 'proprietary')
    for root, dirs, names in os.walk(root_dir):
        for name in names:
            on_disk.add(os.path.relpath(os.path.join(root, name), root_dir))
    for stray in sorted(on_disk - set(files)):
        fail('P6', f'file in the vendor repo but not in the blob list: {stray}')

    # P7, every blob lands in a module or a copy rule
    landed = set()
    for info in vendor_mods.values():
        for src in info['srcs']:
            landed.add(src.removeprefix('proprietary/'))
    for info in device_mods.values():
        for src in info['srcs']:
            landed.add(src)
    for src, dst in ven_copies:
        landed.add(src.removeprefix('vendor/nubia/Z2577/proprietary/'))
    for src, dst in dev_copies:
        landed.add(src.replace('$(LOCAL_PATH)/', '').replace('$(DEVICE_PATH)/', ''))
    for blob in files:
        if blob not in landed:
            fail('P7', f'blob list entry lands in no module or copy rule: {blob}')

    # P8, install_symlink targets
    stock_names = set()
    for root, dirs, names in os.walk(args.stock):
        stock_names.update(names)
    for name, info in vendor_mods.items():
        if info['type'] != 'install_symlink':
            continue
        target = info['symlink_target']
        if not target:
            fail('P8', f'{name}: symlink without a target')
        elif target.startswith('/vendor_dlkm/'):
            continue
        elif os.path.exists(vendor_path(VENDOR, target.lstrip('/'))):
            continue
        elif os.path.basename(target) in stock_names:
            continue
        else:
            fail('P8', f'{name}: symlink target {target} resolves to nothing we ship')

    # P9, $(DEVICE_PATH) references
    for path in (os.path.join(DEVICE, 'BoardConfig.mk'), dev_mk):
        for ref in re.findall(
                r'\$\((?:DEVICE_PATH|LOCAL_PATH)\)/([A-Za-z0-9_./-]+)', read(path)):
            if not os.path.exists(os.path.join(DEVICE, ref)):
                fail('P9', f'{path}: reference to missing file {ref}')

    # P10, copy destination collisions
    dests = defaultdict(set)
    for src, dst in dev_copies + ven_copies:
        dests[dst].add(src)
    for dst, srcs in sorted(dests.items()):
        if len(srcs) > 1:
            fail('P10', f'destination {dst} written by {len(srcs)} sources: '
                        f'{", ".join(sorted(srcs))}')

    STATIC_ONLY = ('cc_library_static', 'cc_prebuilt_library_static',
                   'cc_library_headers')

    # P11, names AOSP also uses; vendor_available is what gives it a vendor variant.
    for name in sorted(vendor_mods):
        source = aosp_counterpart(name, aosp_mods)
        if source is None or vendor_flag(aosp_mods, source):
            continue
        info = aosp_mods[source]
        rel = paths[source].split('refs/', 1)[-1].split('/tmp/', 1)[-1]
        # An interface block without the flag generates a system only library, so ours stays.
        if not prop_flag(aosp_mods, source, 'vendor_available'):
            note('P11', f'module "{name}" replaces the AOSP module "{source}" '
                        f'({rel}) which has no vendor variant, so the prebuilt '
                        f'is the only source and stays')
        elif (vendor_mods[name]['type'] == 'cc_prebuilt_library_shared'
                and info['type'] in STATIC_ONLY):
            # P13, the platform builds it static only, so ours carries another name.
            fail('P13', f'module "{name}" is shared while the AOSP module '
                        f'"{source}" is {info["type"]} only ({rel}); give it '
                        f'a name of its own with ;MODULE= and repoint its '
                        f'dependants in extract-files.py lib_fixups')
        else:
            note('P11', f'module "{name}" also names an AOSP module "{source}" '
                        f'({rel}); with no prefer the platform copy is the one '
                        f'used and installed')

    # P12, the prefer flags setup-makefiles.py drops after generating
    for label, path in (('device', dev_bp), ('vendor', ven_bp)):
        n = len(re.findall(r'^    prefer: true,$', read(path), re.M))
        if n:
            fail('P12', f'{label} Android.bp: {n} prebuilt modules still carry '
                        f'prefer: true, which makes each one claim the AOSP '
                        f'module of the same name; run setup-makefiles.py')

    check_p14(device_mods, vendor_mods, aosp_mods)

    for check, message in findings:
        print(f'{check}: {message}')
    for check, message in notes:
        print(f'{check}: note: {message}')
    print(f'\n{len(findings)} findings, {len(notes)} notes')
    return 1 if findings else 0


FAIL1 = """
cc_library {
    name: "foo",
    shared_libs: ["myiface-V2-ndk", "bar"],
}

cc_library {
    name: "bar",
    shared_libs: ["myiface-V1-ndk"],
}
"""

FAIL2 = """
aidl_interface {
    name: "myiface",
    srcs: ["IFoo.aidl"],
    versions: ["1"],
}

aidl_interface {
    name: "myiface2",
    srcs: ["IBar.aidl"],
    imports: ["myiface-V2"],
}

cc_library {
    name: "foobar",
    shared_libs: ["myiface-V1-ndk", "myiface2-V1-ndk"],
}
"""

FAIL3 = """
aidl_interface {
    name: "myiface",
    srcs: ["IFoo.aidl"],
    versions: ["1"],
}

aidl_interface {
    name: "myiface2",
    srcs: ["IBar.aidl"],
    imports: ["myiface-V2"],
}

cc_library {
    name: "foobar",
    srcs: [":myiface-V1-ndk-source"],
    shared_libs: ["myiface2-V1-ndk"],
}
"""

PASS4 = """
aidl_interface {
    name: "myiface",
    srcs: ["IFoo.aidl"],
    versions: ["1"],
}

cc_library {
    name: "foobar",
    shared_libs: ["myiface-V1-cpp", "myiface-V1-ndk"],
}
"""

PASS5 = """
aidl_interface {
    name: "myiface",
    srcs: ["IFoo.aidl"],
    versions: ["1"],
}

aidl_interface {
    name: "myiface2",
    srcs: ["IBar.aidl"],
    imports: ["myiface-V2"],
}

cc_library {
    name: "foobar",
    srcs: [":myiface-V2-ndk-source"],
    shared_libs: ["myiface2-V1-ndk"],
}
"""

CASES = (
    ('indirect dependency', FAIL1, 'foo', 1),
    ('versioned import', FAIL2, 'foobar', 1),
    ('srcs module reference', FAIL3, 'foobar', 1),
    ('same version, two backends', PASS4, None, 0),
    ('import and srcs agree', PASS5, None, 0),
)


def selftest():
    """The P14 rule against the fixtures system/tools/aidl tests it with."""
    bad = 0
    for label, source, module, count in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'Android.bp')
            with open(path, 'w') as handle:
                handle.write(source)
            mods = parse_bp(path, quiet=True)
        findings.clear()
        notes.clear()
        check_p14(mods, {}, mods)
        found = [message for check, message in findings if check == 'P14']
        ok = len(found) == count and (not module or all(
            f'"{module}"' in message and 'myiface (ndk)' in message
            for message in found))
        print(f'{"ok  " if ok else "FAIL"} {label}: {len(found)} finding(s)')
        bad += 0 if ok else 1
    print(f'{len(CASES) - bad}/{len(CASES)} cases as upstream behaves')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
