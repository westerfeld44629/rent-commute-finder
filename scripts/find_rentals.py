"""使用标准化证据输入，导出 JSON / Markdown / CSV。"""
import argparse
import json
import sys
from pathlib import Path

from rental_core import evaluate, render_csv, render_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON 证据文件")
    parser.add_argument("--output-dir", required=True, help="报告目录")
    parser.add_argument("--as-of", help="仅用于离线回放的带时区评估时间；生产省略")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        report = evaluate(payload, now=args.as_of)
        dest = Path(args.output_dir)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (dest / "report.md").write_text(render_markdown(report), encoding="utf-8")
        (dest / "listings.csv").write_text(render_csv(report), encoding="utf-8-sig", newline="")
    except (ValueError, OSError) as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 2
    print(str(dest.resolve()))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
