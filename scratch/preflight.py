#!/usr/bin/env python3
"""Everything the build would reject, checked before it runs.

The three VPS build cycles so far each found one error at a time. This runs the
same class of check over the whole tree at once, offline:

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
  P13 a shared prebuilt whose AOSP namesake is static only, which Soong
      cannot resolve and which has to be renamed
  P12 prebuilt prefer flags, which regeneration has to drop

Usage: preflight.py [--aosp /tmp/aosp ...] [--stock /tmp/sysmnt]
"""

import argparse
import os
import re
import sys
from collections import defaultdict

DEVICE = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
VENDOR = '/home/andrei/Downloads/Trees/vendor_nubia_Z2577_lineage'

LEGAL_NAME = re.compile(r'^[A-Za-z0-9_.@+-]+$')
MODULE_OPEN = re.compile(r'^([a-z_0-9]+) \{$')
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


def parse_bp(path, quiet=False):
    """Return {module_name: {type, srcs, defaults, vendor, ...}}."""
    modules = {}
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
                srcs += re.findall(r'"([^"]+)"', array)
            else:
                srcs.append(single)
        defaults = re.search(r'defaults: \[(.*?)\]', text, re.S)
        info = {
            'type': mtype,
            'srcs': srcs,
            'defaults': (
                re.findall(r'"([^"]+)"', defaults.group(1)) if defaults else []
            ),
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
    ap = argparse.ArgumentParser()
    ap.add_argument('--aosp', action='append', default=[])
    ap.add_argument('--stock', default='/tmp/sysmnt')
    args = ap.parse_args()

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

    for check, message in findings:
        print(f'{check}: {message}')
    for check, message in notes:
        print(f'{check}: note: {message}')
    print(f'\n{len(findings)} findings, {len(notes)} notes')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
