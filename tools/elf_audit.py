#!/usr/bin/env python3
"""Audit the Z2577 vendor blobs the way the build's ELF check will."""

import os
import sys
from collections import defaultdict

from elftools.elf.elffile import ELFFile
from elftools.elf.dynamic import DynamicSection
from elftools.common.exceptions import ELFError

LIST = '/home/andrei/Downloads/Trees/device_nubia_Z2577/proprietary-files.txt'
BASE = '/home/andrei/Downloads/Trees/vendor_nubia_Z2577_lineage/proprietary'
ROOTS = (os.path.join(BASE, 'vendor'), os.path.join(BASE, 'odm'))
# Libs the platform itself provides, so a vendor blob may depend on them.
PLATFORM_PREFIXES = (
    'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libcutils.so', 'libutils.so',
    'libbase.so', 'libhardware.so', 'libbinder.so', 'libbinder_ndk.so',
    'libhidlbase.so', 'libhidltransport.so', 'libhwbinder.so', 'libhwbinder_noltopgo.so',
    'libutils.so', 'libui.so', 'libgui.so', 'libEGL.so', 'libGLESv1_CM.so',
    'libGLESv2.so', 'libvulkan.so', 'libnativewindow.so', 'libsync.so',
    'libc++.so', 'libc++_shared.so', 'libstdc++.so', 'libz.so', 'libziparchive.so',
    'libtinyxml2.so', 'libjsoncpp.so', 'libexpat.so', 'libsqlite.so',
    'libnetd_client.so', 'libprocessgroup.so', 'libselinux.so', 'libpackagelistparser.so',
    'libprocinfo.so', 'libcgrouprc.so', 'libprotobuf-cpp-lite.so', 'libprotobuf-cpp-full.so',
    'libion.so', 'libdm.so', 'libsysutils.so', 'libmemtrack.so', 'libnl.so',
    'libpcre2.so', 'libyuv.so', 'libcrypto.so', 'libssl.so', 'libkeystore-engine.so',
    'android.hardware.graphics.common-V2-ndk.so',
    'android.hardware.graphics.common-V3-ndk.so',
    'android.hardware.graphics.allocator-V1-ndk.so',
    'android.hardware.graphics.allocator-V2-ndk.so',
    'android.hardware.graphics.mapper@4.0.so', 'libgralloctypes.so',
    'libvndksupport.so', 'libvintf.so', 'libcap.so', 'libaudit.so',
    'libstagefright_foundation.so', 'libmedia_omx.so', 'libstagefright.so',
    'libmedia.so', 'libaudioclient.so', 'libsoundtrigger.so', 'libsonic.so',
    'libavservices_minijail.so', 'libavservices_minijail_vendor.so',
    'libkver.so', 'libusbhost.so', 'libsuspend.so', 'libboot_control_client.so',
)
# Private namespaces on this vendor, a missing one is a missing blob, not a platform lib.
UNISOC_PREFIXES = ('libsprd', 'libzte', 'libunisoc', 'libums', 'libtran', 'libengpc',
                   'libatci', 'libpcmlib', 'libsku', 'libmodem', 'librf')


def soname_and_needed(path):
    with open(path, 'rb') as fh:
        elf = ELFFile(fh)
        soname = None
        needed = []
        for section in elf.iter_sections():
            if isinstance(section, DynamicSection):
                for tag in section.iter_tags():
                    if tag.entry.d_tag == 'DT_SONAME':
                        soname = tag.soname
                    elif tag.entry.d_tag == 'DT_NEEDED':
                        needed.append(tag.needed)
        return elf['e_type'], soname, needed


def main():
    libs, not_elf, scripts = {}, [], []
    provided = set()
    for root in ROOTS:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                provided.add(name)

    for root in ROOTS:
      for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith('.so') and not name.endswith('.so.*'):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, BASE)
            with open(path, 'rb') as fh:
                magic = fh.read(4)
            if magic != b'\x7fELF':
                (scripts if magic[:2] in (b'#!', b'/*', b'IN') or b'INPUT' in magic
                 else not_elf).append(rel)
                continue
            try:
                etype, soname, needed = soname_and_needed(path)
            except ELFError as exc:
                not_elf.append(f'{rel} ({exc})')
                continue
            libs[rel] = (etype, soname, needed)

    print(f'shared objects parsed: {len(libs)}')
    print(f'not ELF: {len(not_elf)}')
    for rel in not_elf[:40]:
        print(f'  {rel}')
    print(f'linker scripts / other text: {len(scripts)}')
    for rel in scripts[:20]:
        print(f'  {rel}')

    missing_soname, mismatch = [], []
    for rel, (_etype, soname, _needed) in sorted(libs.items()):
        base = os.path.basename(rel)
        if soname is None:
            missing_soname.append(rel)
        elif soname != base:
            mismatch.append((rel, soname))

    print(f'\nSONAME missing: {len(missing_soname)}')
    for rel in missing_soname[:60]:
        print(f'  {rel}')
    fixed = set()
    for line in open(LIST, encoding='utf-8'):
        entry = line.strip()
        if entry and not entry.startswith('#') and ';FIX_SONAME' in entry:
            fixed.add(entry.split(';', 1)[0].lstrip('-'))
    print(f'\nSONAME mismatch: {len(mismatch)}')
    uncovered = []
    for rel, soname in mismatch[:80]:
        if rel in fixed:
            print(f'  {rel}  ->  {soname}  (FIX_SONAME)')
        else:
            uncovered.append(rel)
            print(f'  {rel}  ->  {soname}')
    print(f'mismatches with no FIX_SONAME in the list: {len(uncovered)}')

    deps = defaultdict(list)
    for rel, (_e, _s, needed) in libs.items():
        for dep in needed:
            deps[dep].append(rel)
    unresolved = []
    for dep, users in sorted(deps.items()):
        if dep in provided or dep in PLATFORM_PREFIXES:
            continue
        if dep.startswith(UNISOC_PREFIXES):
            unresolved.append((dep, users))
    print(f'\nUnisoc private deps with no provider in the blobs: {len(unresolved)}')
    for dep, users in unresolved[:40]:
        print(f'  {dep}  used by {len(users)} blob(s), e.g. {users[0]}')


if __name__ == '__main__':
    main()
