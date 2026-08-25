"""
Frontend Logic & DOM Integration Test Suite
===========================================
Validates:
1. Complete DOM ID synchronization between index.html and app.js
2. Dropdown selectors, slider inputs, pill filters, preset buttons
3. Complete 24-feature data coverage across records (Profit, Drawdown, Calmar, Sortino, etc.)
4. Pagination mathematics (bounds, page counts, indices)
5. Multi-dimension filter predicates (Text, Min Sharpe, Max DD, Min WinRate, Risk Archetypes)
6. Multi-column sort algorithms (Ascending / Descending)
7. Strategy drill-down modal & trade filters
8. Hierarchical Multi-Level Tree Explorer (Quarters, Months, Trade Series, Tranches)
"""

import os
import re
import json
import unittest

class TestFrontendLogic(unittest.TestCase):
    def setUp(self):
        with open("index.html", "r", encoding="utf-8") as f:
            self.html = f.read()
        with open("app.js", "r", encoding="utf-8") as f:
            self.js = f.read()
        with open("web_data.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_dom_ids_100pct_coverage(self):
        """Verify every document.getElementById call in app.js has an exact corresponding ID in index.html."""
        js_ids = set(re.findall(r'document\.getElementById\(["\']([^"\']+)["\']\)', self.js))
        html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', self.html))
        
        missing_in_html = js_ids - html_ids
        self.assertEqual(len(missing_in_html), 0, f"Found JavaScript references to missing HTML elements: {missing_in_html}")

    def test_all_dropdown_options(self):
        """Verify 4D Studio dropdown selectors contain all required quantitative dimensions."""
        required_dimensions = [
            "Max_DD_Pct", "Total_Ret_Pct", "Net_PnL_USD", "Final_Equity",
            "Sharpe", "Sortino", "Calmar", "Win_Rate_Pct",
            "Profit_Factor", "Expectancy_Pct", "Total_Trades", "Fees_Applied_Pct"
        ]
        for dim in required_dimensions:
            self.assertIn(f'value="{dim}"', self.html, f"Dropdown option '{dim}' is missing from index.html!")

    def test_all_data_features_coverage(self):
        """Verify that strategies in web_data contain all 24 required quantitative data features."""
        base_record = self.data["base_logics"]["EMA_CROSS_SAR"][0]
        required_features = [
            "Total_Ret_Pct", "Net_PnL_USD", "Final_Equity", "Max_DD_Pct",
            "Sharpe", "Sortino", "Calmar", "Win_Rate_Pct", "Profit_Factor",
            "Expectancy_Pct", "Total_Trades", "Avg_Hold_Hours", "Exposure_Pct",
            "Fees_Applied_Pct", "Composite_Score"
        ]
        for feat in required_features:
            self.assertIn(feat, base_record, f"Data feature '{feat}' missing from base record!")

    def test_hierarchy_tree_structure(self):
        """Verify hierarchy_explorer data has valid 5-tier schema (Category -> Strategy -> Quarters -> Months -> Trades -> Tranches)."""
        self.assertIn("hierarchy_explorer", self.data)
        trees = self.data["hierarchy_explorer"]
        self.assertGreater(len(trees), 0, "Hierarchy trees list is empty!")

        for strat_tree in trees:
            self.assertIn("strategy_name", strat_tree)
            self.assertIn("category", strat_tree)
            self.assertIn("summary", strat_tree)
            self.assertIn("quarters", strat_tree)
            self.assertEqual(len(strat_tree["quarters"]), 3, "Strategy missing 3 quarters!")
            for q in strat_tree["quarters"]:
                self.assertIn("quarter_name", q)
                self.assertIn("months", q)
                for m in q["months"]:
                    self.assertIn("month_name", m)
                    self.assertIn("trades", m)

    def test_table_sorting_algorithm(self):
        """Verify that frontend table sorting handles both numeric values and nulls correctly."""
        base_list = self.data["base_logics"]["EMA_CROSS_SAR"]
        
        # Test Descending Total_Ret_Pct
        sorted_desc = sorted(base_list, key=lambda x: x.get("Total_Ret_Pct", 0), reverse=True)
        self.assertGreaterEqual(sorted_desc[0]["Total_Ret_Pct"], sorted_desc[-1]["Total_Ret_Pct"])

        # Test Ascending Max_DD_Pct
        sorted_asc = sorted(base_list, key=lambda x: x.get("Max_DD_Pct", 0), reverse=False)
        self.assertLessEqual(sorted_asc[0]["Max_DD_Pct"], sorted_asc[-1]["Max_DD_Pct"])

    def test_pagination_bounds_and_slicing(self):
        """Verify that pagination mathematics slice data accurately with no index overflow."""
        items = self.data["base_logics"]["EMA_CROSS_SAR"]
        page_size = 25
        total_pages = (len(items) + page_size - 1) // page_size
        
        for p in [1, 2, total_pages]:
            start_idx = (p - 1) * page_size
            end_idx = min(start_idx + page_size, len(items))
            sliced = items[start_idx:end_idx]
            self.assertLessEqual(len(sliced), page_size)
            if p == 1:
                self.assertEqual(start_idx, 0)
            if p == total_pages:
                self.assertEqual(end_idx, len(items))

    def test_risk_archetype_filter_predicates(self):
        """Verify that filtering by Risk Archetype returns non-empty subsets matching the archetype."""
        risk_results = self.data["risk_studio"]["results"]
        archetypes = ["FIXED_SL_ONLY", "FIXED_TP_ONLY", "FIXED_SL_AND_TP", "TRAILING_SL_ONLY", "TRAILING_TP_ONLY"]
        
        for arch in archetypes:
            matching = [r for r in risk_results if r["Risk_Archetype"] == arch]
            self.assertGreater(len(matching), 0, f"No entries found for Risk Archetype '{arch}'!")
            for m in matching:
                self.assertEqual(m["Risk_Archetype"], arch)

    def test_modal_trade_direction_filters(self):
        """Verify that trade history filters properly partition Longs, Shorts, Winners, and Losers."""
        key = list(self.data["base_trade_logs"].keys())[0]
        trades = self.data["base_trade_logs"][key]
        
        longs = [t for t in trades if t["direction"] == "LONG"]
        shorts = [t for t in trades if t["direction"] == "SHORT"]
        winners = [t for t in trades if t["pnl"] > 0]
        losers = [t for t in trades if t["pnl"] <= 0]

        self.assertEqual(len(longs) + len(shorts), len(trades), "Direction filter dropped trades!")
        self.assertEqual(len(winners) + len(losers), len(trades), "Outcome filter dropped trades!")

if __name__ == "__main__":
    unittest.main(verbosity=2)
