#!/usr/bin/env python3
"""Replay the DT_NEEDED half of Soong's check_elf_file over every prebuilt.

The symbol half resolves against the export list of every declared lib, and
those lists only exist once the platform is built, so it is not checkable here.
The DT_NEEDED half is: the module has to declare the soname of every library it
links, and the soname is the output name of the module behind it, not the module
name, which is why a declared dep can satisfy a soname it does not equal.

Usage: check_elf_prebuilts.py [--bp PATH] [--quiet]
"""

import os
import re
import subprocess
import sys

VENDOR_BP = '/home/andrei/Downloads/Trees/vendor_nubia_Z2577_lineage/Android.bp'

# check_elf_file never asks about these
IMMUTABLE = {'libc.so', 'libm.so', 'libdl.so', 'libstdc++.so'}

TYPES = ('cc_prebuilt_library_shared', 'cc_prebuilt_binary')

VARIANT = re.compile(
    r'^\s*(android_arm64|android_arm|arm64|arm)\w*:\s*\{\s*$', re.M)


def balanced(lines, start):
    """Index of the line that closes the block opened at `start`."""
    depth = 0
    for end in range(start, len(lines)):
        depth += lines[end].count('{') - lines[end].count('}')
        if depth <= 0:
            return end
    return len(lines) - 1


def modules(text):
    """Every module block of a type the check runs on, variants split out."""
    lines = text.splitlines()
    out = []
    at = 0
    while at < len(lines):
        head = lines[at].strip()
        kind = head.split('{')[0].strip()
        if kind in TYPES and head.endswith('{'):
            end = balanced(lines, at)
            body = lines[at:end + 1]
            out.append((kind, body))
            at = end + 1
            continue
        at += 1
    return out


def str_prop(text, prop):
    found = re.search(rf'^\s*{prop}:\s*"([^"]+)"', text, re.M)
    return found.group(1) if found else None


def list_prop(text, prop):
    found = re.search(rf'^\s*{prop}:\s*\[(.*?)\]', text, re.M | re.S)
    if not found:
        return []
    return re.findall(r'"([^"]+)"', found.group(1))


def variants(body):
    """(label, src, shared_libs) per architecture block, or the module level."""
    text = '\n'.join(body)
    heads = list(VARIANT.finditer(text))
    if not heads:
        return [('all', str_prop(text, 'src'),
                 list_prop(text, 'shared_libs'))]
    out = []
    lines = text.splitlines()
    for found in heads:
        start = text[:found.start()].count('\n')
        end = balanced(lines, start)
        block = '\n'.join(lines[start:end + 1])
        srcs = list_prop(block, 'srcs') or [
            s for s in [str_prop(block, 'src')] if s]
        out.append((found.group(1), srcs, list_prop(block, 'shared_libs')))
    return out


def readelf(args, path):
    r = subprocess.run(['readelf', *args, path], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ''


def elf_info(path):
    """SONAME, DT_NEEDED list and the dynamic symbol table of one ELF."""
    soname = None
    needed = []
    for line in readelf(['-dW'], path).splitlines():
        if 'SONAME' in line:
            soname = line.split('[')[1].split(']')[0]
        elif 'NEEDED' in line:
            needed.append(line.split('[')[1].split(']')[0])

    defined, undefined = set(), set()
    for line in readelf(['--dyn-syms', '-W'], path).splitlines():
        parts = line.split()
        if len(parts) < 8 or not parts[0].endswith(':') or parts[6] == 'UND':
            if len(parts) >= 8 and parts[0].endswith(':') and parts[6] == 'UND':
                undefined.add(parts[7].split('@')[0])
            continue
        defined.add(parts[7].split('@')[0])
    return soname or os.path.basename(path), needed, defined, undefined


SUFFIXES = ('-vendorcompat', '-vendor', '-odm', '_vendor')


def declares(dep, soname):
    """Does a declared module name account for this DT_NEEDED soname?

    A module's output carries a stem the name does not show: clang's runtime is
    `libclang_rt.ubsan_standalone-<arch>-android`, protobuf's vendorcompat
    module loses the suffix, and the boot impl is named for the version it
    implements last, not the one it is built at.
    """
    base = soname[:-3] if soname.endswith('.so') else soname
    for candidate in (dep, *(dep[:-len(s)] for s in SUFFIXES
                            if dep.endswith(s))):
        if base == candidate or base.startswith(candidate) \
                or candidate.startswith(base):
            return True
    return False


def main():
    bp = VENDOR_BP
    quiet = '--quiet' in sys.argv
    if '--bp' in sys.argv:
        bp = sys.argv[sys.argv.index('--bp') + 1]
    here = os.path.dirname(os.path.abspath(bp))

    declared_sonames = {}
    exports = {}
    jobs = []
    for kind, body in modules(open(bp).read()):
        text = '\n'.join(body)
        name = str_prop(text, 'name')
        stem = str_prop(text, 'stem')
        no_check = 'check_elf_files: false' in text
        no_syms = 'allow_undefined_symbols: true' in text
        for label, srcs, libs in variants(body):
            for src in srcs:
                path = os.path.join(here, src)
                if not os.path.exists(path):
                    continue
                soname, needed, defined, undefined = elf_info(path)
                declared_sonames.setdefault(name, set()).add(soname)
                exports[soname] = defined
                jobs.append((kind, name, label, src, stem, libs, no_check, no_syms,
                             soname, needed, defined, undefined))

    undeclared = []
    mismatched = []
    platform_only = 0
    for (kind, name, label, src, stem, libs, no_check, no_syms,
         soname, needed, defined, undefined) in jobs:
        if no_check:
            continue
        installed = (stem + '.so') if stem else os.path.basename(src)
        if kind == 'cc_prebuilt_library_shared' and soname != installed:
            mismatched.append((name, label, installed, soname))
        missing = [d for d in needed if d not in IMMUTABLE
                   and not any(declares(dep, d) for dep in libs)]
        if missing:
            undeclared.append((name, label, src, missing))

        declared = {soname for dep in libs
                    for soname in declared_sonames.get(dep, {dep + '.so'})}
        known = set(defined)
        for dep in declared & exports.keys():
            known |= exports[dep]
        if not no_syms:
            platform_only += len(undefined - known)

    total = len(jobs)
    print(f'ELF files checked : {total} of {len(declared_sonames)} modules')
    print(f'undeclared DT_NEEDED: {len(undeclared)}')
    for name, label, src, missing in undeclared:
        print(f'  {name} [{label}]  {src}')
        for soname in missing:
            print(f'    {soname}')
    print(f'DT_SONAME not the installed name: {len(mismatched)}')
    for name, label, installed, soname in mismatched:
        print(f'  {name} [{label}]  file {installed}  soname {soname}')
    print(f'undefined symbols left to the platform: {platform_only}')
    return 1 if undeclared or mismatched else 0


if __name__ == '__main__':
    sys.exit(main())
