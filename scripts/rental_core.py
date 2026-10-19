"""逐套房源筛选与报告；只处理输入证据，不执行网络采集。Python 3.10+。"""

import copy
import csv
import html
import io
import math
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VERSION = "1.1.1"
MODES = {"transit": "公共交通", "ebike": "电动车", "bike": "自行车", "car": "自驾"}
LABELS = {"matched": "符合", "pending": "待核实", "excluded": "不符合"}
FEATURES = {"private_bath": "独卫", "elevator": "电梯"}
KINDS = {"detail", "list", "user_evidence", "search_snippet"}


def clean(value):
    text = str(value if value is not None else "")
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[联系方式已隐藏]", text)
    text = re.sub(r"(?:微信|wechat|weixin|vx)\s*[:：=]?\s*[a-zA-Z0-9_-]{5,}", "[联系方式已隐藏]", text, flags=re.I)
    text = re.sub(r"\b(?:sk-[\w-]+|(?:token|api_key|password)\s*[:=]\s*\S+)", "[凭据已隐藏]", text, flags=re.I)
    return text.replace("\x00", "").strip()


def public_url(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        p = urlsplit(value)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return ""
        if any(c in value for c in ("\n", "\r", "<", ">", '"', " ")):
            return ""
        if clean(p.path) != p.path:
            return ""
        # 仅保留常用公开 ID 查询参数，丢弃 key、token、手机号及跟踪信息。
        query = [(k, v) for k, v in parse_qsl(p.query) if k in {"id", "house_id", "listing_id"} and re.fullmatch(r"[\w-]{1,128}", v) and clean(v) == v]
        return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(query), ""))
    except ValueError:
        return ""


def number(value, name, minimum=0, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} 必须是大于等于 {minimum} 的有限数字")
    return value


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("时间必须为带时区的 ISO 8601 字符串") from None
    if dt.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return dt.astimezone(timezone.utc)


def fresh(value, now, hours):
    if not value:
        return False
    try:
        age = (now - timestamp(value)).total_seconds() / 3600
        return 0 <= age <= hours
    except ValueError:
        return False


def validate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("requirements"), dict):
        raise ValueError("需要 requirements 对象")
    req = copy.deepcopy(payload["requirements"])
    for field in ("city", "office"):
        if not isinstance(req.get(field), str) or not req[field].strip():
            raise ValueError(f"requirements.{field} 不能为空")
    for field in ("budget_max", "commute_max_min"):
        number(req.get(field), field, 0.01)
    modes = req.get("modes")
    if not isinstance(modes, list) or not modes or any(not isinstance(m, str) or m not in MODES for m in modes) or len(set(modes)) != len(modes):
        raise ValueError("modes 必须是不重复的 transit/ebike/bike/car 列表")
    req.setdefault("mode_policy", "all")
    req.setdefault("budget_basis", "rent")
    req.setdefault("time_window", "weekday_peak")
    req.setdefault("must_have", [])
    req.setdefault("max_listing_age_hours", 48)
    req.setdefault("max_route_age_hours", 24)
    if req["mode_policy"] not in ("all", "any") or req["budget_basis"] not in ("rent", "monthly_total"):
        raise ValueError("mode_policy 或 budget_basis 无效")
    if req["time_window"] not in ("weekday_peak", "offpeak"):
        raise ValueError("time_window 必须为 weekday_peak/offpeak")
    if not isinstance(req["must_have"], list) or any(not isinstance(f, str) or f not in FEATURES for f in req["must_have"]):
        raise ValueError("must_have 当前支持 private_bath/elevator")
    for f in ("max_listing_age_hours", "max_route_age_hours"):
        number(req[f], f, 0.01)
    listings = payload.get("listings")
    if not isinstance(listings, list) or len(listings) > 5000:
        raise ValueError("listings 必须为列表，单次最多 5000 条")
    for i, item in enumerate(listings):
        if not isinstance(item, dict):
            raise ValueError(f"listings[{i}] 必须是对象")
        for f in ("rent", "monthly_total", "area_sqm"):
            number(item.get(f), f"listings[{i}].{f}", 0.01, nullable=True)
        if item.get("rent") is not None and item.get("monthly_total") is not None and item["monthly_total"] < item["rent"]:
            raise ValueError("总月支出不能小于月租")
        if not isinstance(item.get("source", {}), dict) or not isinstance(item.get("evidence", {}), dict) or not isinstance(item.get("routes", {}), dict):
            raise ValueError(f"listings[{i}] 的 source/evidence/routes 必须为对象")
        for obj, fields in ((item, ("community", "title", "area_basis")), (item.get("source", {}), ("platform", "listing_id", "url", "observed_at", "kind")), (item.get("evidence", {}), ("rent", "monthly_total", "private_bath", "elevator", "available"))):
            if any(f in obj and not isinstance(obj[f], str) for f in fields):
                raise ValueError(f"listings[{i}] 的文本字段必须是字符串，未知字段请省略")
        for f in ("private_bath", "elevator", "available", "monthly_total_complete"):
            if item.get(f) is not None and type(item[f]) is not bool:
                raise ValueError(f"listings[{i}].{f} 只能为 true/false/null")
        for mode, route in item.get("routes", {}).items():
            if mode not in MODES or not isinstance(route, dict):
                raise ValueError("routes 包含不支持的方式或无效对象")
            for f in ("duration_min", "upper_min"):
                number(route.get(f), f"routes.{mode}.{f}", nullable=True)
            if route.get("upper_min") is not None and route.get("duration_min") is not None and route["upper_min"] < route["duration_min"]:
                raise ValueError("upper_min 不得小于 duration_min")
            for f in ("door_to_door", "restriction_checked", "allowed"):
                if route.get(f) is not None and type(route[f]) is not bool:
                    raise ValueError(f"routes.{mode}.{f} 只能为 true/false/null")
            for f in ("basis", "source_url", "checked_at", "time_window", "upper_basis", "origin_ref", "destination"):
                if f in route and not isinstance(route[f], str):
                    raise ValueError(f"routes.{mode}.{f} 必须为字符串")
    if payload.get("synthetic") is not None and type(payload["synthetic"]) is not bool:
        raise ValueError("synthetic 必须为布尔值")
    return req


