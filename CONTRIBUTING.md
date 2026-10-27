# Building native installers

The application uses official Open-Source PyMOL 3.1.0. The checked-in source archive has a SHA-256 manifest and is compiled without engine source patches. Runtime GUI adapters and the AI helper belong to this project.

Native builds are required. The Actions workflow builds Apple Silicon (macos-15), Intel Mac (macos-15-intel), Windows x64, and Ubuntu amd64 separately. Each successful job uploads its installer, build-environment list, and checksum as an Actions artifact. No public release is published automatically.

1. Install Rust and an appropriate C/C++ compiler. On Windows initialize the MSVC x64 developer shell. On Ubuntu install the desktop/OpenGL dependencies listed in `.github/workflows/installers.yml`.
2. Create and activate the environment in `packaging/environment.yml` with micromamba.
3. Run `python scripts/build_native.py --work .build/native`.
4. Run `python scripts/test_frozen.py --work .build/native`. On Ubuntu use `LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a` before this command when no display is available.
5. Run `python scripts/package_native.py --work .build/native --output artifacts`.

The existing Intel release is 0.3.1. The portable source branch is 0.4.0 development until the native CI checks pass. Apple signing/notarization and Windows Authenticode signing need separate certificates. Unsigned builds may trigger OS download warnings. Do not call an artifact tested merely because its build succeeded: the frozen GUI and real Draw/Ray popup tests must pass on that platform.

Mac file types use LaunchServices. Windows registers the app for the selected types and opens Windows Settings for user confirmation. Ubuntu installs a desktop entry, MIME definitions, document icons, and sets only file types explicitly chosen through the app. The DEB never changes user defaults in an administrator install hook.

Accounts, API keys, history, and checkpoints are per-user runtime data and must never be added to this repository. Test requests use localhost mock providers and no paid API accounts.
