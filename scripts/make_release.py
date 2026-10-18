#!/usr/bin/env python3
"""Create a full Windows ZIP + SHA-256 file from an already assembled distribution."""
import argparse
import hashlib
from pathlib import Path
import zipfile

REQUIRED = [
    'AE5iFirmwareStudio.exe', 'app/firmware.py', 'app/Studio.ps1',
    'runtime/python.exe', 'Start.cmd',
    'tools/squashfs-tools-ng/tar2sqfs.exe',
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True, help='Complete unpacked Windows distribution')
    ap.add_argument('--output', type=Path, default=Path('dist'))
    ap.add_argument('--version', required=True)
    args = ap.parse_args()
    src = args.input.resolve()
    if not src.is_dir():
        ap.error('Input must be an existing directory')
    missing = [p for p in REQUIRED if not (src / p).is_file()]
    if missing:
        ap.error('Missing required release component(s): ' + ', '.join(missing))
    out = args.output.resolve()
    if out == src or src in out.parents:
        ap.error('Output must not be inside input directory')
    out.mkdir(parents=True, exist_ok=True)
    stem = f'AE5i-Firmware-Studio-v{args.version}-Windows-x64'
    target = out / (stem + '.zip')
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as z:
        for f in sorted(src.rglob('*')):
            if not f.is_file() or f.is_symlink():
                continue
            rel = f.relative_to(src)
            if '__pycache__' in rel.parts or f.suffix == '.pyc' or rel.parts[0] in ('logs','log','output'):
                continue
            z.write(f, arcname=Path('AE5i_Firmware_Studio') / rel)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    checksum = out / (stem + '.sha256')
    checksum.write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    print(target)
    print(checksum)
    print('SHA256', digest)

if __name__ == '__main__':
    main()