def identity(item, index):
    src = item.get("source", {})
    platform, listing_id = src.get("platform"), src.get("listing_id")
    if platform and listing_id:
        return (str(platform).strip().lower(), str(listing_id))
    url = public_url(src.get("url"))
    if url:
        # 未知查询参数可能是房间主键；若被公开URL清理丢弃，宁可保留候选，也不误并。
        raw_pairs = parse_qsl(urlsplit(src["url"]).query)
        if any(k not in {"id", "house_id", "listing_id", "utm_source", "utm_medium", "utm_campaign", "spm", "from"} for k, _ in raw_pairs):
            return ("record", index)
    return ("url", url) if url else ("record", index)


def deduplicate(listings):
    groups = {}
    for index, item in enumerate(listings):
        groups.setdefault(identity(item, index), []).append((index, item))
    result = []
    for group in groups.values():
        def observed(entry):
            try:
                return timestamp(entry[1].get("source", {}).get("observed_at"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)
        group.sort(key=observed, reverse=True)
        index, item = group[0]
        row = copy.deepcopy(item)
        conflicts = set()
        # 较旧挂牌允许价格更新；同一核验时点矛盾则隔离，不择优拼接字段。
        for other in group[1:]:
            if observed(other) == observed(group[0]):
                for f in ("rent", "monthly_total", "monthly_total_complete", "private_bath", "elevator", "available", "routes"):
                    if other[1].get(f) != item.get(f):
                        conflicts.add(f)
        row["_conflicts"] = sorted(conflicts)
        row["_duplicate_count"] = len(group) - 1
        row["_index"] = index + 1
        result.append(row)
    return result


def route_check(route, mode, req, now):
    if not route or route.get("duration_min") is None:
        return "unknown", "缺少路线时间"
    if route.get("allowed") is False and route.get("restriction_checked") is True and fresh(route.get("checked_at"), now, req["max_route_age_hours"]) and public_url(route.get("source_url")):
        return "no", "路线禁行"
    if route.get("basis") not in ("navigation", "measured"):
        return "unknown", "仅为模型估算"
    if not public_url(route.get("source_url")) or not fresh(route.get("checked_at"), now, req["max_route_age_hours"]):
        return "unknown", "路线来源或时效待核实"
    if route.get("door_to_door") is not True:
        return "unknown", "未覆盖门到门步行/进出园区"
    if route.get("destination") != req["office"]:
        return "unknown", "路线终点与办公楼不匹配"
    if route.get("time_window") != req["time_window"]:
        return "unknown", "通勤时段不匹配或未知"
    if mode in ("ebike", "bike", "car") and (route.get("restriction_checked") is not True or route.get("allowed") is not True):
        return "unknown", "路线通行限制待核实"
    duration = route["duration_min"]
    if duration > req["commute_max_min"]:
        return "no", "通勤超时"
    if route.get("upper_min") is None or not route.get("upper_basis", "").strip():
        return "unknown", "缺少保守时间上界或依据"
    if route["upper_min"] > req["commute_max_min"]:
        return "unknown", "临界时间，上界超过限制"
    return "yes", "导航预测达标" if route["basis"] == "navigation" else "输入实测记录达标"


def evaluate(payload, now=None):
    req = validate(payload)
    now = timestamp(now) if isinstance(now, str) else (now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError("评估时间必须包含时区")
    assumptions = []
    for field, desc in (("mode_policy", "多方式默认要求全部达标"), ("budget_basis", "预算默认只限制月租，另列杂费缺口"), ("time_window", "默认按工作日高峰，具体到岗时间待确认")):
        if field not in payload["requirements"]:
            assumptions.append(desc)
    deduped = deduplicate(payload["listings"])
    rows = []
    reason_counts = Counter()
    price_field = "rent" if req["budget_basis"] == "rent" else "monthly_total"
    for item in deduped:
        src = item.get("source", {})
        evidence = item.get("evidence", {})
        source_ok = src.get("kind") in KINDS - {"search_snippet"} and bool(public_url(src.get("url"))) and fresh(src.get("observed_at"), now, req["max_listing_age_hours"])
        reasons, failures, unknowns = [], [], []
        if not source_ok:
            unknowns.append("房源页面未实开、已过期或缺少来源")
        if item["_conflicts"]:
            unknowns.append("同一房源同一时点证据冲突：" + ",".join(item["_conflicts"]))

        def documented(field):
            return source_ok and isinstance(evidence.get(field), str) and bool(evidence[field].strip()) and field not in item["_conflicts"]

        price_field = "rent" if req["budget_basis"] == "rent" else "monthly_total"
        price = item.get(price_field)
        if price is None or not documented(price_field) or (price_field == "monthly_total" and item.get("monthly_total_complete") is not True):
            unknowns.append("预算金额或费用口径待核实")
        elif price > req["budget_max"]:
            failures.append("超预算")
        for f in req["must_have"]:
            if item.get(f) is None or not documented(f):
                unknowns.append(FEATURES[f] + "待核实")
            elif item[f] is False:
                failures.append("无" + FEATURES[f])
        if item.get("available") is None or not documented("available"):
            unknowns.append("是否仍可租待核实")
        elif item["available"] is False:
            failures.append("已下架或不可租")
        routes = {}
        states = []
        for mode in req["modes"]:
            route = item.get("routes", {}).get(mode, {})
            state, why = route_check(route, mode, req, now)
            origin_ref = src.get("listing_id") or public_url(src.get("url"))
            if not origin_ref or route.get("origin_ref") != origin_ref:
                state, why = "unknown", "路线起点未关联到该套房源"
            if "routes" in item["_conflicts"]:
                state, why = "unknown", "重复记录路线冲突"
            routes[mode] = {f: route.get(f) for f in ("duration_min", "upper_min", "basis", "checked_at", "time_window", "upper_basis", "origin_ref", "destination")}
            routes[mode] = {f: clean(v) if isinstance(v, str) else v for f, v in routes[mode].items()}
            routes[mode].update(state=state, reason=why, source_url=public_url(route.get("source_url")))
            states.append(state)
        if req["mode_policy"] == "all":
            route_state = "no" if "no" in states else ("yes" if all(s == "yes" for s in states) else "unknown")
        else:
            route_state = "yes" if "yes" in states else ("no" if all(s == "no" for s in states) else "unknown")
        if route_state == "no":
            failures.append("通勤条件不符")
        elif route_state == "unknown":
            unknowns.append("通勤待核实")
        status = "excluded" if failures else ("pending" if unknowns else "matched")
        reasons.extend(failures + unknowns)
        reason_counts.update(set(reasons))
        warnings = []
        if item.get("monthly_total_complete") is not True or not documented("monthly_total"):
            warnings.append("水电/服务费等总月支出未齐")
        if source_ok:
            warnings.append("设施为挂牌方自述，现场再确认")
        if payload.get("synthetic"):
            warnings.append("合成测试数据，非真实挂牌")
        usable = [r["upper_min"] for r in routes.values() if r["state"] == "yes"]
        sort_time = (max(usable) if req["mode_policy"] == "all" else min(usable)) if usable else math.inf
        rows.append({
            "record_id": f"R{item['_index']:04d}", "community": clean(item.get("community", "未提供")),
            "title": clean(item.get("title", "")), "rent": item.get("rent"),
            "monthly_total": item.get("monthly_total"), "monthly_total_complete": item.get("monthly_total_complete"),
            "area_sqm": item.get("area_sqm"), "area_basis": clean(item.get("area_basis", "未注明")),
            "private_bath": item.get("private_bath"), "elevator": item.get("elevator"),
            "feature_evidence": {f: clean(evidence.get(f, "")) for f in req["must_have"]},
            "price_evidence": clean(evidence.get(price_field, "")),
            "available_evidence": clean(evidence.get("available", "")),
            "status": status, "reasons": reasons, "warnings": warnings, "routes": routes,
            "source": {"platform": clean(src.get("platform", "未提供")), "listing_id": clean(src.get("listing_id", "")), "url": public_url(src.get("url")), "kind": src.get("kind") if src.get("kind") in KINDS else "unknown", "observed_at": clean(src.get("observed_at", ""))},
            "duplicates_removed": item["_duplicate_count"], "_sort_time": sort_time,
        })
    rows.sort(key=lambda r: ({"matched": 0, "pending": 1, "excluded": 2}[r["status"]], r["_sort_time"], r.get(price_field) or math.inf, r["record_id"]))
    matched = [r for r in rows if r["status"] == "matched"]
    recommendations = []
    for row in matched[:3]:
        policy_label = "全部方式达标" if req["mode_policy"] == "all" else "至少一种方式达标"
        price_label = "月租" if price_field == "rent" else "总月支出"
        recommendations.append({"record_id": row["record_id"], "reason": f"已记录的硬条件均符合；{policy_label}的保守时间 {row['_sort_time']:g} 分钟；{price_label} {row[price_field]:g} 元", "tradeoff": "；".join(row["warnings"]), "next_step": "核对原平台状态并约看，现场确认独卫、电梯与收费"})
    for row in rows:
        row.pop("_sort_time")
    # 不回传任意输入键或原始页面，降低联系方式/凭据进入报告的风险。
    public_req = {k: req[k] for k in ("city", "office", "budget_max", "commute_max_min", "modes", "mode_policy", "budget_basis", "time_window", "must_have", "max_listing_age_hours", "max_route_age_hours")}
    public_req["city"], public_req["office"] = clean(req["city"]), clean(req["office"])
    coverage = payload.get("coverage", [])
    if not isinstance(coverage, list):
        raise ValueError("coverage 必须为列表")
    coverage = [{k: clean(c.get(k, "")) for k in ("platform", "query", "result", "checked_at")} for c in coverage if isinstance(c, dict)]
    counts = Counter(r["status"] for r in rows)
    return {"version": VERSION, "synthetic": payload.get("synthetic", False), "evaluated_at": now.isoformat(), "requirements": public_req, "assumptions": assumptions, "coverage": coverage,
            "audit": {"input_records": len(payload["listings"]), "duplicates_removed": len(payload["listings"]) - len(rows), "unique_listings": len(rows), **{s: counts[s] for s in LABELS}, "reason_counts": dict(sorted(reason_counts.items())), "scope": "仅本轮输入/检索候选；未证明全网覆盖，未自动请求任何房源或地图平台"},
            "listings": rows, "recommendations": recommendations}


def cell(value):
    return html.escape(clean(value), quote=False).replace("|", "\\|").replace("\n", " / ").replace("\r", "")


def route_text(route):
    if not route or route.get("duration_min") is None:
        return "待核实"
    basis = {"navigation": "导航预测", "measured": "输入实测", "estimate": "估算"}.get(route.get("basis"), "口径未知")
    upper = f"~{route['upper_min']:g}" if route.get("upper_min") is not None else "（无上界）"
    return f"{route['duration_min']:g}{upper}分/{basis}/{route['reason']}"


def table_rows(report):
    modes = report["requirements"]["modes"]
    header = ["编号", "状态", "月租", "总月支出", "小区/房间", "面积及口径", "独卫", "电梯"] + [MODES[m] for m in modes] + ["来源链接", "核验时间", "证据/原因/缺口"]
    rows = []
    for row in report["listings"]:
        yn = lambda x: "是（挂牌自述）" if x is True else ("否（挂牌自述）" if x is False else "未知")
        evidence = "; ".join(f"{FEATURES[k]}:{v or '无证据'}" for k, v in row["feature_evidence"].items())
        details = "; ".join(filter(None, [row["price_evidence"], row["available_evidence"], evidence] + row["reasons"] + row["warnings"]))
        rows.append([row["record_id"], LABELS[row["status"]], row["rent"], row["monthly_total"] if row["monthly_total_complete"] is True else "未齐", row["community"] + " / " + row["title"], f"{row['area_sqm'] or '未知'}㎡ / {row['area_basis']}", yn(row["private_bath"]), yn(row["elevator"])] + [route_text(row["routes"][m]) for m in modes] + [row["source"]["url"], row["source"]["observed_at"], details])
    return header, rows


def render_markdown(report):
    req, audit = report["requirements"], report["audit"]
    lines = [f"# {cell(req['city'])}通勤租房报告", "", "**合成数据演示，非真实房源，不可用于租房决策。**" if report["synthetic"] else "报告基于提交证据，挂牌状态及条件仍需约看确认。", "",
             f"办公地点：{cell(req['office'])}。月预算 ≤{req['budget_max']:g} 元（{'仅月租' if req['budget_basis'] == 'rent' else '完整总月支出'}）；通勤 ≤{req['commute_max_min']:g} 分钟；方式：{'、'.join(MODES[m] for m in req['modes'])}，{'全部达标' if req['mode_policy'] == 'all' else '任一种达标'}；时段：{'工作日高峰' if req['time_window'] == 'weekday_peak' else '非高峰'}。", "",
             "假设：" + cell("；".join(report["assumptions"]) or "采用输入明确口径"), "",
             f"输入 {audit['input_records']} 条，去重 {audit['duplicates_removed']} 条，保留 {audit['unique_listings']} 套；符合 {audit['matched']}、待核实 {audit['pending']}、不符合 {audit['excluded']}。", "", "## 房源全表", "", "范围：本轮检索/输入的全部唯一候选，含待核实和不符合；不代表全网全部房源。", ""]
    header, rows = table_rows(report)
    lines += ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    lines += ["", "## 推荐", "", "排序：符合项优先，按所选通勤规则的保守时间、预算金额依次排序。"]
    if not report["recommendations"]:
        lines += ["", "暂无证据充分的符合项；不以待核实或超预算房源补足推荐数量。先补齐表中证据缺口。"]
    for rec in report["recommendations"]:
        lines += ["", f"- **{rec['record_id']}**：{cell(rec['reason'])}。代价/缺口：{cell(rec['tradeoff'])}。下一步：{cell(rec['next_step'])}。"]
    lines += ["", "## 检索覆盖与审计", "", cell(audit["scope"])]
    for cov in report["coverage"]:
        lines += ["", "- " + "；".join(cell(cov[k]) for k in ("platform", "query", "result", "checked_at"))]
    if not report["coverage"]:
        lines += ["", "未提供采集范围；不能据此宣称已完成平台搜索。"]
    lines += ["", "原因计数（同一套可有多项，不作互斥加总）：" + cell("；".join(f"{k} {v}" for k, v in audit["reason_counts"].items()) or "无"), "", "导航返回值是预测，模型估算没有已验证的统一误差范围。签约前按实际出入口、楼栋和通勤时段复核，不保证可租或保证到达时间。", ""]
    return "\n".join(lines)


def render_csv(report):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    header, rows = table_rows(report)
    writer.writerow(header)
    for row in rows:
        values = []
        for value in row:
            text = clean(value)
            # 防止房源标题/描述在 Excel 中变成公式。
            if text.lstrip().startswith(("=", "+", "-", "@")):
                text = "'" + text
            values.append(text)
        writer.writerow(values)
    return buffer.getvalue()
