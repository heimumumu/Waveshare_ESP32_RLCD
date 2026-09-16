# Copyright (c) 2026 黑沐. MIT License.
import subprocess
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="syna-ui-") as temporary:
    output=Path(temporary)/"test"
    sources=list((root/"simulator/vendor/lvgl-9.5.0/src").rglob("*.c"))
    assets=list((root/"simulator/src/assets").glob("*.c"))
    subprocess.run(["clang","-w","-O0","-DLV_CONF_INCLUDE_SIMPLE","-DLV_LVGL_H_INCLUDE_SIMPLE",
        "-Iinclude","-Isimulator/vendor/lvgl-9.5.0","-Isimulator/src",
        "tests/ui_branding.c","simulator/src/ui/ui.c",*map(str,sources),*map(str,assets),
        "-o",str(output)],cwd=root,check=True)
    subprocess.run([str(output),str(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(temporary)/"about.ppm")],cwd=root,check=True)
