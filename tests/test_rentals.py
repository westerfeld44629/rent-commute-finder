import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rental_core import evaluate, public_url, render_csv, render_markdown
from commute_calc import DEFAULTS, bike_min, evaluate as estimate, metro_ride_min

NOW = "2026-10-19T09:00:00+08:00"
SEEN = "2026-10-19T08:00:00+08:00"
OFFICE = "xx办公楼（虚构地址）"


def listing(listing_id="demo-1"):
    route = {"duration_min": 40, "upper_min": 50, "basis": "navigation", "source_url": "https://maps.example.invalid/route", "checked_at": SEEN, "time_window": "weekday_peak", "door_to_door": True, "restriction_checked": True, "allowed": True, "origin_ref": listing_id, "destination": OFFICE, "upper_basis": "合成测试：高峰预测上界并加入进出楼步行"}
    return {"community": "演示小区A", "title": "合成房间1", "rent": 2300, "area_sqm": 20, "area_basis": "房间面积", "private_bath": True, "elevator": True, "available": True,
            "source": {"platform": "synthetic", "listing_id": listing_id, "url": "https://housing.example.invalid/room/" + listing_id, "observed_at": SEEN, "kind": "detail"},
            "evidence": {"rent": "合成测试：月租2300元", "private_bath": "合成测试：该房间独立卫生间", "elevator": "合成测试：有电梯", "available": "合成测试：当前可租"},
            "routes": {"transit": copy.deepcopy(route), "ebike": copy.deepcopy(route)}}


def payload(*items):
    return {"synthetic": True, "requirements": {"city": "xx市", "office": OFFICE, "budget_max": 2500, "commute_max_min": 60, "modes": ["transit", "ebike"], "must_have": ["private_bath", "elevator"]}, "listings": list(items) or [listing()]}


