#!/usr/bin/env python3
"""Validate external native artifacts before promoting the local v4 candidate.

Does not execute binaries, install on devices, commit, or publish a release.
Only allowlisted provenance is copied to the public module repository.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import package_native_control_v4 as package


def inspect_elf(path, kind, expected, readelf):
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    if digest in package.RETIRED_DRIVERS or digest != expected.get('sha256'):
        raise ValueError('Unexpected or retired native artifact: ' + kind)
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
        raise ValueError('Expected little-endian ELF64 AArch64: ' + kind)
    dynamic = subprocess.check_output([readelf, '-d', str(path)], text=True)
    needed = sorted(re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic))
    if not needed or needed != sorted(expected.get('direct_dt_needed', [])):
        raise ValueError('Actual DT_NEEDED differs from provenance: ' + kind)
    if kind == 'driver':
        if not re.search(r'\(SONAME\).*\[libjamesdspaidl\.so\]', dynamic) or 'NODELETE' not in dynamic:
            raise ValueError('Missing library SONAME or NODELETE')
        symbols = subprocess.check_output([readelf, '--dyn-syms', '--wide', str(path)], text=True)
        for name in ('queryEffect', 'createEffect', 'destroyEffect'):
            if not any(re.search(r'\b' + name + r'(?:@@?\S+)?\s*$', line) and
                       ' UND ' not in line for line in symbols.splitlines()):
                raise ValueError('Missing defined factory export: ' + name)
    elif int.from_bytes(data[16:18], 'little') not in (2, 3):
        raise ValueError('Helper must be an ELF executable or PIE')
    return {'path': package.EXPECTED_PATHS[kind], 'sha256': digest, 'sizeBytes': len(data)}


def import_candidate(driver, helper, provenance_path, root=package.ROOT, readelf=None):
    value = package.candidate(root)
    commit = value['nativeSource'].get('commit')
    provenance = json.loads(provenance_path.read_text())
    if not re.fullmatch('[0-9a-f]{40}', commit or '') or provenance.get('source', {}).get('commit') != commit:
        raise ValueError('Compiler source commit does not match the pinned v4 source')
    readelf = readelf or os.environ.get('JDSP_READELF') or shutil.which('llvm-readelf') or shutil.which('readelf')
    if not readelf:
        raise ValueError('Set JDSP_READELF to the Android NDK llvm-readelf path')
    public = {'source': {'commit': commit}, 'artifacts': {}}
    for kind, path in (('driver', driver), ('helper', helper)):
        report = provenance.get('artifacts', {}).get(kind, {})
        value['artifacts'][kind] = inspect_elf(path, kind, report, readelf)
        public['artifacts'][kind] = {key: report[key] for key in ('sha256', 'direct_dt_needed')}
    value['state'] = 'ready-for-device-test'
    # Stage a complete verification tree first. A failed check leaves all tracked
    # candidate files untouched, including the existing driver and signed APK.
    with tempfile.TemporaryDirectory(prefix='jdsp-v4-import-') as directory:
        stage = Path(directory)
        for kind, source in (('driver', driver), ('helper', helper),
                             ('app', root / package.EXPECTED_PATHS['app'])):
            target = stage / package.EXPECTED_PATHS[kind]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        meta = 'common/files/JamesDSPManagerThePBone.apk.meta'
        shutil.copy2(root / meta, stage / meta)
        (stage / 'native-control').mkdir(exist_ok=True)
        (stage / package.MANIFEST).write_text(json.dumps(value, indent=2) + '\n')
        report_path = 'native-control/v4-build-provenance.json'
        (stage / report_path).write_text(json.dumps(public, indent=2) + '\n')
        package.verify_artifacts(stage)
        names = [package.EXPECTED_PATHS['driver'], package.EXPECTED_PATHS['helper'], report_path, package.MANIFEST]
        backups = {name: (root / name).read_bytes() if (root / name).exists() else None for name in names}
        props = root / 'module.prop'
        original_props = props.read_bytes()
        try:
            for name in names:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage / name, target)
            (root / package.EXPECTED_PATHS['helper']).chmod(0o755)
            text = props.read_text()
            text = re.sub(r'^name=.*$', 'name=JamesDSP Manager (native-control-v4 test)', text, flags=re.M)
            text = re.sub(r'^version=.*$', 'version=v6.5.15-native-control-v4-test', text, flags=re.M)
            text = re.sub(r'^versionCode=.*$', 'versionCode=119', text, flags=re.M)
            text = re.sub(r'^description=.*$', 'description=Experimental global jdsp.control; device processing must be verified', text, flags=re.M)
            props.write_text(text)
        except Exception:
            props.write_bytes(original_props)
            for name, data in backups.items():
                if data is None:
                    (root / name).unlink(missing_ok=True)
                else:
                    (root / name).write_bytes(data)
            raise
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', required=True, type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--provenance', required=True, type=Path)
    args = parser.parse_args()
    import_candidate(args.driver, args.helper, args.provenance)
    print('Validated native artifacts imported. Run tests and package_native_control_v4.py; no device or release changed.')


if __name__ == '__main__':
    main()
