#!/usr/bin/env python3
# Enumerate the prebuilts whose name the platform takes, one Soong replay per name.

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / 'shadow-findings.txt'
SUFFIXES = ('_vendor', '_Z2577')

# The shape Soong prints for a module that has no variant in a requested image.
ERROR = re.compile(
    r'dependency "(?P<dep>[^"]+)" of "(?P<depender>[^"]+)" missing variant:\n'
    r'  (?P<variant>[^\n]+)'
)

# The other shape, a dependency path that cannot reach its last node.
ERROR_LINE = re.compile(r'^error: (.+)$')
CHAIN_LINE = re.compile(r'^\s+-> (.+)$')
MODULE_IN = re.compile(r'module "([^"]+)"')

NAME = '    name: "%s",'
SRC = re.compile(r'^\s*"proprietary/([^"]+)",$', re.M)
NAME_LINE = re.compile(r'^    name: "([^"]+)",$')
BOOL_LINE = re.compile(r'^    ([a-z_]+): true,$')
LIST_HEAD = re.compile(r'^    (shared_libs|static_libs|whole_static_libs|header_libs): \[$')
LIST_ENTRY = re.compile(r'^\s*"([^"]+)",$')
MODULE_START = re.compile(r'^([a-z][a-z0-9_]*)\s*\{$')

# The flags Soong splits an image off a module by, and where each one installs.
IMAGE_FLAGS = {'vendor', 'proprietary', 'soc_specific', 'vendor_available',
               'system_ext_specific'}
VENDOR_FLAGS = {'vendor', 'proprietary', 'soc_specific', 'vendor_available'}

# Platform roots, for a tree with no built module list to read.
PLATFORM_ROOTS = ('system', 'system_ext', 'product', 'hardware', 'frameworks',
                  'packages', 'vendor', 'device')

ITEM = re.compile(
    r'^(?P<dep>\S+) -> (?P<module>\S+)'
    r'(?:\s+\(stem (?P<stem>[^)]*)\))?\s*$'
)
DEPENDANT = re.compile(r'^\s*dependant (?P<depender>.+), requested (?P<variant>.+)$')
LIVES = re.compile(r'^\s*module lives in (?P<file>.+)$')


def log(message: str) -> None:
    print(message, flush=True)


def find_top(start: pathlib.Path) -> pathlib.Path | None:
    """The AOSP root, which is not the device tree's own git root."""
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / 'build/envsetup.sh').exists() and (
            candidate / 'out/host/linux-x86/bin/soong_build'
        ).is_file():
            return candidate
    return None


def canonical_name(name: str) -> str:
    """Pick the suffix form that already exists in the generated vendor Android.bp."""
    found = defined_modules(HERE.parent)
    if name + '_vendor' in found:
        return name + '_vendor'
    if name + '_Z2577' in found:
        return name + '_Z2577'
    return name


