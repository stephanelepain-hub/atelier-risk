import copy
import hashlib
import json
import pathlib
import re
import tempfile
import unittest

from atelier_engine import calibration, export, quick, study

ROOT = pathlib.Path(__file__).resolve().parents[2]
CAL = calibration.load("anssi-v1.5")
EXAMPLE = ROOT / "examples" / "anssi-guide-vaccine-example.json"


def profile(**kw):
    p = {"name": "Test", "activity": {"value": "We sell books"}, "values": {"value": ["Orders", "Customer list"]},
         "tools": {"value": ["office", "shop"]}, "downtime": {"answer": "day"},
         "sensitivity": {"answer": "confidential"}, "document": {"provided": False}}
    p.update(kw)
    return p


def answers(prof=None, **kw):
    prof = prof or profile()
    q = {"lang": "en", "profile": prof, "risks": [{"id": i, "decision": "keep"} for i in quick.suggest(prof)]}
    q.update(kw)
    return q


class Catalogue(unittest.TestCase):
    def setUp(self):
        self.cat = quick.load_catalogue()

    def test_loads_and_is_in_range(self):
        self.assertTrue(25 <= len(self.cat["risks"]) <= 35, len(self.cat["risks"]))
        fams = {r["family"] for r in self.cat["risks"]}
        self.assertEqual(fams, {"deliberate", "accidental"})
        self.assertEqual({p["id"] for p in self.cat["packs"]},
                         {"all", "office-it", "cloud-service", "website-shop", "industrial"})

    def test_each_risk_has_the_required_fields(self):
        for r in self.cat["risks"]:
            for k in ("title", "description"):
                self.assertTrue(r[k]["en"] and r[k]["fr"], (r["id"], k))
            self.assertTrue(set(r["criteria"]) <= set(quick.CRITERIA) and r["criteria"], r["id"])
            self.assertIsInstance(r["always_assessed"], bool)
            self.assertTrue(3 <= len(r["measures"]) <= 6, r["id"])
            for m in r["measures"]:
                self.assertTrue(m["id"] and m["en"] and m["fr"])
            if r["family"] == "deliberate":
                self.assertIn(r["origin"], {o["id"] for o in self.cat["origins"]})
                self.assertIn(r["objective"], {o["id"] for o in self.cat["objectives"]})

    def test_every_pack_has_risks_and_some_always_assessed_exist(self):
        for p in ("office-it", "cloud-service", "website-shop", "industrial"):
            self.assertTrue([r for r in self.cat["risks"] if p in r["packs"]], p)
        self.assertTrue([r for r in self.cat["risks"] if r["always_assessed"]])
        fam_acc = [r for r in self.cat["risks"] if r["family"] == "accidental"]
        text = " ".join(r["title"]["en"].lower() for r in fam_acc)
        for word in ("mistake", "backup", "break", "lost", "stolen", "fire", "storm", "supplier", "network"):
            self.assertIn(word, text, word)

    def test_no_vendor_or_company_names(self):
        blob = json.dumps(self.cat, ensure_ascii=False).lower()
        for name in ("microsoft", "google", "amazon", "aws", "azure", "oracle", "sap ", "cisco", "apple", "meta ",
                     "facebook", "linkedin", "paypal", "stripe", "zoom", "dropbox", "office 365", "windows"):
            self.assertNotIn(name, blob, name)

    def test_check_refuses_a_broken_catalogue(self):
        bad = copy.deepcopy(self.cat)
        bad["risks"][0]["measures"] = bad["risks"][0]["measures"][:2]
        with self.assertRaises(quick.QuickError):
            quick.check_catalogue(bad)
        bad = copy.deepcopy(self.cat)
        bad["risks"][1]["id"] = bad["risks"][0]["id"]
        with self.assertRaises(quick.QuickError):
            quick.check_catalogue(bad)

    def test_load_from_another_path(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "c.json"
            f.write_text(json.dumps(self.cat), encoding="utf-8")
            self.assertEqual(quick.load_catalogue(f)["version"], self.cat["version"])
            f.write_text("{not json", encoding="utf-8")
            with self.assertRaises(quick.QuickError):
                quick.load_catalogue(f)


class Suggest(unittest.TestCase):
    def test_all_pack_and_always_assessed_first(self):
        cat = quick.load_catalogue()
        by = {r["id"]: r for r in cat["risks"]}
        ids = quick.suggest(profile(tools={"value": ["cloud"]}))
        flags = [by[i]["always_assessed"] for i in ids]
        self.assertEqual(flags, sorted(flags, reverse=True))   # all True before any False
        self.assertTrue(flags[0] and not flags[-1])
        for i in ids:
            self.assertTrue({"all", "cloud-service"} & set(by[i]["packs"]), i)
        self.assertEqual(len(ids), len(set(ids)))

    def test_packs_follow_the_tools(self):
        self.assertIn("website-shop", quick.packs_for(profile(tools={"value": ["shop"]})))
        self.assertIn("industrial", quick.packs_for(profile(tools={"value": ["industrial"]})))
        self.assertNotIn("industrial", quick.packs_for(profile(tools={"value": ["office"]})))
        ind = quick.suggest(profile(tools={"value": ["industrial"]}))
        self.assertIn("D14", ind)
        self.assertNotIn("D14", quick.suggest(profile(tools={"value": ["office"]})))

    def test_dont_know_or_skipped_tools_default_to_office_it(self):
        for tools in ({"dont_know": True, "value": []}, {}, {"value": []}):
            self.assertEqual(quick.packs_for(profile(tools=tools)), ["all", "office-it"])

    def test_accepts_a_whole_quick_answers_object(self):
        q = answers()
        self.assertEqual(quick.suggest(q), quick.suggest(q["profile"]))


class BuildStudy(unittest.TestCase):
    def test_valid_with_no_errors_and_one_row_per_kept_risk(self):
        q = answers()
        q["risks"][0]["extra"] = ["backup_offline", "mfa"]
        q["risks"][1]["decision"] = "discard"
        q["risks"][1]["reason"] = "not for us"
        q["risks"].append({"id": "C1", "decision": "keep", "custom": {"title": "Our key machine breaks", "family": "accidental",
                                                                    "criteria": ["availability"]}})
        st = quick.build_study(q, CAL)
        res = study.validate(st, CAL)
        self.assertEqual(res["errors"], [])
        rows = study.register(st, CAL)
        kept = [r["id"] for r in q["risks"] if r["decision"] == "keep"]
        self.assertEqual([r["id"] for r in rows], kept)
        self.assertEqual(len(rows), len(kept))
        for r in rows:
            self.assertIn(r["level"], {l["name"] for l in CAL["levels"]})
            self.assertIn(r["level_target"], {l["name"] for l in CAL["levels"]})
            self.assertTrue(1 <= r["severity"] <= 4 and 1 <= r["likelihood"] <= 4 and 1 <= r["likelihood_target"] <= 4)
            self.assertEqual(r["level"], calibration.level(CAL, r["severity"], r["likelihood"]))
            self.assertEqual(r["level_target"], calibration.level(CAL, r["severity"], r["likelihood_target"]))

    def test_before_and_after_differ_when_extra_measures_lower_the_likelihood(self):
        q = answers()
        q["risks"][0].update({"likelihood": {"answer": "very_likely"}, "extra": ["backup_offline", "updates", "mfa"]})
        st = quick.build_study(q, CAL)
        row = study.register(st, CAL)[0]
        self.assertEqual(row["likelihood"], 4)
        self.assertEqual(row["likelihood_target"], 2)
        self.assertLess(row["likelihood_target"], row["likelihood"])
        self.assertEqual(len(row["measures"]), 3)

    def test_no_extra_measure_means_no_change(self):
        row = study.register(quick.build_study(answers(), CAL), CAL)[0]
        self.assertEqual(row["likelihood"], row["likelihood_target"])
        self.assertEqual(row["level"], row["level_target"])

    def test_every_element_carries_a_source(self):
        q = answers()
        q["risks"][0]["extra"] = ["mfa"]
        q["risks"][0]["in_place"] = ["updates"]
        st = quick.build_study(q, CAL)
        for key in study.COLLECTIONS:
            for x in st[key]:
                self.assertIn(x.get("source"), quick.SOURCES, (key, x["id"]))
        for r in st["risks"]:
            self.assertIn(r["sources"]["severity"], quick.SOURCES)
            self.assertIn(r["sources"]["likelihood"], quick.SOURCES)

    def test_sources_say_what_happened(self):
        q = answers()
        q["risks"][0]["likelihood"] = {"answer": "likely"}
        q["risks"][1]["likelihood"] = {"answer": "dont_know"}
        q["risks"][2]["severity"] = {"value": 1, "reason": "we have a paper fallback"}
        st = quick.build_study(q, CAL)
        r = {x["id"]: x for x in st["risks"]}
        ids = [x["id"] for x in q["risks"]]
        self.assertEqual(r[ids[0]]["sources"], {"severity": "catalogue", "likelihood": "answer"})
        self.assertEqual(r[ids[1]]["sources"]["likelihood"], "default")
        self.assertEqual(r[ids[2]]["sources"]["severity"], "answer")
        self.assertEqual(r[ids[2]]["severity"], 1)
        self.assertEqual(r[ids[2]]["severity_reason"], "we have a paper fallback")
        self.assertIn("severity_proposed", r[ids[2]])

    def test_slot_source(self):
        self.assertEqual(quick.slot_source({"answer": "dont_know"}), "default")
        self.assertEqual(quick.slot_source({"value": "x"}), "answer")
        self.assertEqual(quick.slot_source({"value": "x", "dont_know": True}), "default")
        self.assertEqual(quick.slot_source({"value": "x", "source": "document"}), "document")
        self.assertEqual(quick.slot_source({}), "default")

    def test_unknown_profile_answers_give_default_sources(self):
        q = answers(profile(downtime={"dont_know": True}, sensitivity={}))
        st = quick.build_study(q, CAL)
        self.assertTrue(all(r["sources"]["severity"] == "default" for r in st["risks"]))
        self.assertEqual(study.validate(st, CAL)["errors"], [])

    def test_deliberate_and_accidental_mapping(self):
        st = quick.build_study(answers(), CAL)
        self.assertTrue(st["risk_origins"] and st["strategic_scenarios"] and st["operational_scenarios"])
        deliberate = [r for r in st["risks"] if r["id"].startswith("D")]
        accidental = [r for r in st["risks"] if r["id"].startswith("A")]
        self.assertEqual(len(st["strategic_scenarios"]), len(deliberate))
        self.assertTrue(accidental)
        self.assertTrue(all("strategic_scenario" not in r for r in accidental))
        os_ = {o["strategic_scenario"]: o for o in st["operational_scenarios"]}
        for r in deliberate:
            self.assertEqual(os_[r["strategic_scenario"]]["likelihood"], r["likelihood"])

    def test_severity_comes_from_the_engine_and_matches_the_scenario(self):
        st = quick.build_study(answers(), CAL)
        fe = {f["id"]: f for f in st["feared_events"]}
        for ss in st["strategic_scenarios"]:
            self.assertEqual(ss["severity"], max(fe[i]["severity"] for i in ss["feared_events"]))

    def test_measures_in_place_become_baseline_extra_become_measures(self):
        q = answers()
        q["risks"][0]["in_place"] = ["updates", "mfa"]
        q["risks"][0]["extra"] = ["mfa", "awareness"]   # mfa is already in place: not an extra
        st = quick.build_study(q, CAL)
        self.assertEqual({b["id"] for b in st["baseline"]}, {"BL-updates", "BL-mfa"})
        self.assertEqual({m["id"] for m in st["measures"]}, {"M-awareness"})
        self.assertTrue(all(b["status"] == "applied" for b in st["baseline"]))

    def test_a_measure_shared_by_two_risks_is_one_measure(self):
        q = answers()
        shared = [e for e in q["risks"] if e["id"] in ("D01", "D02")]
        for e in shared:
            e["extra"] = ["mfa"]
        st = quick.build_study(q, CAL)
        m = [x for x in st["measures"] if x["id"] == "M-mfa"]
        self.assertEqual(len(m), 1)
        self.assertEqual(sorted(m[0]["risks"]), ["D01", "D02"])

    def test_french_study_uses_french_labels(self):
        st = quick.build_study(answers(lang="fr"), CAL)
        self.assertEqual(st["risks"][0]["label"], "Un rançongiciel bloque vos fichiers et vos systèmes")
        self.assertEqual(study.validate(st, CAL)["errors"], [])

    def test_no_business_value_given_falls_back_to_a_default_one(self):
        st = quick.build_study(answers(profile(values={"dont_know": True, "value": []})), CAL)
        self.assertEqual(len(st["business_values"]), 1)
        self.assertEqual(st["business_values"][0]["source"], "default")
        self.assertEqual(study.validate(st, CAL)["errors"], [])

    def test_study_carries_the_quick_answers(self):
        q = answers()
        self.assertEqual(quick.build_study(q, CAL)["quick"], q)

    def test_works_with_the_calibration_in_a_synthetic_four_level_grid(self):
        cal = copy.deepcopy(CAL)
        cal["id"] = "synthetic"
        cal["levels"] = [{"name": n, "rank": i + 1, "colour": "CCCCCC"} for i, n in enumerate(("A", "B", "C", "D"))]
        cal["grid_by_severity"] = {"4": ["B", "C", "D", "D"], "3": ["A", "B", "C", "D"], "2": ["A", "A", "B", "C"], "1": ["A", "A", "A", "B"]}
        calibration.check(cal)
        st = quick.build_study(answers(), cal)
        self.assertEqual(study.validate(st, cal)["errors"], [])
        self.assertEqual(st["study"]["calibration"], "synthetic")

    def test_bad_answers_are_refused(self):
        for mutate in (lambda q: q["risks"][0].update(decision="maybe"),
                       lambda q: q["risks"][0].update(id="NOPE"),
                       lambda q: q["risks"][0].update(severity={"value": 5, "reason": "x"}),
                       lambda q: q["risks"][0].update(severity={"value": 1, "reason": ""}),
                       lambda q: q["risks"][0].update(likelihood={"answer": "never"}),  # D01 is deliberate
                       lambda q: q["risks"].append(dict(q["risks"][0])),
                       lambda q: q["risks"].append({"id": "C1", "decision": "keep", "custom": {"title": " "}}),
                       lambda q: q["profile"].update(downtime={"answer": "soon"})):
            q = answers()
            mutate(q)
            with self.assertRaises((quick.QuickError, calibration.CalibrationError)):
                quick.build_study(q, CAL)

    def test_always_assessed_needs_a_reason_to_discard(self):
        q = answers()
        q["risks"][0].update(decision="discard")   # first suggested risk is always assessed
        with self.assertRaises(quick.QuickError):
            quick.build_study(q, CAL)
        q["risks"][0]["reason"] = "we have no computers at all"
        self.assertEqual(study.validate(quick.build_study(q, CAL), CAL)["errors"], [])


class Levels(unittest.TestCase):
    def test_likelihood_after_rule(self):
        self.assertEqual([quick.likelihood_after(3, n) for n in (0, 1, 2, 3, 6)], [3, 2, 2, 1, 1])
        self.assertEqual(quick.likelihood_after(1, 5), 1)
        with self.assertRaises(calibration.CalibrationError):
            quick.likelihood_after(0, 1)

    def test_severity_is_proposed_from_the_answers_and_the_catalogue(self):
        cat = {r["id"]: r for r in quick.load_catalogue()["risks"]}
        ransomware = cat["D01"]           # typical severity 4, hits availability
        low = {"downtime": {"answer": "week"}, "sensitivity": {"answer": "public"}}
        high = {"downtime": {"answer": "hours"}, "sensitivity": {"answer": "critical"}}
        self.assertEqual(quick.propose_severity(ransomware, high), 4)
        self.assertEqual(quick.propose_severity(ransomware, low), 3)   # (4 + 1) / 2, half up
        small = cat["A15"]               # typical 2, availability only
        self.assertEqual(quick.propose_severity(small, high), 3)
        self.assertEqual(quick.propose_severity(small, low), 2)

    def test_likelihood_answers(self):
        self.assertEqual([quick.likelihood_from_answer("deliberate", a) for a in ("unlikely", "possible", "likely", "very_likely")], [1, 2, 3, 4])
        self.assertEqual([quick.likelihood_from_answer("accidental", a) for a in ("never", "once", "sometimes", "often")], [1, 2, 3, 4])
        self.assertIsNone(quick.likelihood_from_answer("accidental", "dont_know"))
        self.assertIsNone(quick.likelihood_from_answer("accidental", "likely"))


class Confidence(unittest.TestCase):
    def full(self):
        """Every answer given and every severity chosen by the person."""
        q = answers()
        for e in q["risks"]:
            e["assessed"] = True
            e["severity"] = {"value": 2, "reason": "our call"}
            fam = "deliberate" if e["id"].startswith("D") else "accidental"
            e["likelihood"] = {"answer": "possible" if fam == "deliberate" else "once"}
        return q

    def test_range_and_integer(self):
        for q in (self.full(), answers(), answers(risks=[])):
            c = quick.confidence(q)
            self.assertIsInstance(c, int)
            self.assertTrue(0 <= c <= 100)

    def test_no_kept_risk_is_zero(self):
        self.assertEqual(quick.confidence(answers(risks=[])), 0)

    def test_never_above_75_without_a_document(self):
        q = self.full()
        self.assertLessEqual(quick.confidence(q), 75)
        self.assertEqual(quick.confidence(q), 75)   # everything answered by the person: the ceiling itself

    def test_a_document_flag_alone_does_not_raise_it_above_what_the_sources_give(self):
        q = self.full()
        q["profile"]["document"] = {"provided": True, "kind": "architecture", "filename": "x.docx"}
        self.assertEqual(quick.confidence(q), 75)   # stored but not read: all inputs are still answers

    def test_defaults_and_dont_know_lower_it(self):
        base = self.full()
        c0 = quick.confidence(base)
        q = copy.deepcopy(base)
        q["risks"][0]["likelihood"] = {"answer": "dont_know"}
        c1 = quick.confidence(q)
        self.assertLess(c1, c0)
        q2 = copy.deepcopy(q)
        q2["risks"][1]["likelihood"] = {}
        self.assertLess(quick.confidence(q2), c1)
        q3 = copy.deepcopy(base)
        q3["profile"]["downtime"] = {"dont_know": True}
        q3["profile"]["sensitivity"] = {"dont_know": True}
        self.assertLess(quick.confidence(q3), c0)
        q4 = copy.deepcopy(base)
        q4["profile"]["activity"] = {"dont_know": True}
        self.assertLess(quick.confidence(q4), c0)

    def test_keeping_the_proposed_severity_weighs_less_than_choosing_one(self):
        chosen = self.full()
        kept = copy.deepcopy(chosen)
        for e in kept["risks"]:
            e.pop("severity")
        self.assertLess(quick.confidence(kept), quick.confidence(chosen))

    def test_a_document_source_would_weigh_most(self):
        self.assertGreater(quick.SOURCE_WEIGHT["document"], quick.SOURCE_WEIGHT["answer"])
        self.assertGreater(quick.SOURCE_WEIGHT["answer"], quick.SOURCE_WEIGHT["catalogue"])
        self.assertGreater(quick.SOURCE_WEIGHT["catalogue"], quick.SOURCE_WEIGHT["default"])

    def test_band(self):
        self.assertEqual([quick.confidence_band(x) for x in (0, 49, 50, 79, 80, 100)],
                         ["low", "low", "medium", "medium", "high", "high"])


class AssumptionsAndActions(unittest.TestCase):
    def test_assumptions_list_defaults_and_dont_know(self):
        q = answers(profile(downtime={"dont_know": True}))
        q["risks"][0]["likelihood"] = {"answer": "dont_know"}
        a = quick.assumptions(q, CAL)
        kinds = {x["kind"] for x in a}
        self.assertTrue({"dont_know", "default", "catalogue"} <= kinds)
        self.assertEqual(a[0]["scope"], "profile")          # About-you assumptions come first
        self.assertTrue(any(x["what"] == "likelihood" and x["kind"] == "dont_know" and x["risk"] == q["risks"][0]["id"] for x in a))
        for x in a:
            self.assertTrue(x["text"]["en"] and x["text"]["fr"])

    def test_risk_assumptions_ordered_by_level(self):
        q = answers()
        rows = quick.compute(q, CAL)
        a = [x for x in quick.assumptions(q, CAL) if x["scope"] == "risk"]
        rank = {r["id"]: (r["rank"], r["severity"]) for r in rows}
        first = [rank[x["risk"]] for x in a]
        self.assertEqual(first, sorted(first, reverse=True))

    def test_top_actions_are_at_most_five_ranked_and_only_extras(self):
        q = answers()
        for i, e in enumerate(q["risks"][:8]):
            e["extra"] = ["mfa", "backup_offline"] if i < 4 else ["awareness"]
        acts = quick.top_actions(q, CAL)
        self.assertTrue(1 <= len(acts) <= 5)
        self.assertEqual([a["priority"] for a in acts], sorted([a["priority"] for a in acts], reverse=True))
        ticked = {m for e in q["risks"] for m in e.get("extra", [])}
        self.assertTrue({a["id"] for a in acts} <= ticked)
        self.assertEqual(quick.top_actions(answers(), CAL), [])

    def test_top_actions_limit(self):
        q = answers()
        for e in q["risks"]:
            e["extra"] = ["mfa", "backup_offline", "updates", "awareness", "least_access", "monitoring"][:3]
        q["risks"][0]["extra"] = ["mfa", "awareness"]
        self.assertLessEqual(len(quick.top_actions(q, CAL, n=2)), 2)

    def test_facts(self):
        f = quick.facts(answers(), CAL)
        self.assertEqual(f["not_provided"], ["architecture", "business-impact", "security-baseline"])
        self.assertFalse(f["document_provided"])
        q = answers()
        q["profile"]["document"] = {"provided": True, "kind": "architecture"}
        f2 = quick.facts(q, CAL)
        self.assertEqual(f2["documents"], ["architecture"])
        self.assertEqual(f2["not_provided"], ["business-impact", "security-baseline"])


class Honesty(unittest.TestCase):
    def test_statement_constants(self):
        self.assertEqual(set(quick.HONESTY), {"en", "fr"})
        # the exact English text of the owner's brief, pinned by hash so that the text itself stays in one place
        self.assertEqual(hashlib.sha256(quick.HONESTY["en"].encode("utf-8")).hexdigest(),
                         "02f1e09c76e2938862de6d93b89bf8dca6c15c61df681c8c15a1f6f9283e52a0")
        self.assertIn("treat it as a first view.", quick.HONESTY["en"])
        self.assertTrue(quick.HONESTY["fr"].startswith("Cette analyse reflète uniquement"))
        self.assertIn("première vue", quick.HONESTY["fr"])

    def test_the_text_is_written_once_in_the_engine_package_and_app(self):
        needle = "reflects only the " + "answers you gave"
        hits = []
        for base in (ROOT / "engine", ROOT / "app"):
            for f in base.rglob("*.py"):
                if "tests" in f.parts:
                    continue
                if needle in f.read_text(encoding="utf-8"):
                    hits.append(f.name)
        self.assertEqual(hits, ["quick.py"])

    def test_xlsx_header_carries_the_statement(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed")
        q = answers()
        st = quick.build_study(q, CAL)
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "q.xlsx"
            export.to_xlsx(st, CAL, f, notice=quick.xlsx_notice(q, CAL), extra_sheets=quick.xlsx_sheets(q, CAL))
            wb = openpyxl.load_workbook(f)
            first = wb.worksheets[0]
            self.assertEqual(first["A1"].value, quick.HONESTY["en"])
            self.assertIn("Confidence:", first["A2"].value)
            header = [c.value for c in first[4]]
            self.assertEqual(header[:3], ["id", "label", "severity"])
            self.assertEqual(first["A5"].value, st["risks"][0]["id"])
            self.assertIn("Assumptions", wb.sheetnames)
            self.assertIn("Map now", wb.sheetnames)
            self.assertIn("Map target", wb.sheetnames)

    def test_plain_export_is_unchanged_without_a_notice(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed")
        ex = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "x.xlsx"
            export.to_xlsx(ex, CAL, f)
            ws = openpyxl.load_workbook(f).worksheets[0]
            self.assertEqual(ws["A1"].value, "id")


class WorkedExample(unittest.TestCase):
    def test_the_guide_example_still_validates_with_the_same_levels(self):
        ex = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(study.validate(ex, CAL)["errors"], [])
        got = [(r["id"], r["severity"], r["likelihood"], r["level"]) for r in study.register(ex, CAL)]
        # levels read off the guide's risk grid (p.75) for R1-R5 of its worked example, recorded before the quick path
        self.assertEqual(got, [("R1", 3, 3, "Élevé"), ("R2", 3, 2, "Moyen"), ("R3", 3, 4, "Élevé"),
                               ("R4", 4, 2, "Moyen"), ("R5", 4, 1, "Moyen")])


if __name__ == "__main__":
    unittest.main()
