# PyMOL AI-Assistant standalone package

Native standalone package: 0.4.0. This independently prepared package combines official Open-Source PyMOL 3.1.0 with a docked AI assistant. It is not a Schrödinger distribution or endorsement. PyMOL is a trademark of Schrödinger, LLC.

## Download installers

These standalone installers also provide a convenient way to set up **free, open-source PyMOL 3.1.0** as a normal desktop app. Python and Conda are not required. You can use PyMOL’s standard molecular visualization tools offline without connecting an AI account. AI features are optional; charges from your chosen AI provider may apply.

| Platform | Version 0.4.0 download |
| --- | --- |
| Mac — Apple Silicon (M-series) | [Download arm64 DMG](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/download/v0.4.0/PyMOL-AI-Assistant-0.4.0-macOS-arm64.dmg) |
| Mac — Intel | [Download x86_64 DMG](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/download/v0.4.0/PyMOL-AI-Assistant-0.4.0-macOS-x86_64.dmg) |
| Windows — x64 | [Download Setup EXE](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/download/v0.4.0/PyMOL-AI-Assistant-0.4.0-Windows-x64-Setup.exe) |
| Ubuntu — amd64 (built on 22.04) | [Download DEB](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/download/v0.4.0/PyMOL-AI-Assistant-0.4.0-Ubuntu-amd64.deb) |

