#!/usr/bin/env python3
"""Pripraví publikovateľný SHMÚ radarový adresár pre R2.

Vstup: výstup imeteo-radar (PNG + extent_index.json, prípadne v podpriečinkoch)
Výstup: plochý adresár s poslednými snímkami, extent_index.json a manifest.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PNG_RE = re.compile(r"^(\d{10})\.png$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_extent(root: Path) -> tuple[Path, dict[str, float]]:
    candidates = sorted(root.rglob("extent_index.json"))
    if not candidates:
        fail("extent_index.json sa vo výstupe nenašiel")

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            w = data.get("wgs84") or data.get("extent") or {}
            extent = {
                "west": float(w["west"]),
                "east": float(w["east"]),
                "south": float(w["south"]),
                "north": float(w["north"]),
            }
            if extent["west"] >= extent["east"] or extent["south"] >= extent["north"]:
                continue
            return path, extent
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue

    fail("žiadny extent_index.json neobsahuje platné WGS84 hranice")


def main() -> None:
    if len(sys.argv) != 3:
        fail("použitie: build_manifest.py <raw-output> <publish-output>")

    raw = Path(sys.argv[1]).resolve()
    publish = Path(sys.argv[2]).resolve()
    if not raw.is_dir():
        fail(f"vstupný adresár neexistuje: {raw}")

    max_frames = int(os.environ.get("MAX_RADAR_FRAMES", "36"))
    if max_frames < 1 or max_frames > 100:
        fail("MAX_RADAR_FRAMES musí byť 1 až 100")

    extent_path, extent = read_extent(raw)

    frames: list[tuple[int, Path]] = []
    for path in raw.rglob("*.png"):
        match = PNG_RE.match(path.name)
        if match and path.stat().st_size > 100:
            frames.append((int(match.group(1)), path))

    frames.sort(key=lambda item: item[0])
    frames = frames[-max_frames:]
    if not frames:
        fail("nenašla sa žiadna radarová PNG snímka s názvom <unix_timestamp>.png")

    if publish.exists():
        shutil.rmtree(publish)
    publish.mkdir(parents=True, exist_ok=True)

    manifest_frames = []
    for timestamp, source in frames:
        target = publish / f"{timestamp}.png"
        shutil.copy2(source, target)
        manifest_frames.append(
            {
                "time": timestamp,
                "file": target.name,
                "bytes": target.stat().st_size,
            }
        )

    shutil.copy2(extent_path, publish / "extent_index.json")

    latest = manifest_frames[-1]["time"]
    manifest = {
        "version": 1,
        "source": "SHMU",
        "product": "zmax",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "latestTime": latest,
        "latestIso": datetime.fromtimestamp(latest, timezone.utc).isoformat().replace("+00:00", "Z"),
        "extent": extent,
        "frames": manifest_frames,
        "attribution": "Radarové dáta: Slovenský hydrometeorologický ústav (SHMÚ)",
    }
    (publish / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"Manifest hotový: {len(manifest_frames)} snímok, "
        f"najnovšia {manifest['latestIso']}, výstup {publish}"
    )


if __name__ == "__main__":
    main()
