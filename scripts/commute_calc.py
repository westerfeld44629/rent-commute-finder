#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通勤时间计算器 —— rent-commute-finder 技能配套脚本

给定「房源→最近地铁站距离」「最近站→目标站站间距」「目标站→办公楼距离」，
输出公共交通 / 骑行 / 电动车 / 自驾四种方式的探索估算。
内置地点和里程均为虚构合成数据，不对应真实用户地址。

用法：
  python commute_calc.py --demo
  python commute_calc.py --config config.json
  python commute_calc.py --config config.json --json

config.json 结构：
{
  "office": {
    "name": "xx办公楼（虚构地址）",
    "station": "示例办公站",
    "station_to_office_m": 500
  },
  "params": { "detour_factor": 1.3 },
  "stations": [
    {
      "area": "示例小区A",
      "name": "示例车站A",
      "house_to_station_m": 500,
      "stops": 4,
      "ride_min": 12,
      "straight_to_office_m": 6000
    }
  ]
}

口径（可在 params 里覆盖）：
  步行速度      80 m/min
  进站候车      5 min
  地铁旅行速度  38 km/h（已含停站；默认不另加停站）
  骑行均速      人力 13 km/h / 电动车 20 km/h（含红绿灯的实际均速）
  自驾非高峰    28 km/h
  自驾高峰      15 km/h
  道路绕行系数  1.3（直线距离 → 道路距离）
"""

import argparse
import json
import math
import sys
import unicodedata

DEFAULTS = {
    "walk_speed_m_per_min": 80,
    "wait_min": 5,
    "metro_kmh": 38,
    "dwell_min_per_stop": 0,
    "bike_kmh": 13,
    "ebike_kmh": 20,
    "car_offpeak_kmh": 28,
    "car_peak_kmh": 15,
    "parking_min": 4,
    "detour_factor": 1.3,
}


def disp_width(s):
    """中文字符按 2 列宽计算，用于表格对齐"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def pad(s, width, align="left"):
    gap = width - disp_width(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def metro_ride_min(distance_m, stops, cfg):
    speed_m_per_min = cfg["metro_kmh"] * 1000 / 60
    return distance_m / speed_m_per_min + stops * cfg["dwell_min_per_stop"]


def transit_total(house_to_station_m, ride_min, station_to_office_m, cfg):
    walk1 = house_to_station_m / cfg["walk_speed_m_per_min"]
    walk2 = station_to_office_m / cfg["walk_speed_m_per_min"]
    return walk1 + cfg["wait_min"] + ride_min + walk2


def bike_min(straight_m, cfg, mode="ebike"):
    kmh = cfg["ebike_kmh"] if mode == "ebike" else cfg["bike_kmh"]
    road_km = straight_m * cfg["detour_factor"] / 1000
    return road_km / kmh * 60


def car_min(straight_m, cfg, peak=False):
    kmh = cfg["car_peak_kmh"] if peak else cfg["car_offpeak_kmh"]
    road_km = straight_m * cfg["detour_factor"] / 1000
    return road_km / kmh * 60 + cfg["parking_min"]


def evaluate(config):
    cfg = dict(DEFAULTS)
    cfg.update(config.get("params", {}))
    for key, value in cfg.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"参数 {key} 必须是非负有限数字")
        if key in ("walk_speed_m_per_min", "metro_kmh", "bike_kmh", "ebike_kmh", "car_offpeak_kmh", "car_peak_kmh", "detour_factor") and value == 0:
            raise ValueError(f"参数 {key} 必须大于 0")
    office = config["office"]
    rows = []

    for st in config["stations"]:
        ride = st.get("ride_min")
        if ride is None and st.get("distance_m") is not None:
            ride = metro_ride_min(st["distance_m"], st["stops"], cfg)
        if ride is None:
            raise ValueError(f"站点 {st.get('area')} 缺少 ride_min 或 distance_m")

        transit = transit_total(
            st["house_to_station_m"], ride, office["station_to_office_m"], cfg
        )
        row = {
            "area": st["area"],
            "station": st["name"],
            "house_to_station_m": st["house_to_station_m"],
            "stops": st["stops"],
            "ride_min": round(ride, 1),
            "transit_min": round(transit),
        }
        straight = st.get("straight_to_office_m")
        if straight is not None:
            row["ebike_min"] = round(bike_min(straight, cfg, "ebike"))
            row["bike_min"] = round(bike_min(straight, cfg, "bike"))
            row["car_offpeak_min"] = round(car_min(straight, cfg, False))
            row["car_peak_min"] = round(car_min(straight, cfg, True))
        rows.append(row)

    rows.sort(key=lambda r: r["transit_min"])
    return rows


DEMO = {
    "office": {
        "name": "xx办公楼（虚构地址）",
        "station": "示例办公站",
        "station_to_office_m": 500,
    },
    "params": {"detour_factor": 1.3},
    "stations": [
        {"area": "示例小区A", "name": "示例车站A", "house_to_station_m": 500,
         "stops": 4, "distance_m": 6000, "straight_to_office_m": 6000},
        {"area": "示例小区B", "name": "示例车站B", "house_to_station_m": 600,
         "stops": 3, "distance_m": 4500, "straight_to_office_m": 7000},
        {"area": "示例小区C", "name": "示例车站C", "house_to_station_m": 800,
         "stops": 5, "distance_m": 8000, "straight_to_office_m": 9000},
        {"area": "示例小区D", "name": "示例车站D", "house_to_station_m": 700,
         "stops": 3, "distance_m": 5000, "straight_to_office_m": 8000},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="通勤时间计算器")
    ap.add_argument("--config", help="配置文件路径（JSON）")
    ap.add_argument("--demo", action="store_true", help="用内置示例跑一遍")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if args.demo:
        config = DEMO
    elif args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        ap.print_help()
        sys.exit(1)

    rows = evaluate(config)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    print(f"办公地点：{config['office']['name']}")
    print(f"目标站：{config['office']['station']}，出站步行 {config['office']['station_to_office_m']} m")
    print()

    cols = [
        ("小区", 18, "left"), ("最近站", 14, "left"), ("距站", 7, "right"),
        ("站数", 5, "right"), ("公交", 7, "right"), ("电动车", 8, "right"),
        ("自行车", 8, "right"), ("自驾平峰", 9, "right"), ("自驾高峰", 9, "right"),
    ]
    print("".join(pad(c[0], c[1], c[2]) for c in cols))
    total_w = sum(c[1] for c in cols)
    print("-" * total_w)

    for r in rows:
        vals = [
            (r["area"], 18, "left"), (r["station"], 14, "left"),
            (f"{r['house_to_station_m']}m", 7, "right"),
            (str(r["stops"]), 5, "right"),
            (f"{r['transit_min']}分", 7, "right"),
            (f"{r.get('ebike_min', '—')}分", 8, "right"),
            (f"{r.get('bike_min', '—')}分", 8, "right"),
            (f"{r.get('car_offpeak_min', '—')}分", 9, "right"),
            (f"{r.get('car_peak_min', '—')}分", 9, "right"),
        ]
        print("".join(pad(v[0], v[1], v[2]) for v in vals))

    print()
    print("注：本演示仅作模型估算，未经误差校准；不是已核验房源或门到门导航。")
    print("    电动车时间未扣除禁行路段，使用前须单独核实。")


if __name__ == "__main__":
    main()
