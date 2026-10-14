"""UTF-8 is the wire encoding of our CLI/NDJSON pipes, including frozen builds."""

import sys


def configure_stdio() -> None:
    # PyInstaller ignores Python startup environment variables. Configure the
    # actual streams too, including source-mode CLI entry points launched alone.
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            options = {
                "encoding": "utf-8",
                "errors": "backslashreplace" if name == "stderr" else "strict",
            }
            if name != "stdin":
                options["line_buffering"] = True
            reconfigure(**options)
