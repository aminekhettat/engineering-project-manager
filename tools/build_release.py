#!/usr/bin/env python3
"""Build and verify new MIT runtime assets from a reviewed source checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

from export_public_skill import export_skill
from publication_check import check_manifest, read_snapshot, source_paths
from validation_paths import resolve_layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New destination with an existing parent')
    parser.add_argument('--skill-root', type=Path)
    args = parser.parse_args()
    layout = resolve_layout(args.skill_root)
    root = args.output.absolute()
    if root.exists() or root.is_symlink() or not root.parent.is_dir():
        parser.error('Output must be a new directory with an existing parent')
    if root.resolve().is_relative_to(layout.skill.resolve()):
        parser.error('Output must be outside the runtime source')
    version = (layout.skill / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        parser.error('Invalid runtime version')
    if os.environ.get('GITHUB_REF_TYPE') == 'tag' and os.environ.get('GITHUB_REF_NAME') != 'v' + version:
        parser.error('Tag and runtime version disagree')
    root.mkdir()
    archive = root / ('project-manager-' + version + '.zip')
    result = export_skill(layout.skill, root / 'project-manager', archive)
    if result['status'] != 'PASS' or result['license'] != 'MIT':
        print(json.dumps(result))
        return 1
    with tempfile.TemporaryDirectory(prefix='pm-release-verify-') as tmp:
        extracted = Path(tmp)
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                relative = PurePosixPath(item.filename)
                if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'project-manager':
                    raise ValueError('Unsafe generated archive path')
            bundle.extractall(extracted)
        runtime = extracted / 'project-manager'
        payload, findings = read_snapshot(runtime, source_paths(runtime, True), (), 'runtime')
        if 'PUBLICATION-MANIFEST.json' not in payload:
            raise ValueError('Manifest missing')
        findings += check_manifest(payload)
        if findings:
            print(json.dumps({'status': 'FAIL', 'findings': [f.as_dict() for f in findings]}))
            return 1
        subprocess.run([sys.executable, '-B', str(layout.tools / 'skill_package_check.py'), str(runtime)], check=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps({'status': 'PASS', 'version': version, 'license': 'MIT', 'archive': archive.name,
                      'sha256': digest, 'manifest_verified_after_extraction': True}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
