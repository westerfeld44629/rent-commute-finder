"""stdio MCP 服务；不抓取平台，不写报告文件，不更改客户端配置。"""
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from rental_core import VERSION, evaluate, render_csv, render_markdown

mcp = FastMCP("rent-commute-finder")


@mcp.tool()
def get_rental_input_contract() -> dict:
    """返回房源评估输入结构。房源和地图证据须由宿主检索或授权数据源提供。"""
    root = Path(__file__).resolve().parent.parent
    return {
        "version": VERSION,
        "schema": json.loads((root / "references" / "input.schema.json").read_text(encoding="utf-8")),
        "collection_rules": [
            "先定位办公楼与可用出入口；不将办公地点所在行政区误当成唯一居住范围。",
            "检索公交直达/换乘/接驳和电动车可达片区，保留平台覆盖及失败原因。",
            "每套记录真实详情链接、房源ID、带时区核验时间及预算/独卫/电梯/可租证据。",
            "不同房间不能按小区合并，搜索摘要仅作线索。未知设施用 null。",
            "两种方式默认 all；输入 any 才允许仅一种达标。",
            "公交和电动车路线分别记录；导航为预测，禁行未知或模型估算进入待核实。",
            "不含自动房源搜索、地理编码或地图 API；不传联系方式、凭据、整页原文。",
        ],
    }


@mcp.tool()
def evaluate_rentals(payload: dict, output_format: str = "json") -> dict:
    """筛选输入证据，输出全部唯一房源与推荐。不是实时房源搜索工具。支持 json/markdown/csv。"""
    if output_format not in ("json", "markdown", "csv"):
        raise ValueError("output_format 必须为 json/markdown/csv")
    report = evaluate(payload)
    if output_format == "json":
        return report
    return {"audit": report["audit"], "synthetic": report["synthetic"], "content": render_markdown(report) if output_format == "markdown" else render_csv(report)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
