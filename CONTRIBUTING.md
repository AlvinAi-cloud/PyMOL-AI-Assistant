# Building native installers

The application uses official Open-Source PyMOL 3.1.0. The checked-in source archive has a SHA-256 manifest and is compiled without engine source patches. Runtime GUI adapters and the AI helper belong to this project.

Native builds are required. The Actions workflow builds Apple Silicon (macos-15), Intel Mac (macos-15-intel), Windows x64, and Ubuntu amd64 separately. Each successful job uploads its installer, build-environment list, and checksum as an Actions artifact. No public release is published automatically.

1. Install Rust and an appropriate C/C++ compiler. On Windows initialize the MSVC x64 developer shell. On Ubuntu install the desktop/OpenGL dependencies listed in `.github/workflows/installers.yml`.
2. Create and activate the environment in `packaging/environment.yml` with micromamba.
3. Run `python scripts/build_native.py --work .build/native`.
4. Run `python scripts/test_frozen.py --work .build/native`. On Ubuntu use `LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a` before this command when no display is available.
5. Run `python scripts/package_native.py --work .build/native --output artifacts`.

Frozen GUI checks cover update checks, About text, Draw/Ray, AI vision and sequence tools, lighting presets, graphics options, transparency focus, offline Help, and transparent PNG export. A LOCAL_REVIEW marker is forbidden in public installers. Apple notarization and Windows Authenticode signing require separate certificates.

For a local Mac review app, set `PYMOL_AI_LOCAL_REVIEW=1` and set `PYMOL_AI_BUILD_DIR` to the absolute `freeze` directory under your chosen build work directory. Run `python setup.py bdist_mac`, then run `python scripts/test_frozen.py --work <work-directory> --local-review`. The review app uses its own bundle ID and profile.

Mac file types use LaunchServices. Windows registers the app for the selected types and opens Windows Settings for user confirmation. Ubuntu installs a desktop entry, MIME definitions, document icons, and sets only file types explicitly chosen through the app. The DEB never changes user defaults in an administrator install hook.

Accounts, API keys, history, and checkpoints are per-user runtime data and must never be added to this repository. Test requests use localhost mock providers and no paid API accounts.
