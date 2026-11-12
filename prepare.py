"""Verify the qualified S4B application files used as build inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = Path("payload/App/v5")
ASSETS = {
    APP / "frontend/logo.png": "873fc35fdf01d795def96127d74268c7d0cb7db7bc44f5a2537f789bc7289be8",
    APP / "scripts/gary.ico": "dc607cd8f403e86ae328093664b3438c3815ad902ed5c47e58d057c02e9bae26",
}


def verify_sources():
    manifest = json.loads((ROOT / "SHA256_SOURCES.json").read_text(encoding="utf-8"))
    sources = {Path(name): digest for name, digest in manifest.items()
               if name.startswith("payload/") and name != "payload/App/v5/package.json"}
    for name, digest in (sources | ASSETS).items():
        target = ROOT / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source S4B manquante ou divergente : {name}")
    return tuple(sources | ASSETS)


if __name__ == "__main__":
    print(f"{len(verify_sources())} sources applicatives et ressources vérifiées.")
