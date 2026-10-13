"""Build dist/maps4drone-qgis-<version>.zip: the plugin plus the vendored core."""

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "maps4drone_qgis"
PLUGIN_DIR = ROOT / "qgis_plugin" / PLUGIN_NAME
CORE_DIR = ROOT / "src" / "maps4drone"


def core_version() -> str:
    match = re.search(r'__version__ = "([^"]+)"', (CORE_DIR / "__init__.py").read_text())
    if match is None:
        raise RuntimeError("could not read __version__ from the core package")
    return match.group(1)


def _files(base: Path, skip_dirs: tuple[str, ...] = ()) -> list[Path]:
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and not any(part in skip_dirs for part in p.relative_to(base).parts)
    )


def build(out_dir: Path) -> Path:
    version = core_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"maps4drone-qgis-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in _files(PLUGIN_DIR, skip_dirs=("vendor",)):
            arc = f"{PLUGIN_NAME}/{path.relative_to(PLUGIN_DIR).as_posix()}"
            if path.name == "metadata.txt":
                text = re.sub(r"(?m)^version=.*$", f"version={version}", path.read_text())
                z.writestr(arc, text)
            else:
                z.write(path, arc)
        for path in _files(CORE_DIR, skip_dirs=("web",)):
            z.write(
                path, f"{PLUGIN_NAME}/vendor/maps4drone/{path.relative_to(CORE_DIR).as_posix()}"
            )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    print(build(parser.parse_args().out))


if __name__ == "__main__":
    main()
