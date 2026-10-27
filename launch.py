"""Frozen executable entry point with startup diagnostics."""
import os
import traceback

if __name__ == "__main__":
    try:
        from pymol_ai_assistant.app import main
        main()
    except Exception:
        details = traceback.format_exc()
        try:
            from pymol_ai_assistant.config import profile_dir
            with (profile_dir() / "launch.log").open("a", encoding="utf-8") as log:
                log.write(details + "\n")
        except Exception:
            pass
        # CI cannot dismiss cx_Freeze's GUI traceback dialog. Preserve the
        # actual startup error and exit so diagnostics are collected promptly.
        if os.environ.get("PYMOL_AI_SKIP_SETUP"):
            raise SystemExit(1)
        raise
