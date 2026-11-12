"""Build the portable ZIP in an isolated staging directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import ROOT, verify_sources

VERSION = "3.14.4"
NODE_VERSION = "24.22.1"


def extract_verified(archive, expected, destination):
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected.lower():
            raise ValueError(f"SHA-256 incorrect : {archive.name}")
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            relative = Path(item.filename)
            if relative.is_absolute() or relative.drive or ".." in relative.parts:
                raise ValueError(f"Chemin ZIP interdit : {archive.name}")
        bundle.extractall(destination)


def packaging_file(file, root):
    excluded = {".links", "__pycache__", ".vite-temp", ".vite", "DEPENDENCIES_VALIDATED"}
    return file.is_file() and file.suffix.lower() != ".log" and not excluded.intersection(file.relative_to(root).parts)


def run(arguments, cwd, env=None):
    subprocess.run([str(arg) for arg in arguments], cwd=cwd, env=env, check=True)


def build(output, python_zip, python_sha256, node_zip, node_sha256):
    sources = verify_sources()
    if output.exists():
        raise FileExistsError(f"Destination déjà présente : {output}")
    with tempfile.TemporaryDirectory(prefix="gary-build-") as temp:
        work = Path(temp)
        stage = work / "portable"
        for name in sources:
            target = stage / name.relative_to("payload")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        app = stage / "App/v5"
        runtime = app / "runtime/python"
        extract_verified(python_zip, python_sha256, runtime)
        path_config = runtime / "python314._pth"
        original_path_config = path_config.read_bytes()
        with path_config.open("a", encoding="utf-8") as config:
            config.write("\n..\\..\\..\n")
        actual = subprocess.check_output(
            [runtime / "python.exe", "-I", "-c",
             "import ctypes, sqlite3, ssl, struct, sys; print(sys.version.split()[0], struct.calcsize('P')*8)"],
            stderr=subprocess.STDOUT, text=True)
        if actual.strip() != f"{VERSION} 64":
            raise ValueError("Python privé attendu : 3.14.4 x64")
        run([runtime / "python.exe", "-I", "-B", "-c",
             "import v5.server, v5.gary_v5.windows_vault"], work)
        extract_verified(node_zip, node_sha256, work / "node")
        node_dir = work / "node" / f"node-v{NODE_VERSION}-win-x64"
        node = node_dir / "node.exe"
        if subprocess.check_output([node, "--version"], text=True).strip() != f"v{NODE_VERSION}":
            raise ValueError("Node privé attendu : 24.22.1 x64")
        npm = node_dir / "node_modules/npm/bin/npm-cli.js"
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(ROOT / "payload/App/v5" / name, app / name)
        env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(app / "runtime/browser"),
               "npm_config_cache": str(work / "npm-cache")}
        run([node, npm, "ci", "--no-audit", "--no-fund", "--registry=https://registry.npmjs.org"], app, env)
        run([node, "node_modules/vite/bin/vite.js", "build", "--config", "vite.config.mjs"], app, env)
        run([node, "node_modules/playwright/cli.js", "install", "chromium", "--only-shell"], app, env)
        browser = app / "runtime/browser"
        expected = json.loads((ROOT / "runtimes.lock.json").read_text(encoding="utf-8"))["browser"]
        actual_browser = {}
        for file in browser.rglob("*"):
            if packaging_file(file, browser):
                with file.open("rb") as stream:
                    actual_browser[file.relative_to(browser).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual_browser != expected:
            raise ValueError("Fichiers Chromium/FFmpeg/winldd divergents du verrou")
        env["GARY_PLAYWRIGHT"] = str(app / "node_modules/playwright/index.mjs")
        run([node, ROOT / "S4-UI/recette.mjs", app / "dist"], app, env)
        run([node, npm, "prune", "--omit=dev", "--no-audit", "--no-fund", "--offline"], app, env)

        private_node = app / "runtime/node"
        private_node.mkdir()
        for file in node_dir.iterdir():
            if file.name.lower() in {"node.exe", "license", "readme.md"} or file.suffix.lower() == ".dll":
                shutil.copyfile(file, private_node / file.name)
        maintenance = stage / "MaintenanceRuntime"
        shutil.copytree(runtime, maintenance)
        (maintenance / path_config.name).write_bytes(original_path_config)
        for name in ("GaryUpdate.pyw", "maintenance_transaction.py"):
            shutil.copyfile(ROOT / "S4A-TER" / name, maintenance / name)
        candidate = work / "Gary_V5_Portable.zip"
        with zipfile.ZipFile(candidate, "x", zipfile.ZIP_DEFLATED) as bundle:
            for file in sorted(stage.rglob("*")):
                if packaging_file(file, stage):
                    name = file.relative_to(stage).as_posix()
                    bundle.writestr(zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)),
                                    file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(candidate) as bundle:
            if bundle.testzip() is not None:
                raise ValueError("Archive portable corrompue")
        output.mkdir(parents=True)
        shutil.copyfile(candidate, output / candidate.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    for runtime in ("python", "node"):
        parser.add_argument(f"--{runtime}-zip", type=Path, required=True)
        parser.add_argument(f"--{runtime}-sha256", required=True)
    args = parser.parse_args()
    try:
        build(args.output.resolve(), args.python_zip.resolve(), args.python_sha256,
              args.node_zip.resolve(), args.node_sha256)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Construction portable interrompue : {error}\n")





