#!/usr/bin/env python3
"""Independently inspect and stage v6 artifacts. No device, commit or release actions."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import package_native_control_v6 as package
from native_v6 import validate_v6_elf as gate


def inspect_bundle(driver, unstripped, helper, manifest, commit, readelf, nm, output):
    subprocess.run([sys.executable, str(Path(gate.__file__).resolve()),
                    '--driver', str(driver), '--unstripped-driver', str(unstripped),
                    '--helper', str(helper), '--manifest', str(manifest),
                    '--source-commit', commit, '--readelf', readelf, '--nm', nm,
                    '--out', str(output)], check=True)
    raw = json.loads(output.read_text())
    # Only allowlisted proof goes into this public repository, never compiler
    # paths, full manifests, build logs or arbitrary extra provenance fields.
    report = {key: raw[key] for key in ('iteration', 'profile', 'controlProtocol', 'state')}
    report['source'] = {key: raw['source'][key] for key in ('commit', 'aospManifestSha256')}
    report['embeddedCodeEvidence'] = {key: raw['embeddedCodeEvidence'][key] for key in
                                     ('definedSymbolsVerified', 'loadSegmentsSha256', 'unstrippedSha256')}
    report['artifacts'] = {kind: {key: raw['artifacts'][kind][key] for key in
                                ('sha256', 'sizeBytes', 'direct_dt_needed', 'soname', 'nodelete')}
                           for kind in ('driver', 'helper')}
    return report


def import_candidate(driver, unstripped, helper, manifest, commit, root=package.ROOT, readelf=None, nm=None):
    value = package.candidate(root)
    if value.get('nativeSource', {}).get('commit') != commit:
        raise ValueError('Compiler commit does not match the pinned v6 source')
    readelf = readelf or package.readelf_tool()
    nm = nm or os.environ.get('JDSP_NM') or shutil.which('llvm-nm') or shutil.which('nm')
    if not nm:
        raise ValueError('Set JDSP_NM to a trusted LLVM nm executable')
    notices = (root / package.NOTICES).read_bytes()
    if not notices.strip():
        raise ValueError('Missing reviewed v6 redistribution notices')
    value['notices'] = {'path': package.NOTICES, 'sha256': sha256(notices).hexdigest(),
                        'sizeBytes': len(notices)}
    with tempfile.TemporaryDirectory(prefix='jdsp-v6-import-') as directory:
        stage = Path(directory)
        report = inspect_bundle(driver, unstripped, helper, manifest, commit, readelf, nm, stage / 'report.json')
        for kind, source in (('driver', driver), ('helper', helper),
                             ('app', root / package.EXPECTED_PATHS['app'])):
            target = stage / package.EXPECTED_PATHS[kind]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for kind in ('driver', 'helper'):
            artifact = report['artifacts'][kind]
            value['artifacts'][kind] = {'path': package.EXPECTED_PATHS[kind],
                                       'sha256': artifact['sha256'], 'sizeBytes': artifact['sizeBytes']}
        value['state'] = 'ready-for-device-test'
        value['notes'] = [
            'The v6 driver and matching helper passed independent ELF and embedded-code inspection before import.',
            'Embedded AIDL Effect V4/common V5 and legacy AELI share one driver; control protocol remains 3.',
            'Android factory compatibility, SELinux behavior and real audio processing remain unverified for this build.',
        ]
        meta = 'common/files/JamesDSPManagerThePBone.apk.meta'
        shutil.copy2(root / meta, stage / meta)
        (stage / 'native-control').mkdir()
        (stage / package.NOTICES).write_bytes(notices)
        (stage / package.MANIFEST).write_text(json.dumps(value, indent=2) + '\n')
        (stage / package.PROVENANCE).write_text(json.dumps(report, indent=2) + '\n')
        package.verify_artifacts(stage, readelf)
        # Nothing in the tracked candidate is touched before staged inspection.
        props = root / 'module.prop'
        lines = props.read_text().splitlines()
        replacements = {
            'name': 'JamesDSP Manager (dual-entry native-control-v6 test)',
            'version': package.VERSION, 'versionCode': str(package.VERSION_CODE),
            'description': 'Dual-entry AIDL/legacy driver; global jdsp.control protocol 3 with legacy fallback',
        }
        updated = []
        for line in lines:
            key = line.split('=', 1)[0]
            updated.append(key + '=' + replacements[key] if key in replacements else line)
        text = '\n'.join(updated) + '\n'
        (stage / 'module.prop').write_text(text)
        names = [package.EXPECTED_PATHS['driver'], package.EXPECTED_PATHS['helper'],
                 package.MANIFEST, package.PROVENANCE, 'module.prop']
        backups = {name: ((root / name).read_bytes(), (root / name).stat().st_mode)
                   if (root / name).exists() else None for name in names}
        try:
            for name in names:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage / name, target)
            (root / package.EXPECTED_PATHS['helper']).chmod(0o755)
        except Exception:
            for name, before in backups.items():
                target = root / name
                if before is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(before[0])
                    target.chmod(before[1])
            raise
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('driver', 'unstripped-driver', 'helper', 'manifest'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--readelf')
    parser.add_argument('--nm')
    args = parser.parse_args()
    import_candidate(args.driver, args.unstripped_driver, args.helper, args.manifest,
                     args.source_commit, readelf=args.readelf, nm=args.nm)
    print('V6 artifacts independently inspected and imported; no device or release changed.')


if __name__ == '__main__':
    main()
