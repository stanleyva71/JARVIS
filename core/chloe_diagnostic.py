"""Standalone smoke test for the Chloe OpenGL viewport."""

from __future__ import annotations

import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from PyQt6.QtWidgets import QApplication

from core.chloe_gl import ChloeGLWidget


def main() -> int:
    app = QApplication(sys.argv)
    base = BASE
    widget = ChloeGLWidget(base)
    widget.resize(640, 640)
    widget.show()

    app.processEvents()
    time.sleep(2.0)
    app.processEvents()

    context = widget.context()
    gl = getattr(__import__("core.chloe_gl", fromlist=["GL"]), "GL", None)
    vendor = renderer = gl_version = "unavailable"
    if context is not None and context.isValid() and gl is not None:
        vendor = gl.glGetString(gl.GL_VENDOR).decode("ascii", "replace")
        renderer = gl.glGetString(gl.GL_RENDERER).decode("ascii", "replace")
        gl_version = gl.glGetString(gl.GL_VERSION).decode("ascii", "replace")

    print(f"[Chloe diagnostic] isValid={widget.isValid()}")
    print(f"[Chloe diagnostic] contextValid={context.isValid() if context else False}")
    print(f"[Chloe diagnostic] vendor={vendor}")
    print(f"[Chloe diagnostic] renderer={renderer}")
    print(f"[Chloe diagnostic] version={gl_version}")
    print(f"[Chloe diagnostic] ready={widget.ready}")
    print(f"[Chloe diagnostic] error={widget._error or 'none'}")

    image = widget.grabFramebuffer()
    out = base / "chloe-diagnostic.png"
    image.save(str(out))
    print(f"[Chloe diagnostic] framebuffer={out}")

    widget.close()
    return 0 if widget.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
