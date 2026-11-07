"""Package the Firefox companion for temporary loading or Mozilla submission."""
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "browser-extension/firefox"
version = json.loads((source / "manifest.json").read_text())["version"]
output = root / "out" / f"decky-downloader-sender-{version}-unsigned.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(root / "LICENSE", "LICENSE")
    archive.write(root / "downloader/remote.js", "remote.js")
    for path in sorted(source.iterdir()):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Unexpected extension input")
        archive.write(path, path.name)
print(output)