[All release files and source](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/tag/v0.4.0) · [SHA-256 checksums](https://github.com/AlvinAi-cloud/PyMOL-AI-Assistant/releases/download/v0.4.0/SHA256SUMS-0.4.0.txt)

Mac builds are ad-hoc signed and are not Apple-notarized; the Windows installer is unsigned. Your OS may show a download warning. The installers passed native build and GUI checks.

The Apple Silicon download has been revised (build 6) to launch natively as ARM64 without Rosetta. Its architecture preference and native execution are checked through macOS Launch Services, as used by Finder.

## Use

- **macOS:** open the DMG for your processor, drag **PyMOL AI-Assistant.app** into Applications, and launch that copy.
- **Windows x64:** run **Setup.exe** and launch **PyMOL AI-Assistant** from the Start menu. The installer runs per user and offers a desktop shortcut.
- **Ubuntu amd64:** install the DEB with `sudo apt install ./PyMOL-AI-Assistant-0.4.0-Ubuntu-amd64.deb`, then launch it from the applications menu.

Python, Conda, Rust, and Codex are not required by installed apps. Native graphics drivers with OpenGL 2.1 or newer and normal desktop OS libraries remain required. Windows CI registers a pinned Mesa software driver on its disposable test runner; this driver is never included in the installer. The existing `pymol` Terminal shortcut on the development Mac is unaffected.

On first launch, choose which document types should open here by default: PDB (`.pdb`), mmCIF (`.cif`, `.mmcif`), PyMOL sessions (`.pse`), Mol/SDF (`.mol`, `.sdf`) and Mol2 (`.mol2`). On macOS and Ubuntu, only checked types change. Windows registers the checked formats and opens Settings for the user to confirm the preferred app. Choose Skip to keep existing preferences. Reopen this setup through **AI Assistant → File Types…**. PyMOL-based app and format-labeled document icons are bundled. Finder may need a moment to refresh cached icons after a preference changes. File association setup is per user and requires no administrator password.

Use PyMOL’s normal File menu to open structures or sessions. The AI Assistant panel places Accounts and Example together above a larger conversation and message input. Connection/progress status shares the commands/results box. Use PyMOL’s existing Export Image As menu for images. Draw/Ray and the bundled Designer dialogs have compiled forms; the PyQt UI loader is also included.

Connect your own provider under **AI Assistant → Accounts and Models…**. Supported transports are OpenAI API, Anthropic, Gemini, compatible/local APIs, and the inherited eligible open-source ChatGPT sign-in flow. Choose or enter an accessible model ID. A provider website subscription does not automatically supply API access. ChatGPT access depends on eligibility and consent; live account access has not been verified in this build. No credentials from RDataCraft, PlasmidCraft, Codex, or another PyMOL installation are imported.

An explicit Send starts an automatic assistant turn. The assistant can call PyMOL, receive its results, and continue for up to eight steps without manual approval. The initial summary contains object names, atom counts and chain names. When needed, the assistant can extract FASTA from any molecular selection or examine an image of the current PyMOL window/viewport. Sequences reflect loaded atoms and may omit unresolved residues. Window images are captured within this application, include visible labels/console/conversation, and are sent only when the assistant requests inspection. Images stay in memory for one follow-up request and are not written to conversation history. Choose a vision-capable model for image inspection; text-only models can still use molecular queries. Recent conversation and actual tool results accompany follow-up requests, so requested molecular data and paths may be sent to your configured provider. Model discovery/sign-in contacts the provider without molecular context. Test connection sends a small request and may incur usage.

The assistant now executes native PyMOL command-line operations automatically, including selections, object creation/deletion, styling, atom-property expressions, fitting, distances, maps, loading/fetching structures and saving/exporting files. It uses PyMOL's own command interpreter and returns actual console output and query values to the model. An activity panel shows what ran. There is no Apply/review button or manual Undo button. General Python scripts, shell commands, aliases and command callbacks are outside the assistant command interface; the ordinary manual PyMOL interface remains available.

Before changing a scene, the app automatically saves a private recovery checkpoint. All command rounds within one assistant turn share that checkpoint. Ask the assistant to undo or restore the previous scene; its restore tool loads the checkpoint rather than guessing reverse commands. The last three checkpoints persist across app restarts. Read-only query turns do not replace the previous changing turn's checkpoint. Recovery restores the molecular scene, not saved-file overwrites or other external effects. Cancel stops follow-up AI requests and subsequent commands; a running native PyMOL command completes before cancellation takes effect.

The assistant panel's initial width is 238 logical pixels, 30% narrower than the original 340-pixel setting. Users can still resize or detach it. The app icon declaration and Qt application icon both use the bundled PyMOL artwork.

Normal PyMOL tools work offline. Settings, saved API credentials, ChatGPT sessions, launch logs, conversation history and checkpoints live in `~/Library/Application Support/PyMOL AI-Assistant`, on macOS, `%LOCALAPPDATA%/PyMOL AI-Assistant` on Windows, or `$XDG_CONFIG_HOME/pymol-ai-assistant` (default `~/.config/pymol-ai-assistant`) on Linux, outside documents and exports. Credential files are restricted to the current user; they are not encrypted by this initial file-based helper. Disconnect retains saved API settings; Forget removes them. ChatGPT sign-out attempts revocation and reports an unconfirmed revocation.

The app ignores other PyMOL startup scripts/plugins at launch. Its standard PyMOL menus remain available for molecular workflows. Native Apple Silicon, Intel Mac, Windows x64, and Ubuntu amd64 builds have passed their frozen GUI and Draw/Ray regression tests. Windows and Ubuntu installers are also checked by installing the package and exercising the installed Draw/Ray popup. Developer ID signing/notarization and validation on other Macs remain release work. A local ad-hoc signature does not constitute Apple notarization.

## Source and build

The upstream engine is pinned to official tag `v3.1.0`, commit `f51e58f6b08308c41c85b9d12a23231f49ca325a`, from https://github.com/schrodinger/pymol-open-source. It is compiled locally, not taken from the third-party Apple Silicon DMG. No upstream source patches are used. Fast MMTF/msgpack-c support is disabled in this initial build; VMD molfile plugins and COLLADA support retain the upstream build defaults.

`scripts/build_native.py` builds each native platform; `scripts/build_macos.py` retains the original Intel Mac build pipeline. `setup.py` freezes Python/PyMOL/Qt and bundles the independently built AI helper. The source of that helper is in `ai-helper/` with a locked Cargo dependency graph. The Python adapter/panel is in `pymol_ai_assistant/`.

Application integration and the RDataCraft-derived helper are GPL-3.0-or-later. PlasmidCraft contributions retain their MIT notice. Open-Source PyMOL and all bundled dependencies retain their own licenses; see `LICENSE` and `licenses/`.

The assistant is a molecular visualization aid. It does not validate biological conclusions or replace inspection of structures and calculated results.

Vision transport formats follow the official [OpenAI](https://developers.openai.com/api/docs/guides/images-vision), [Anthropic](https://platform.claude.com/docs/en/build-with-claude/vision), and [Gemini](https://ai.google.dev/gemini-api/docs/image-understanding) documentation. Offline tests validate request contents; live model/account access remains unverified.

Version 0.3.1 adapts the compiled Draw/Ray form controller to the QWidget expected by the native popup. Regression QA opens the actual button menu and invokes Draw and Ray through its controls.

## Native platform installers

See [CONTRIBUTING.md](CONTRIBUTING.md) and [.github/workflows/installers.yml](.github/workflows/installers.yml). Outputs are native Apple Silicon and Intel Mac DMGs, a Windows x64 Setup EXE, and an Ubuntu amd64 DEB. Successful native jobs upload installers as GitHub Actions artifacts. No installer is represented as complete until its native GUI checks pass.
