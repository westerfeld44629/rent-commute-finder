"""以允许列表构建可分发预览ZIP；不包含虚拟环境/抓取数据/本地配置。"""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from rental_core import VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [root / n for n in ("SKILL.md", "README.md", "LICENSE", "requirements-mcp.txt", "PHASE_REPORT.md", ".gitignore", ".gitattributes")]
    for folder, patterns in (("scripts", ("*.py",)), ("references", ("*.md", "input.schema.json")), ("examples", ("*.md", "demo-input.json", "demo-report.json", "demo-listings.csv")), ("tests", ("test_rentals.py", "mcp_smoke.py")), ("evals", ("cases.json",))):
        for pattern in patterns:
            paths.extend(sorted((root / folder).glob(pattern)))
    paths = sorted(set(paths))
    manifest = {"version": VERSION, "channel": "preview", "files": []}
    archive = out / f"rent-commute-finder-{VERSION}-preview.zip"
    prefix = "rent-commute-finder/"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"发布文件缺失或是符号链接：{path.name}")
            name = path.relative_to(root).as_posix()
            data = path.read_bytes()
            zf.writestr(prefix + name, data)
            manifest["files"].append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        zf.writestr(prefix + "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "files": len(paths), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
