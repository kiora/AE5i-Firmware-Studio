# AE5i Firmware Studio

**Version:** 1.4.11 · Windows 10/11 x64

Firmware inspection, partition export/import, integrity validation and SquashFS workflow for the verified ZEEHO AE5i GEMINI / SW.1.01.15 layout. Operates on local files; **does not connect to vehicles or initiate OTA updates**.

## Download / 下载

- **Windows users:** download `AE5i-Firmware-Studio-v1.4.11-Windows-x64.zip` from [GitHub Releases](../../releases). Extract the entire archive, then run `AE5iFirmwareStudio.exe`. `Start.cmd` is the fallback; `Start_Diagnostic.cmd` is for troubleshooting. Do not download only the EXE.
- **Developers:** this repository is the source distribution. It intentionally excludes the embedded Python runtime, prebuilt native components and binary launcher.

## Repository layout

- `app/firmware.py`: firmware processing backend
- `app/Studio.ps1`: Windows desktop UI
- `app/launcher.c`: GUI launcher source
- `assets/`: icon
- `tests/`: regression checks
- `docs/`: audit, development and test documentation
- `tools/squashfs-tools-ng/`: third-party notices and documentation (binaries are bundled in Releases)
- `scripts/make_release.py`: verify and package a complete Windows distribution

## Development

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md). To run the original regression test suite you must supply your **own firmware**; no firmware or test fixtures are distributed. The release package embeds CPython 3.12.10 and SquashFS tools (see [`THIRD_PARTY.md`](THIRD_PARTY.md)).

## Build / release process

1. Start with a complete Windows distribution containing `runtime/python.exe`, `AE5iFirmwareStudio.exe`, `app/Studio.ps1`, `app/firmware.py` and SquashFS tools. The source repository **by itself is not a complete executable distribution**.
2. Build the launcher as documented in `docs/DEVELOPMENT.md` and stage the approved runtime/dependencies.
3. Run `python scripts/make_release.py --input <distribution-folder> --output dist --version 1.4.11` to validate and create an uploadable ZIP and SHA256 digest.
4. Upload those files as assets of GitHub Release `v1.4.11`. See [`docs/RELEASING.md`](docs/RELEASING.md).

## Compatibility and safety / 兼容性与安全

- Restricted to the verified GEMINI / SW.1.01.15 layout; not a universal OTA flasher.
- Repackaging checksums do **not** replace OEM signatures or guarantee the resulting image is accepted by a vehicle.
- Keep a backup of the original firmware. No official firmware image is included.
- Current changelog notes that Windows GUI operation has **not yet been verified on a physical Windows machine**; treat the release as pre-release until tested.

## License

Project copyright/license text: [`COPYING`](COPYING) (AGPL-3.0); bundled dependencies have additional terms detailed in [`THIRD_PARTY.md`](THIRD_PARTY.md).
