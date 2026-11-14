"""Apply the TAgent theme to an OpenNotebook Next.js build before starting it."""

import argparse
import hashlib
from pathlib import Path

MARKER = "/* TAgent space theme */"
REFERENCE_TYPES = {".html", ".js", ".json", ".rsc"}


def apply_theme(build: Path, theme: str) -> Path:
    candidates = []
    for path in (build / "static/css").glob("*.css"):
        content = path.read_text(encoding="utf-8")
        if all(token in content for token in ("--primary:", "--sidebar:", "--background:")):
            candidates.append((path, content))
    if len(candidates) != 1:
        raise ValueError(f"Expected one OpenNotebook theme stylesheet in {build / 'static/css'}")

    path, content = candidates[0]
    updated = f"{content.partition(MARKER)[0].rstrip()}\n{theme}".encode()
    asset = path.with_name(f"{hashlib.sha256(updated).hexdigest()[:16]}.css")
    if asset == path:
        return asset

    asset.write_bytes(updated)
    old_name = path.name.encode()
    new_name = asset.name.encode()
    for folder in ("server", "static/chunks"):
        for reference in (build / folder).rglob("*"):
            if reference.suffix not in REFERENCE_TYPES or not reference.is_file():
                continue
            data = reference.read_bytes()
            if old_name in data:
                reference.write_bytes(data.replace(old_name, new_name))
    path.unlink()
    return asset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("next_build", type=Path, nargs="+")
    args = parser.parse_args()
    theme = Path(__file__).with_name("space.css").read_text(encoding="utf-8")
    for build in args.next_build:
        try:
            print(apply_theme(build, theme))
        except ValueError as error:
            parser.exit(1, f"{error}\n")
