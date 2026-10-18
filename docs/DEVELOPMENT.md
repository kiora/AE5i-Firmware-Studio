# Development

Backend dependency versions bundled with the app: CPython 3.12.10 (Windows x64), dissect.squashfs 1.12, dissect.cstruct 4.7, dissect.util 3.24.

Run regression tests with an externally supplied AE5i SW.1.01.15 firmware ZIP:

```
python tests/test_audit.py path/to/firmware.zip empty_test_directory
```

On Linux, supply a native squashfs-tools-ng 1.1.0 tar2sqfs as the final argument. This only substitutes the process launcher in the test harness; production continues to use its bundled Windows EXE.

```
python tests/test_audit.py path/to/firmware.zip empty_test_directory /path/to/tar2sqfs
```

Compile the launcher with a development Python environment containing ziglang:

```
python -m ziglang cc -target x86_64-windows-gnu -municode -Wl,--subsystem,windows -O2 -s app/launcher.c -o AE5iFirmwareStudio.exe -luser32 -lkernel32
```

No fixture firmware or temporary test outputs are distributed. Full Windows GUI execution remains to be verified on Windows.
