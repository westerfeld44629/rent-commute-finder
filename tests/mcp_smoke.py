"""真实 stdio 握手/工具发现/调用测试；不访问真实房源或地图，不写客户端配置。"""
import asyncio
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def unpack(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


async def run():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "scripts" / "mcp_server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "rent-commute-finder"
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"get_rental_input_contract", "evaluate_rentals"}
            contract = unpack(await session.call_tool("get_rental_input_contract", {}))
            assert contract["schema"]["properties"]["requirements"]["required"]
            data = json.loads((ROOT / "examples" / "demo-input.json").read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(contract["schema"])
            Draft202012Validator(contract["schema"]).validate(data)
            current = datetime.now(timezone.utc) - timedelta(minutes=1)
            for item in data["listings"]:
                item["source"]["observed_at"] = (current - timedelta(days=4) if item["source"]["listing_id"] == "demo-8" else current).isoformat()
                for route in item.get("routes", {}).values():
                    route["checked_at"] = current.isoformat()
            report = unpack(await session.call_tool("evaluate_rentals", {"payload": data}))
            assert report["audit"]["input_records"] == 9, report
            assert report["audit"]["duplicates_removed"] == 1, report
            assert report["audit"]["matched"] == 2, report
            assert report["audit"]["pending"] == 4, report
            assert report["audit"]["excluded"] == 2, report
            assert report["synthetic"] is True
            markdown = unpack(await session.call_tool("evaluate_rentals", {"payload": data, "output_format": "markdown"}))
            assert "合成数据演示" in markdown["content"]
            csv = unpack(await session.call_tool("evaluate_rentals", {"payload": data, "output_format": "csv"}))
            assert "编号,状态" in csv["content"]
            bad = copy.deepcopy(data)
            bad["requirements"]["budget_max"] = -1
            rejected = await session.call_tool("evaluate_rentals", {"payload": bad})
            assert rejected.isError
            print("PASS: MCP stdio initialize, tools/list, contract, json/markdown/csv calls, invalid input rejection")
            print(json.dumps(report["audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(asyncio.wait_for(run(), timeout=45))
