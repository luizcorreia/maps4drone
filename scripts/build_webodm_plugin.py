"""Build dist/maps4drone-webodm-<version>.zip: the WebODM plugin plus the vendored core.

Upload the zip in WebODM (Administration > Plugins > Load Plugin) or unpack its single
`maps4drone/` folder into <media>/plugins/. The compiled UI goes in public/; it is added
when `web/` has been built for the plugin (see docs/webodm.md).
"""

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "maps4drone"
PLUGIN_DIR = ROOT / "webodm_plugin" / PLUGIN_NAME
CORE_DIR = ROOT / "src" / "maps4drone"
DEFAULT_UI = ROOT / "web" / "dist-webodm"


def plugin_version() -> str:
    return str(json.loads((PLUGIN_DIR / "manifest.json").read_text())["version"])


def _files(base: Path, skip_dirs: tuple[str, ...] = ()) -> list[Path]:
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and not any(part in skip_dirs for part in p.relative_to(base).parts)
    )


def build(out_dir: Path, ui_dir: Path = DEFAULT_UI) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"maps4drone-webodm-{plugin_version()}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in _files(PLUGIN_DIR, skip_dirs=("vendor", "public")):
            z.write(path, f"{PLUGIN_NAME}/{path.relative_to(PLUGIN_DIR).as_posix()}")
        for path in _files(CORE_DIR, skip_dirs=("web",)):
            z.write(
                path, f"{PLUGIN_NAME}/vendor/maps4drone/{path.relative_to(CORE_DIR).as_posix()}"
            )
        if ui_dir.is_dir():
            for path in _files(ui_dir):
                z.write(path, f"{PLUGIN_NAME}/public/{path.relative_to(ui_dir).as_posix()}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--ui", type=Path, default=DEFAULT_UI, help="compiled UI to ship in public/"
    )
    args = parser.parse_args()
    print(build(args.out, args.ui))


if __name__ == "__main__":
    main()
