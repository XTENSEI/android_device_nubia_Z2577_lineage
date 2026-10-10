#!/usr/bin/env python3
"""Compare the stock vendor VINTF declarations against the platform FCMs."""

import glob
import os
import xml.etree.ElementTree as ET

VENDOR = '/home/andrei/romtools/WORK/rom/src/stock/vendor/etc/vintf'
PLATFORM = '/tmp/sysmnt/system/etc/vintf'


def parse(path):
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        print(f'  ! {path}: {exc}')
        return None


def hals_of(root):
    out = []
    for hal in root.iter('hal'):
        name = hal.findtext('name')
        if not name:
            continue
        versions = [v.text for v in hal.findall('version')]
        interfaces = [(i.findtext('name'), i.findtext('instance'))
                      for i in hal.findall('interface')]
        fqnames = [f.text for f in hal.findall('fqname')]
        out.append((hal.get('format'), name, versions, interfaces,
                    fqnames, hal.get('optional')))
    return out


def main():
    print('### vendor declarations')
    vendor = []
    for path in [f'{VENDOR}/manifest.xml'] + sorted(glob.glob(f'{VENDOR}/manifest/*.xml')):
        root = parse(path)
        if root is None:
            continue
        found = hals_of(root)
        vendor.extend(found)
        for fmt, name, versions, interfaces, fqnames, _opt in found:
            detail = ','.join(versions) or '-'
            ifaces = ' '.join(f'{i}/{n}' for i, n in interfaces) or ' '.join(fqnames)
            print(f'  {fmt:5} {name:45} v{detail:8} {ifaces}')
    print(f'  ({len(vendor)} entries)')

    print('\n### platform coverage')
    names = sorted({name for _f, name, _v, _i, _fq, _o in vendor})
    covered, uncovered = [], []
    for name in names:
        entries = []
        for path in sorted(glob.glob(f'{PLATFORM}/compatibility_matrix.*.xml')):
            root = parse(path)
            if root is None:
                continue
            for fmt, pname, versions, interfaces, _fq, opt in hals_of(root):
                if pname == name:
                    entries.append((os.path.basename(path), fmt, versions, opt))
        (covered if entries else uncovered).append(name)
        if entries:
            short = sorted({(e[0], e[1], ','.join(e[2]) or '-') for e in entries})
            print(f'  {name:45} {short}')
    print('\n### not in any platform matrix')
    for name in uncovered:
        print(f'  {name}')
    print('\n### platform sepolicy elements')
    for path in sorted(glob.glob(f'{PLATFORM}/compatibility_matrix.2025*.xml')):
        root = parse(path)
        if root is None:
            continue
        sepolicy = root.find('sepolicy')
        print(f'  {os.path.basename(path)}: level={root.get("level")} '
              f'sepolicy={"yes" if sepolicy is not None else "no"} '
              f'children={[c.tag for c in sepolicy] if sepolicy is not None else "-"}')


if __name__ == '__main__':
    main()