class RentalTests(unittest.TestCase):
    def report(self, data):
        return evaluate(data, NOW)

    def status(self, item):
        return self.report(payload(item))["listings"][0]["status"]

    def test_match(self):
        self.assertEqual(self.status(listing()), "matched")

    def test_unknown_feature_is_pending(self):
        item = listing(); item["elevator"] = None
        self.assertEqual(self.status(item), "pending")

    def test_feature_without_evidence(self):
        item = listing(); item["evidence"].pop("private_bath")
        self.assertEqual(self.status(item), "pending")

    def test_no_elevator_excluded(self):
        item = listing(); item["elevator"] = False
        self.assertEqual(self.status(item), "excluded")

    def test_over_budget(self):
        item = listing(); item["rent"] = 2500.01
        self.assertEqual(self.status(item), "excluded")

    def test_budget_boundary(self):
        item = listing(); item["rent"] = 2500
        self.assertEqual(self.status(item), "matched")

    def test_unrounded_commute_limit(self):
        item = listing(); item["routes"]["ebike"].update(duration_min=60.01, upper_min=61)
        self.assertEqual(self.status(item), "excluded")

    def test_all_vs_any(self):
        item = listing(); item["routes"]["ebike"].update(duration_min=70, upper_min=75)
        data = payload(item)
        self.assertEqual(self.report(data)["audit"]["excluded"], 1)
        data["requirements"]["mode_policy"] = "any"
        self.assertEqual(self.report(data)["audit"]["matched"], 1)

    def test_unknown_second_mode_all_pending(self):
        item = listing(); item["routes"].pop("ebike")
        self.assertEqual(self.status(item), "pending")

    def test_restrictions_unknown(self):
        item = listing(); item["routes"]["ebike"]["restriction_checked"] = False
        self.assertEqual(self.status(item), "pending")

    def test_forbidden_route(self):
        item = listing(); item["routes"]["ebike"]["allowed"] = False
        self.assertEqual(self.status(item), "excluded")

    def test_estimate_only(self):
        item = listing(); item["routes"]["ebike"]["basis"] = "estimate"
        self.assertEqual(self.status(item), "pending")

    def test_near_time_limit(self):
        item = listing(); item["routes"]["transit"]["upper_min"] = 65
        self.assertEqual(self.status(item), "pending")

    def test_upper_without_basis(self):
        item = listing(); item["routes"]["transit"].pop("upper_basis")
        self.assertEqual(self.status(item), "pending")

    def test_wrong_destination(self):
        item = listing(); item["routes"]["transit"]["destination"] = "别的办公楼"
        self.assertEqual(self.status(item), "pending")

    def test_wrong_room_route(self):
        item = listing(); item["routes"]["transit"]["origin_ref"] = "other-room"
        self.assertEqual(self.status(item), "pending")

    def test_not_door_to_door(self):
        item = listing(); item["routes"]["transit"]["door_to_door"] = False
        self.assertEqual(self.status(item), "pending")

    def test_wrong_time_window(self):
        item = listing(); item["routes"]["transit"]["time_window"] = "offpeak"
        self.assertEqual(self.status(item), "pending")

    def test_stale_listing(self):
        item = listing(); item["source"]["observed_at"] = "2026-10-01T08:00:00+08:00"
        self.assertEqual(self.status(item), "pending")

    def test_future_observation(self):
        item = listing(); item["source"]["observed_at"] = "2027-01-01T00:00:00Z"
        self.assertEqual(self.status(item), "pending")

    def test_stale_route(self):
        item = listing(); item["routes"]["ebike"]["checked_at"] = "2026-10-01T08:00:00+08:00"
        self.assertEqual(self.status(item), "pending")

    def test_search_snippet(self):
        item = listing(); item["source"]["kind"] = "search_snippet"
        self.assertEqual(self.status(item), "pending")

    def test_unavailable(self):
        item = listing(); item["available"] = False
        self.assertEqual(self.status(item), "excluded")

    def test_duplicate_same_room(self):
        data = payload(listing(), listing())
        self.assertEqual(self.report(data)["audit"]["unique_listings"], 1)
        self.assertEqual(self.report(data)["audit"]["duplicates_removed"], 1)

    def test_same_community_distinct_rooms(self):
        self.assertEqual(self.report(payload(listing("1"), listing("2")))["audit"]["unique_listings"], 2)

    def test_different_platform_not_merged(self):
        other = listing(); other["source"]["platform"] = "another"
        self.assertEqual(self.report(payload(listing(), other))["audit"]["unique_listings"], 2)

    def test_duplicate_conflict(self):
        other = listing(); other["rent"] = 1200
        report = self.report(payload(listing(), other))
        self.assertEqual(report["audit"]["pending"], 1)
        self.assertFalse(report["recommendations"])

    def test_latest_duplicate_wins(self):
        older = listing(); older["rent"] = 2600; older["source"]["observed_at"] = "2026-10-18T08:00:00+08:00"
        self.assertEqual(self.report(payload(older, listing()))["audit"]["matched"], 1)

    def test_monthly_total_unknown(self):
        data = payload(); data["requirements"]["budget_basis"] = "monthly_total"
        self.assertEqual(self.report(data)["audit"]["pending"], 1)

    def test_monthly_total_exceeds_budget(self):
        data = payload(); data["requirements"]["budget_basis"] = "monthly_total"
        data["listings"][0].update(monthly_total=2700, monthly_total_complete=True)
        data["listings"][0]["evidence"]["monthly_total"] = "合成测试：全月费用2700元"
        self.assertEqual(self.report(data)["audit"]["excluded"], 1)

    def test_zero_matches_no_filler(self):
        item = listing(); item["rent"] = 9000
        report = self.report(payload(item))
        self.assertFalse(report["recommendations"])
        self.assertIn("暂无证据充分", render_markdown(report))

    def test_full_table_includes_rejected_and_pending(self):
        a, b, c = listing("a"), listing("b"), listing("c")
        b["elevator"] = None; c["rent"] = 3000
        report = self.report(payload(a, b, c))
        self.assertEqual(len(report["listings"]), 3)
        self.assertEqual({r["status"] for r in report["listings"]}, {"matched", "pending", "excluded"})
        self.assertIn("R0003", render_csv(report))

    def test_empty_input(self):
        data = payload(); data["listings"] = []
        self.assertEqual(self.report(data)["audit"]["unique_listings"], 0)

    def test_invalid_numbers(self):
        for value in (-1, float("nan"), float("inf"), True, "2300"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                item = listing(); item["rent"] = value; self.status(item)

    def test_invalid_bool_string(self):
        item = listing(); item["elevator"] = "false"
        with self.assertRaises(ValueError): self.status(item)

    def test_invalid_source_kind(self):
        item = listing(); item["source"]["kind"] = []
        with self.assertRaises(ValueError): self.status(item)

    def test_invalid_upper(self):
        item = listing(); item["routes"]["transit"]["upper_min"] = 30
        with self.assertRaises(ValueError): self.status(item)

    def test_source_url_credentials(self):
        self.assertEqual(public_url("https://name:secret@example.com/room"), "")
        self.assertEqual(public_url("javascript:alert(1)"), "")
        self.assertEqual(public_url("https://example.com/room?id=abc&token=secret"), "https://example.com/room?id=abc")

    def test_output_does_not_echo_arbitrary_fields(self):
        item = listing(); item["phone"] = "13912345678"; item["token"] = "secret-sentinel"
        item["title"] = "微信 abcdefg 电话13912345678 <script>alert(1)</script>"
        data = payload(item); data["requirements"]["secret"] = "secret-sentinel"
        report = self.report(data)
        text = json.dumps(report, ensure_ascii=False) + render_markdown(report) + render_csv(report)
        self.assertNotIn("13912345678", text)
        self.assertNotIn("abcdefg", text)
        self.assertNotIn("secret-sentinel", text)
        self.assertNotIn("<script>", render_markdown(report))

    def test_csv_formula_injection(self):
        item = listing(); item["community"] = "=HYPERLINK(1)"
        self.assertIn("'=HYPERLINK", render_csv(self.report(payload(item))))

    def test_no_input_mutation(self):
        data = payload(); before = copy.deepcopy(data); self.report(data)
        self.assertEqual(data, before)

    def test_estimator_no_double_dwell(self):
        self.assertEqual(metro_ride_min(3800, 3, DEFAULTS), 6)
        self.assertEqual(bike_min(0, DEFAULTS), 0)

    def test_estimator_invalid_speed(self):
        with self.assertRaises(ValueError): estimate({"office": {}, "params": {"ebike_kmh": 0}})

    def test_unknown_url_query_not_merged(self):
        first, second = listing(), listing()
        first["source"].pop("listing_id"); second["source"].pop("listing_id")
        first["source"]["url"] = "https://example.com/room?room=1"
        second["source"]["url"] = "https://example.com/room?room=2"
        self.assertEqual(self.report(payload(first, second))["audit"]["unique_listings"], 2)

    def test_route_text_redacted(self):
        item = listing(); item["routes"]["ebike"]["upper_basis"] += " 联系13912345678"
        self.assertNotIn("13912345678", json.dumps(self.report(payload(item)), ensure_ascii=False))

    def test_total_below_rent_rejected(self):
        item = listing(); item["monthly_total"] = 1000
        with self.assertRaises(ValueError): self.status(item)

    def test_schema_and_demo_audit(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "examples" / "demo-input.json").read_text(encoding="utf-8"))
        report = self.report(data)
        self.assertEqual({k: report["audit"][k] for k in ("input_records", "unique_listings", "duplicates_removed", "matched", "pending", "excluded")}, {"input_records": 9, "unique_listings": 8, "duplicates_removed": 1, "matched": 2, "pending": 4, "excluded": 2})


if __name__ == "__main__":
    unittest.main()