def defined_modules(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Every module name the two trees generate, and the file that declares it."""
    found: dict[str, pathlib.Path] = {}
    files = [root / 'vendor/nubia/Z2577/Android.bp']
    files += sorted((root / 'device/nubia/Z2577').glob('**/Android.bp'))
    for path in files:
        if not path.is_file():
            continue
        for m in re.finditer(r'^    name: "([^"]+)",$', path.read_text(), re.M):
            found.setdefault(m.group(1), path)
    return found


def stem_of(text: str, name: str) -> str | None:
    """The file name a generated module installs as, which is what ;MODULE= keeps."""
    span = module_span(text, name)
    if span is None:
        return None
    block = ''.join(text.splitlines(keepends=True)[span[0] : span[1]])
    src = SRC.search(block)
    if src is None:
        return None
    return pathlib.PurePosixPath(src.group(1)).name.split('.so')[0]


def module_span(text: str, name: str) -> tuple[int, int] | None:
    marker = NAME % name
    if marker not in text:
        return None
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.rstrip('\n') == marker)
    for end in range(start + 1, len(lines)):
        if lines[end].startswith('}'):
            return start, end
    return None


def rename(text: str, old: str, new: str, stem: str) -> str:
    """The module edit extract-utils makes for ;MODULE=, applied by hand."""
    lines = text.splitlines(keepends=True)
    span = module_span(text, old)
    assert span is not None
    start, _ = span
    lines[start] = NAME % new + '\n'
    lines.insert(start + 1, f'    stem: "{stem}",\n')
    return ''.join(lines)


def repoint(text: str, old: str, new: str) -> str:
    pattern = re.compile(r'^(\s*)"%s",$' % re.escape(old), re.M)
    return pattern.sub(lambda m: f'{m.group(1)}"{new}",', text)


def images(flags: set[str]) -> set[str]:
    """The images a module installs into, read off the flags Soong splits on."""
    found: set[str] = set()
    if not flags & IMAGE_FLAGS or 'vendor_available' in flags:
        found.add('system')
    if flags & VENDOR_FLAGS:
        found |= {'vendor', 'odm'}
    if 'system_ext_specific' in flags:
        found.add('system_ext')
    return found or {'system'}


def parse_modules(text: str) -> list[dict]:
    """name, type, flags and library references of every module block in one file."""
    found: list[dict] = []
    cur: dict | None = None
    in_list = False
    for line in text.splitlines():
        if cur is None:
            if m := MODULE_START.match(line):
                cur = {'type': m.group(1), 'flags': set(), 'libs': set()}
            continue
        if line == '}':
            if 'name' in cur:
                found.append(cur)
            cur, in_list = None, False
            continue
        if m := NAME_LINE.match(line):
            cur['name'] = m.group(1)
        elif m := BOOL_LINE.match(line):
            cur['flags'].add(m.group(1))
        elif LIST_HEAD.match(line):
            in_list = True
        elif in_list:
            if line.strip() == ']':
                in_list = False
            elif m := LIST_ENTRY.match(line):
                cur['libs'].add(m.group(1))
    return found


def our_prebuilts(root: pathlib.Path) -> dict[str, tuple[str, set[str]]]:
    found: dict[str, tuple[str, set[str]]] = {}
    files = [root / 'vendor/nubia/Z2577/Android.bp']
    files += sorted((root / 'device/nubia/Z2577').glob('**/Android.bp'))
    for path in files:
        if not path.is_file():
            continue
        for mod in parse_modules(path.read_text(errors='replace')):
            if not mod['type'].startswith('cc_prebuilt_library'):
                continue
            found.setdefault(
                mod['name'],
                (str(path.relative_to(root)), images(mod['flags'])),
            )
    return found


def platform_files(top: pathlib.Path) -> list[pathlib.Path]:
    listing = top / 'out/.module_paths/Android.bp.list'
    if listing.is_file():
        paths = [top / line.strip() for line in listing.read_text().splitlines()
                 if line.strip()]
    else:
        paths = []
        for root in PLATFORM_ROOTS:
            base = top / root
            if base.is_dir():
                paths += sorted(base.rglob('Android.bp'))
    ours = (str(top / 'device/nubia/Z2577'), str(top / 'vendor/nubia/Z2577'))
    return [path for path in paths
            if path.is_file() and not str(path).startswith(ours)]


def reverse_pass(top: pathlib.Path) -> list[str]:
    """The mirror direction: platform modules that name one of our prebuilts."""
    ours = our_prebuilts(top)
    if not ours:
        return []
    matcher = re.compile('|'.join(
        re.escape(f'"{name}"') for name in sorted(ours, key=len, reverse=True)
    ))
    found: list[str] = []
    for path in platform_files(top):
        text = path.read_text(errors='replace')
        if not matcher.search(text):
            continue
        where = path.relative_to(top)
        for mod in parse_modules(text):
            mine = ours.get(mod['name'])
            if mine is not None:
                shared = images(mod['flags']) & mine[1]
                if shared:
                    found.append(
                        f'{mod["name"]}: the platform module in {where} and our '
                        f'prebuilt {mine[0]} both build {", ".join(sorted(shared))}'
                    )
            for lib in sorted(mod['libs'] & set(ours)):
                if not images(mod['flags']) & ours[lib][1]:
                    found.append(
                        f'{mod["name"]}: lists {lib} from {where}, which we ship '
                        f'only in {", ".join(sorted(ours[lib][1]))}'
                    )
    return found


def unmodelled(output: str) -> list[tuple[str, str, str]]:
    """Blueprint errors the sweep does not fix, deduplicated on the error text."""
    entries: list[tuple[str, str, str]] = []
    line_text: str | None = None
    root = ''
    for line in output.splitlines():
        if m := ERROR_LINE.match(line):
            if line_text is not None:
                entries.append((line_text, root, ''))
            line_text, root = m.group(1).strip(), ''
        elif line_text is not None and (m := CHAIN_LINE.match(line)):
            root = m.group(1).strip()
    if line_text is not None:
        entries.append((line_text, root, ''))

    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    for line_text, root, _ in entries:
        name = MODULE_IN.search(line_text)
        module = name.group(1) if name else ''
        found.setdefault((module, root), (line_text, root, module))
    return list(found.values())


def find_target(top: pathlib.Path, wanted: str) -> str:
    """The Kati suffix, which is the product name without Soong's extra pass."""
    variables = sorted((top / 'out/soong').glob('soong.*.variables'))
    names = [p.name[len('soong.') : -len('.variables')] for p in variables]
    if not names:
        sys.exit('no out/soong/soong.<target>.variables, run a build first')
    if wanted:
        if wanted not in names:
            sys.exit(f'{wanted} is not a built target, one of: {", ".join(names)}')
        return wanted
    primary = [name for name in names if not name.endswith('.extra')]
    if len(primary) == 1:
        return primary[0]
    if len(names) == 1:
        return names[0]
    sys.exit(f'several targets, pass --target: {", ".join(names)}')


def find_soong_build(top: pathlib.Path, wanted: str) -> pathlib.Path | None:
    if wanted:
        return pathlib.Path(wanted)
    for candidate in (top / 'out/host/linux-x86/bin/soong_build',
                      top / 'out/host/linux-x86/soong_ui'):
        if candidate.is_file():
            return candidate
    return None


def read_findings(report: pathlib.Path) -> list[dict[str, str]]:
    """A findings file back into items, ignoring what does not parse."""
    items: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    if not report.is_file():
        return items
    for line in report.read_text().splitlines():
        if m := ITEM.match(line):
            if cur:
                items.append(cur)
            cur = {'dep': m.group('dep'), 'module': m.group('module'),
                   'stem': (m.group('stem') or '').strip()}
            continue
        if cur is None:
            continue
        if m := DEPENDANT.match(line):
            cur['depender'] = m.group('depender')
            cur['variant'] = m.group('variant')
        elif m := LIVES.match(line):
            cur['file'] = m.group('file')
    if cur:
        items.append(cur)
    return items


def is_applied(item: dict[str, str]) -> bool:
    blobs = HERE.parent / 'proprietary-files.txt'
    if not blobs.is_file():
        return False
    stem = item['stem'] or item['dep']
    for line in blobs.read_text().splitlines():
        blob, _, args = line.partition(';')
        blob = pathlib.PurePosixPath(blob.lstrip('-*').strip()).name
        if blob == f'{stem}.so' and 'MODULE=' in args:
            return True
    return False


def carried_findings(found: list[dict[str, str]],
                     report: pathlib.Path) -> list[dict[str, str]]:
    """Findings still unapplied, so a rerun does not lose them."""
    carried: list[dict[str, str]] = []
    known = {item['dep'] for item in found}
    for item in read_findings(report):
        if item['dep'] in known or is_applied(item):
            continue
        known.add(item['dep'])
        carried.append(item)
    return carried


def write_report(findings: list[dict[str, str]], reverse: list[str],
                 manual: list[str], path: pathlib.Path) -> None:
    findings = findings + carried_findings(findings, path)
    lines = ['# Names the platform took from a prebuilt', '']
    if not findings:
        lines.append('none: the module graph builds with the tree as committed')
    for item in findings:
        lines += [
            f'{item["dep"]} -> {item["module"]}   (stem {item["stem"]})',
            f'    dependant {item["depender"]}, requested {item["variant"]}',
            f'    module lives in {item["file"]}',
            f'    ;MODULE={item["module"]} on the blob entry for {item["stem"]}.so',
            f"    '{item['dep']}': lambda lib, partition: "
            f"'{item['module']}',   in lib_fixups",
            '',
        ]
    if reverse:
        lines += ['reverse: platform modules that name one of our prebuilts', '']
        lines += [f'    {line}' for line in reverse] + ['']
    if manual:
        lines += ['manual: the sweep cannot model these', '']
        lines += [f'    {line}' for line in manual] + ['']
    path.write_text('\n'.join(lines) + '\n')


def apply_blob_modules(path: pathlib.Path, items: list[dict[str, str]]) -> int:
    lines = path.read_text().splitlines()
    edits = 0
    for item in items:
        stem = item['stem'] or item['dep']
        wanted = f'{stem}.so'
        seen = False
        for index, line in enumerate(lines):
            blob, _, args = line.partition(';')
            blob = blob.lstrip('-*').strip()
            if not blob or pathlib.PurePosixPath(blob).name != wanted:
                continue
            seen = True
            if 'MODULE=' in args:
                continue
            lines[index] = f'{line};MODULE={item["module"]}'
            edits += 1
        if not seen:
            log(f'note: no blob entry named {wanted} for {item["dep"]}')
    if edits:
        path.write_text('\n'.join(lines) + '\n')
    return edits


def apply_lib_fixups(path: pathlib.Path, items: list[dict[str, str]]) -> int:
    text = path.read_text()
    added = 0
    for item in items:
        dep = item['dep']
        if re.search(rf"^\s*'?{re.escape(dep)}'?:\s*lambda", text, re.M):
            continue
        entry = f"    '{dep}': lambda lib, partition: '{item['module']}',"
        for anchor in ('    **lib_fixups,\n', 'lib_fixups: lib_fixups_user_type = {\n'):
            if anchor in text:
                text = text.replace(anchor, anchor + entry + '\n', 1)
                added += 1
                break
        else:
            log(f'note: no lib_fixups dict in {path.name}, '
                f'add {entry.strip()} by hand')
    if added:
        path.write_text(text)
    return added


def apply_cmd(args: argparse.Namespace) -> int:
    """Turn a findings file into a fixed tree: list, fixups, regenerate."""
    report = pathlib.Path(args.apply) if args.apply else REPORT
    if not report.is_file():
        sys.exit(f'no {report}, run the sweep first')
    items = read_findings(report)
    if not items:
        log(f'nothing to apply in {report}')
        return 0

    blobs = HERE.parent / 'proprietary-files.txt'
    if not blobs.is_file():
        sys.exit(f'no {blobs}')
    edits = apply_blob_modules(blobs, items)

    fixups = HERE.parent / 'extract-files.py'
    lambdas = apply_lib_fixups(fixups, items) if fixups.is_file() else 0

    log(f'{edits} ;MODULE= entry(s) in {blobs.name}, {lambdas} lib_fixups entry(s) '
        f'in {fixups.name}')
    if not edits and not lambdas:
        log('the tree already carries every finding')
        return 0

    setup = HERE.parent / 'setup-makefiles.py'
    if not setup.is_file():
        sys.exit(f'no {setup}, the vendor makefiles are not regenerated')
    subprocess.run([sys.executable, str(setup)], cwd=str(HERE.parent), check=True)
    write_report([item for item in items if not is_applied(item)], [], [], report)
    log('regenerated the vendor makefiles, rerun the sweep to confirm')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Enumerate every prebuilt whose name the platform takes.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--top', default='', help='source tree root, found above the script')
    parser.add_argument('--target', default='', help='lineage_Z2577 by default')
    parser.add_argument('--builder', default='', help='soong_build, default out/host/linux-x86/bin')
    parser.add_argument('--max', type=int, default=200, help='safety bound on replays')
    parser.add_argument('--in-place', action='store_true', help='write the real out/soong')
    parser.add_argument('--keep', action='store_true', help='leave the generated files patched')
    parser.add_argument('--reverse', action='store_true', help='also report the mirror direction')
    parser.add_argument('--apply', nargs='?', const='', default=None,
                        help='apply a findings file and regenerate')
    parser.add_argument('--gate', action='store_true',
                        help='exit non zero while any name is shadowed, for a pre-build check')
    args = parser.parse_args()

    if args.apply is not None:
        return apply_cmd(args)

    top = pathlib.Path(args.top).resolve() if args.top else find_top(HERE)
    if top is None:
        sys.exit('no built source root above this script, pass --top')
    builder = find_soong_build(top, args.builder)
    findings: list[dict[str, str]] = []
    manual: list[str] = []

    if builder is None:
        if not args.reverse:
            sys.exit('no soong_build under out/host/linux-x86, run a build first')
        log('no soong_build here, reporting the reverse direction only')

    if builder is not None:
        target = find_target(top, args.target)
        variables = top / 'out/soong' / f'soong.{target}.variables'
        module_list = top / 'out/.module_paths/Android.bp.list'
        available_env = top / 'out/soong/soong.environment.available'
        used_env = top / 'out/soong' / f'soong.environment.used.{target}.build'

        patchable = [top / 'vendor/nubia/Z2577/Android.bp']
        patchable += sorted((top / 'device/nubia/Z2577').glob('**/Android.bp'))
        patchable = [path for path in patchable if path.exists()]

        work = top / 'out/shadow-sweep'
        if args.in_place:
            soong_out, out_dir = 'out/soong', 'out'
        else:
            (work / 'soong').mkdir(parents=True, exist_ok=True)
            (work / 'out').mkdir(parents=True, exist_ok=True)
            soong_out, out_dir = 'out/shadow-sweep/soong', 'out/shadow-sweep/out'
        ninja = f'{out_dir}/build.{target}.ninja'

        argv = [
            str(builder),
            '--top', str(top),
            '--soong_out', soong_out,
            '--out', out_dir,
            '--soong_variables', str(variables.relative_to(top)),
            '-o', ninja,
            '--incremental-build-actions',
            '--kati_suffix', f'-{target}',
            '--kati_enabled',
            '-l', str(module_list.relative_to(top)),
            '--available_env', str(available_env.relative_to(top)),
            '--used_env', str(used_env.relative_to(top)),
            'Android.bp',
        ]

        originals = {path: path.read_bytes() for path in patchable}
        texts = {path: originals[path].decode() for path in patchable}
        fallback = False

        def run() -> tuple[int, str]:
            proc = subprocess.run(argv, cwd=top, capture_output=True, text=True)
            return proc.returncode, proc.stdout + proc.stderr

        try:
            for attempt in range(1, args.max + 1):
                for path, text in texts.items():
                    path.write_text(text)
                code, output = run()
                if code == 0:
                    log(f'replay {attempt}: soong accepted the tree')
                    break

                errors = list(ERROR.finditer(output))
                if not errors:
                    if not args.in_place and not fallback:
                        log('no variant error, retrying against the real out/soong')
                        fallback = True
                        argv[argv.index('--soong_out') + 1] = 'out/soong'
                        argv[argv.index('--out') + 1] = 'out'
                        argv[argv.index('-o') + 1] = f'out/soong/build.{target}.ninja'
                        continue
                    if 'partition is different' in output:
                        log('a prebuilt prefers over a platform module on another '
                            'partition: prefer only pairs on one partition, so either '
                            'the prebuilt moves to that partition or the platform '
                            'module keeps the name')
                    ours = defined_modules(top)
                    stuck = unmodelled(output)
                    for line_text, root, module in stuck:
                        manual.append(f'{line_text} -> cannot reach {root}' if root
                                      else line_text)
                        if module and module in ours:
                            manual.append(f'{module} is also a prebuilt of ours, so the '
                                          'platform name is claimed twice')
                    log(f'stopped on {len(stuck)} error(s) this sweep does not model')
                    break

                defined = defined_modules(top)
                progressed = False
                for error in errors:
                    dep, depender = error.group('dep'), error.group('depender')
                    variant = error.group('variant').strip()
                    owner = defined.get(dep)
                    where = f'{dep} of {depender}'
                    if owner is None or defined.get(depender) is None:
                        manual.append(f'{where}: not a generated module of ours ({variant})')
                        continue
                    if 'link:shared' not in variant:
                        manual.append(f'{where}: not a shared link ({variant})')
                        continue
                    new = canonical_name(dep)
                    if new == dep:
                        new = next(
                            (dep + suffix for suffix in SUFFIXES if dep + suffix not in defined),
                            None,
                        )
                    if new is None or new == dep:
                        manual.append(f'{where}: no free name beside it ({variant})')
                        continue
                    stem = stem_of(texts[owner], dep) or dep
                    texts[owner] = rename(texts[owner], dep, new, stem)
                    findings.append({'dep': dep, 'module': new, 'stem': stem,
                                     'file': str(owner.relative_to(top)),
                                     'depender': depender, 'variant': variant})
                    for path, text in texts.items():
                        texts[path] = repoint(text, dep, new)
                    log(f'replay {attempt}: {dep} -> {new} ({variant})')
                    progressed = True

                if not progressed:
                    break
            else:
                log(f'stopped after {args.max} replays')
        finally:
            if not args.keep:
                for path, blob in originals.items():
                    path.write_bytes(blob)

    mirror = reverse_pass(top) if args.reverse else []
    write_report(findings, mirror, manual, REPORT)

    log('')
    log(f'{len(read_findings(REPORT))} shadowed prebuilt(s) outstanding, '
        f'{len(manual)} needing a hand')
    for item in manual:
        log(f'    {item}')
    if args.reverse:
        log(f'{len(mirror)} platform module(s) naming one of ours')
    log(f'written to {REPORT}')
    if args.gate and (read_findings(REPORT) or manual):
        log('refusing to build: apply the findings first')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
