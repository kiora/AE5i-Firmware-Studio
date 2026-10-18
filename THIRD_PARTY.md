# Third-party components

The application includes unmodified runtime/dependency distributions and their license notices.

- CPython 3.12.10 Windows x64 embeddable distribution — Python Software Foundation License; `runtime/LICENSE.txt`; https://www.python.org/ftp/python/3.12.10/
- dissect.squashfs 1.12 — AGPL-3.0-or-later; source included under `runtime/Lib/site-packages/dissect/squashfs`; https://github.com/fox-it/dissect.squashfs
- dissect.cstruct 4.7 — Apache-2.0; source included under `runtime/Lib/site-packages/dissect/cstruct`; https://github.com/fox-it/dissect.cstruct
- dissect.util 3.24 — Apache-2.0; source and Windows native extension under `runtime/Lib/site-packages/dissect/util`; https://github.com/fox-it/dissect.util

The dependency `.dist-info/licenses` directories contain original LICENSE and COPYRIGHT files. No firmware images are included. The EXE launcher is compiled from the included `app/launcher.c` using Zig's Windows GNU target and Windows system libraries.

- squashfs-tools-ng 1.1.0 Windows x64 utilities and DLLs (GPLv3/LGPLv3 and third-party licenses) — `tools/squashfs-tools-ng/COPYING.md` and `tools/squashfs-tools-ng/licenses/`; https://github.com/AgentD/squashfs-tools-ng
