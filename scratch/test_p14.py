#!/usr/bin/env python3
"""P14 against the fixtures AOSP tests the same rule with.

system/tools/aidl/build/aidl_test.go, TestDuplicatedVersions. Three shapes have
to be flagged and two must not; the two that must not are the reason the check
is keyed by backend as well as by interface.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preflight

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


def run(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp, 'Android.bp')
        path.write_text(text)
        mods = preflight.parse_bp(str(path), quiet=True)
    preflight.findings.clear()
    preflight.notes.clear()
    preflight.check_p14(mods, {}, mods)
    return [message for check, message in preflight.findings if check == 'P14']


def main():
    bad = 0
    for label, text, module, count in CASES:
        found = run(text)
        ok = len(found) == count
        if ok and module:
            ok = all(f'"{module}"' in m and 'myiface (ndk)' in m for m in found)
        print(f'{"ok  " if ok else "FAIL"} {label}: {len(found)} finding(s)'
              + (f' -> {found[0]}' if found else ''))
        if not ok:
            bad += 1
    print(f'\n{len(CASES) - bad}/{len(CASES)} cases as upstream behaves')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
