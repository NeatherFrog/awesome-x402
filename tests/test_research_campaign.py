"""Progress is passive and counts actual rows without promoting a strategy."""
from copy import deepcopy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from propdesk import research_campaign as campaign
from propdesk.server import Application, make_handler


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def fixture(root, study="pairs", *, kind=None, configurations=3, evaluated=2):
    spec = campaign.STUDIES[study]
    kind = kind or spec["kind"]
    producers = {}
    for name in ("propdesk/" + spec["engine"] + ".py", "scripts/" + spec["driver"] + ".py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("frozen")
        producers[name] = hashlib.sha256(b"frozen").hexdigest()
    source = root / "data" / "quotes.json"
    write(source, {"bars": [{"time": "2024-01-01T00:00:00Z", "close": 100}]})
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    objective = root / "docs" / "EIGHT_PERCENT_PROTOCOL.json"
    write(objective, {"target": 8})
    objective_hash = hashlib.sha256(objective.read_bytes()).hexdigest()
    names = ["a", "b", "c"] if configurations == 3 else [f"v{number:03d}" for number in range(configurations)]
    variants = [{"id": name} for name in names]
    evaluation = {"passed": False, "base": {"total_return": -.01}}
    directory = root / "data" / spec["directory"]
    protocol = {"grid": variants, "producers": producers, "inputs": {"data/quotes.json": source_hash},
                "common_objective_path": "docs/EIGHT_PERCENT_PROTOCOL.json", "common_objective_sha256": objective_hash}
    rows = [{"id": name, "target": deepcopy(evaluation), "passed": False} for name in names[:evaluated]]
    if kind == "sessions":
        protocol = {"variants": variants, "common_target_protocol": {"path": "docs/EIGHT_PERCENT_PROTOCOL.json", "file_sha256": objective_hash}}
        value = {"phase": "complete", "protocol": protocol, "protocol_sha256": campaign.digest(protocol, ascii=False),
                 "producer_sha256": producers, "source_lock": {"MES=F": {"path": "data/quotes.json", "file_sha256": source_hash,
                    "canonical_bars_sha256": campaign.digest(json.loads(source.read_text())["bars"], ascii=False)}},
                 "variants": [{"id": name, "training": deepcopy(evaluation)} for name in names[:evaluated]]}
        lock = {"protocol_sha256": value["protocol_sha256"], "producer_sha256": producers,
                "source_lock_sha256": campaign.digest(value["source_lock"], ascii=False),
                "training_metrics": {item["id"]: item["training"] for item in value["variants"]}}
        value["training_lock_sha256"] = campaign.digest(lock, ascii=False)
        write(directory / "training-lock.json", lock)
        write(directory / "source-lock.json", value["source_lock"])
    elif kind == "fx":
        protocol["variants"] = protocol.pop("grid")
        protocol["inputs"] = {"EURUSD": {"file": "data/quotes.json", "sha256": source_hash}}
        rows = [{**deepcopy(evaluation), "variant": {"id": name}} for name in names[:evaluated]]
        value = {"phase": "completed_training_failed", "protocol": protocol,
                 "protocol_sha256": campaign.digest(protocol), "training": rows,
                 "selection": {"variant": None, "training_sha256": campaign.digest(rows)}}
        write(directory / "selection.json", value["selection"])
        write(directory / "input-lock.json", protocol["inputs"])
    else:
        value = {"phase": "completed_no_training_candidate", "protocol": protocol,
                 "protocol_sha256": campaign.digest(protocol), "training": rows}
        lock = {"protocol_sha256": value["protocol_sha256"], "training_results_sha256": campaign.digest(rows), "selected": None}
        value[spec.get("selection_field", "selection_lock")] = lock
        value[spec.get("selection_digest_field", "selection_lock_sha256")] = campaign.digest(lock)
        filename = spec.get("selection_file", "training_selection.json" if study in ("pairs", "pairs_close", "native_trend", "native_mark") else "training-selection.json")
        write(directory / filename, lock)
    write(directory / "protocol.json", protocol)
    path = root / "docs" / spec["file"]
    write(path, value)
    if kind == "sessions":
        write(directory / "result-lock.json", {"report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "protocol_sha256": value["protocol_sha256"], "producer_sha256": producers,
              "training_lock_sha256": value["training_lock_sha256"]})
    return value, path, directory


class ResearchCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_cross_fixed_objective_path_still_requires_the_frozen_target_hash(self):
        value, path, directory = fixture(self.root, "cross_sectional")
        value["protocol"].pop("common_objective_path")
        value["protocol_sha256"] = campaign.digest(value["protocol"])
        value["selection_lock"]["protocol_sha256"] = value["protocol_sha256"]
        value["selection_lock_sha256"] = campaign.digest(value["selection_lock"])
        write(directory / "protocol.json", value["protocol"])
        write(directory / "training-selection.json", value["selection_lock"])
        write(path, value)
        self.assertTrue(campaign.inspect(self.root, "cross_sectional", value)["protocol_verified"])
        write(self.root / "docs/EIGHT_PERCENT_PROTOCOL.json", {"target": 999})
        checked = campaign.inspect(self.root, "cross_sectional", value)
        self.assertFalse(checked["protocol_verified"])
        self.assertFalse(checked["replay_artifacts_verified"])
        self.assertIn("Общий протокол цели не подтверждён", checked["verification_reasons"])

    def test_missing_reports_keep_prior_count_without_fake_new_experiments(self):
        board = campaign.board(self.root)
        self.assertEqual(board["reported_evaluated_configurations"], 292)
        self.assertEqual(board["new_reported_evaluated_configurations"], 0)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 0)
        self.assertTrue(board["crypto_pending_reports"])
        self.assertFalse(board["live_orders"])
        self.assertFalse(board["telegram_enabled"])
        self.assertIsNone(board["primary"])
        self.assertIn("does not rerun simulations", board["verification_scope"])

    def test_actual_two_evaluated_rows_not_three_registered_or48_expected(self):
        fixture(self.root)
        board = campaign.board(self.root)
        row = board["studies"][0]
        self.assertEqual(row["registered_configurations"], 3)
        self.assertEqual(row["reported_evaluated_configurations"], 2)
        self.assertEqual(board["reported_evaluated_configurations"], 294)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 2)
        self.assertTrue(row["replay_artifacts_verified"])

    def test_missing_inputs_preserve_reported_count_but_not_replay_proof(self):
        fixture(self.root)
        (self.root / "data" / "quotes.json").unlink()
        board = campaign.board(self.root)
        row = board["studies"][0]
        self.assertEqual(board["new_reported_evaluated_configurations"], 2)
        self.assertTrue(row["protocol_verified"])
        self.assertTrue(row["producer_hashes_verified"])
        self.assertFalse(row["input_available"])
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 0)

    def test_changed_source_hash_is_unverified_and_does_not_create_candidate(self):
        value, path, _ = fixture(self.root)
        value.update(live_orders=True, telegram_enabled=True, retrospective_target_candidate=True,
                     selected="a", historical_reference_passed=True)
        write(path, value)
        (self.root / "data" / "quotes.json").write_text("changed")
        row = campaign.board(self.root)["studies"][0]
        self.assertTrue(row["input_available"])
        self.assertFalse(row["input_hashes_verified"])
        self.assertFalse(row["eligible_for_paper"])
        self.assertFalse(row["live_orders"])
        self.assertFalse(row["telegram_enabled"])
        response = campaign.report(self.root, "pairs")
        self.assertFalse(response["live_orders"])
        self.assertFalse(response["telegram_enabled"])

    def test_changed_producer_and_protocol_are_separate_checks(self):
        value, path, _ = fixture(self.root)
        (self.root / "propdesk" / "relative_value.py").write_text("changed")
        row = campaign.board(self.root)["studies"][0]
        self.assertTrue(row["protocol_verified"])
        self.assertFalse(row["producer_hashes_verified"])
        value["protocol"]["inputs"]["data/quotes.json"] = "0" * 64
        write(path, value)
        self.assertFalse(campaign.board(self.root)["studies"][0]["protocol_verified"])

    def test_source_traversal_absolute_windows_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            sentinel = Path(outside) / "private"
            sentinel.write_text("not project data")
            for name in ("../private", str(sentinel), "C:\\private", "data/../../private"):
                value, path, directory = fixture(self.root)
                value["protocol"]["inputs"] = {name: hashlib.sha256(sentinel.read_bytes()).hexdigest()}
                value["protocol_sha256"] = campaign.digest(value["protocol"])
                write(directory / "protocol.json", value["protocol"])
                write(path, value)
                self.assertFalse(campaign.board(self.root)["studies"][0]["replay_artifacts_verified"])
            link = self.root / "data" / "outside-link"
            try:
                link.symlink_to(sentinel)
            except (OSError, NotImplementedError):
                return  # Windows runners may not grant symlink creation.
            value, path, directory = fixture(self.root)
            value["protocol"]["inputs"] = {"data/outside-link": hashlib.sha256(sentinel.read_bytes()).hexdigest()}
            value["protocol_sha256"] = campaign.digest(value["protocol"])
            write(directory / "protocol.json", value["protocol"])
            write(path, value)
            self.assertFalse(campaign.board(self.root)["studies"][0]["replay_artifacts_verified"])

    def test_protocol_only_registration_does_not_count_unseen_training(self):
        value, path, _ = fixture(self.root)
        value.pop("training")
        value["phase"] = "frozen_before_outcomes"
        write(path, value)
        self.assertEqual(campaign.board(self.root)["new_reported_evaluated_configurations"], 0)

    def test_crypto_partial_training_counts_only_rows_and_waits_for_lock(self):
        value, path, directory = fixture(self.root, "native_fvg")
        (directory / "training-selection.json").unlink()
        value.pop("selection_lock")
        value.pop("selection_lock_sha256")
        value["phase"] = "training_in_progress"
        write(path, value)
        board = campaign.board(self.root)
        row = next(item for item in board["studies"] if item["id"] == "native_fvg")
        self.assertEqual(row["expected_configurations"], 192)
        self.assertEqual(row["reported_evaluated_configurations"], 2)
        self.assertTrue(row["protocol_verified"])
        self.assertTrue(row["producer_hashes_verified"])
        self.assertFalse(row["replay_artifacts_verified"])
        self.assertTrue(board["crypto_pending_reports"])

    def test_completed_context48_has_verified_artifacts_and_never_promotes(self):
        value, path, _ = fixture(self.root, "native_context", configurations=48, evaluated=48)
        value.update(selected="v000", live_orders=True, telegram_enabled=True,
                     live_qualified=True, prop_qualified=True, retrospective_target_candidate=True)
        write(path, value)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        board = campaign.board(self.root)
        row = next(item for item in board["studies"] if item["id"] == "native_context")
        self.assertEqual(board["reported_evaluated_configurations"], 340)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 48)
        self.assertEqual(row["reported_evaluated_configurations"], 48)
        self.assertEqual(row["registered_configurations"], 48)
        self.assertTrue(row["replay_artifacts_verified"])
        response = campaign.report(self.root, "native_context")
        self.assertEqual(response["study"], "native_context")
        for subject in (board, row, response):
            for flag in ("eligible_for_paper", "live_orders", "telegram_enabled"):
                self.assertIs(subject[flag], False)
        self.assertIsNone(board["primary"])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_context_inherited_parent_hash_and_training_lock_are_checked(self):
        value, path, directory = fixture(self.root, "native_context", configurations=48, evaluated=48)
        parent = self.root / "propdesk/liquidity_native.py"
        parent.write_text("unchanged parent")
        value["protocol"]["producers"]["propdesk/liquidity_native.py"] = hashlib.sha256(parent.read_bytes()).hexdigest()
        value["protocol_sha256"] = campaign.digest(value["protocol"])
        value["selection_lock"]["protocol_sha256"] = value["protocol_sha256"]
        value["selection_lock_sha256"] = campaign.digest(value["selection_lock"])
        write(directory / "protocol.json", value["protocol"])
        write(directory / "training-selection.json", value["selection_lock"])
        write(path, value)
        self.assertTrue(campaign.inspect(self.root, "native_context", value)["replay_artifacts_verified"])
        parent.write_text("altered parent")
        row = campaign.inspect(self.root, "native_context", value)
        self.assertTrue(row["protocol_verified"])
        self.assertFalse(row["producer_hashes_verified"])
        self.assertFalse(row["replay_artifacts_verified"])
        value["training"][0]["target"]["base"]["total_return"] = 3
        self.assertFalse(campaign.inspect(self.root, "native_context", value)["training_results_verified"])

    def test_metal_and_flow_budgets_are_pending_and_registration_is_not_completion(self):
        board = campaign.board(self.root)
        for name, count in (("metals", 96), ("crypto_flow", 64)):
            with self.subTest(study=name):
                row = next(item for item in board["studies"] if item["id"] == name)
                self.assertEqual(row["expected_configurations"], count)
                self.assertEqual(row["reported_evaluated_configurations"], 0)
                self.assertEqual(row["status"], "missing_report")
                value, path, _ = fixture(self.root, name, configurations=count, evaluated=0)
                value["phase"] = "frozen_before_outcomes"
                write(path, value)
                row = campaign.inspect(self.root, name, value)
                self.assertEqual(row["registered_configurations"], count)
                self.assertEqual(row["reported_evaluated_configurations"], 0)
                self.assertFalse(row["live_orders"])
                self.assertFalse(row["telegram_enabled"])
        self.assertEqual(campaign.board(self.root)["reported_evaluated_configurations"], 292)

    def test_named_metal_rows_and_flow_hyphenated_selection_count_actual_results(self):
        fixture(self.root, "metals", configurations=96, evaluated=2)
        fixture(self.root, "crypto_flow", configurations=64, evaluated=3)
        board = campaign.board(self.root)
        for name, count in (("metals", 2), ("crypto_flow", 3)):
            with self.subTest(study=name):
                row = next(item for item in board["studies"] if item["id"] == name)
                self.assertEqual(row["reported_evaluated_configurations"], count)
                self.assertTrue(row["replay_artifacts_verified"])
        self.assertEqual(board["new_reported_evaluated_configurations"], 5)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 5)

    def test_completed_native_trend96_uses_its_existing_underscore_selection_lock(self):
        fixture(self.root, "native_trend", configurations=96, evaluated=96)
        board = campaign.board(self.root)
        row = next(item for item in board["studies"] if item["id"] == "native_trend")
        self.assertEqual(row["reported_evaluated_configurations"], 96)
        self.assertTrue(row["replay_artifacts_verified"])
        self.assertEqual(board["reported_evaluated_configurations"], 388)

    def test_partial_mark96_counts_actual_rows_and_waits_for_immutable_selection(self):
        value, path, directory = fixture(self.root, "native_mark", configurations=96, evaluated=42)
        (directory / "training_selection.json").unlink()
        value.pop("selection_lock")
        value.pop("selection_lock_sha256")
        value["phase"] = "training_in_progress"
        write(path, value)
        board = campaign.board(self.root)
        row = next(item for item in board["studies"] if item["id"] == "native_mark")
        self.assertEqual(board["reported_evaluated_configurations"], 334)
        self.assertEqual(row["expected_configurations"], 96)
        self.assertEqual(row["registered_configurations"], 96)
        self.assertEqual(row["reported_evaluated_configurations"], 42)
        self.assertTrue(row["protocol_verified"])
        self.assertTrue(row["producer_hashes_verified"])
        self.assertFalse(row["training_results_verified"])
        self.assertFalse(row["replay_artifacts_verified"])
        self.assertIn("повторных", row["interpretation"])
        self.assertTrue(board["crypto_pending_reports"])
        self.assertEqual(board["phase"], "research_in_progress")
        for flag in ("eligible_for_paper", "live_orders", "telegram_enabled"):
            self.assertIs(row[flag], False)

    def test_complete_mark96_uses_actual_underscore_selection_lock(self):
        value, _path, _directory = fixture(self.root, "native_mark", configurations=96, evaluated=96)
        row = campaign.inspect(self.root, "native_mark", value)
        self.assertEqual(row["reported_evaluated_configurations"], 96)
        self.assertTrue(row["training_results_verified"])
        self.assertTrue(row["replay_artifacts_verified"])
        self.assertFalse(row["eligible_for_paper"])

    def test_mark_v2_noise_cross_pending_budgets_contribute_zero(self):
        board = campaign.board(self.root)
        for name, count in (("native_mark_v2", 96), ("native_noise", 24), ("cross_sectional", 72)):
            row = next(item for item in board["studies"] if item["id"] == name)
            self.assertEqual(row["expected_configurations"], count)
            self.assertEqual(row["reported_evaluated_configurations"], 0)
            self.assertEqual(row["registered_configurations"], 0)
        self.assertEqual(board["reported_evaluated_configurations"], 292)
        self.assertTrue(board["crypto_pending_reports"])

    def test_noise_selection_envelope_and_v2_underscore_lock_are_supported(self):
        for name, count in (("native_mark_v2", 96), ("native_noise", 24), ("cross_sectional", 72)):
            with self.subTest(study=name):
                value, _path, directory = fixture(self.root, name, configurations=count, evaluated=2)
                row = campaign.inspect(self.root, name, value)
                self.assertEqual(row["reported_evaluated_configurations"], 2)
                self.assertTrue(row["training_results_verified"])
                self.assertTrue(row["replay_artifacts_verified"])
                self.assertFalse(row["eligible_for_paper"])
                if name == "native_noise":
                    self.assertIn("selection", value)
                    self.assertIn("selection_sha256", value)
                    self.assertTrue((directory / "selection.json").is_file())
                    write(directory / "selection.json", {"changed": True})
                    self.assertFalse(campaign.inspect(self.root, name, value)["training_results_verified"])

    def test_known_causality_revocation_is_separate_from_sha_artifact_consistency(self):
        value, path, directory = fixture(self.root, "native_mark")
        value.update(live_orders=True, telegram_enabled=True, promotion_blocked=False,
                     execution_causality_status="verified", retrospective_target_candidate=True)
        write(path, value)
        with patch.dict(campaign.STUDIES["native_mark"], {"blocked_protocol_sha256": value["protocol_sha256"]}):
            row = campaign.inspect(self.root, "native_mark", value)
            self.assertTrue(row["replay_artifacts_verified"])
            self.assertEqual(row["reported_evaluated_configurations"], 2)
            self.assertEqual(row["status"], "verified_artifacts_execution_blocked")
            self.assertEqual(row["execution_causality_status"], "revoked_after_synthetic_audit")
            self.assertTrue(row["promotion_blocked"])
            self.assertFalse(row["causality_audit_receipt_verified"])
            self.assertIn("BTC", row["interpretation"])
            self.assertIn("ETH", row["interpretation"])
            for flag in ("eligible_for_paper", "live_orders", "telegram_enabled"):
                self.assertIs(row[flag], False)
            # Missing or malformed optional audit bytes cannot erase observed
            # evaluations or undo the fixed known protocol's causal block.
            (directory / "retrospective-causality-audit.json").write_text("invalid")
            row = next(item for item in campaign.board(self.root)["studies"] if item["id"] == "native_mark")
            self.assertEqual(row["reported_evaluated_configurations"], 2)
            self.assertTrue(row["promotion_blocked"])
        other = campaign.inspect(self.root, "native_mark", value)
        self.assertFalse(other["promotion_blocked"])

    def test_sealed_causally_blocked_study_does_not_remain_an_active_search(self):
        value, path, _directory = fixture(self.root, "native_mark", configurations=96, evaluated=96)
        value["phase"] = "training_complete_primary_locked_oos_unopened"
        write(path, value)
        spec = {**campaign.STUDIES["native_mark"], "blocked_protocol_sha256": value["protocol_sha256"]}
        with patch.dict(campaign.STUDIES, {"native_mark": spec}, clear=True):
            board = campaign.board(self.root)
        self.assertEqual(board["reported_evaluated_configurations"], 388)
        self.assertFalse(board["crypto_pending_reports"])
        self.assertEqual(board["phase"], "reports_available")
        self.assertTrue(board["studies"][0]["promotion_blocked"])

    def test_all_nine_completed_catalogues_count1100_without_signal_permissions(self):
        original = ("pairs", "pairs_close", "sessions", "fx", "native_fvg", "native_trend", "native_context", "metals", "crypto_flow")
        for name in original:
            spec = campaign.STUDIES[name]
            fixture(self.root, name, configurations=spec["count"], evaluated=spec["count"])
        board = campaign.board(self.root)
        self.assertGreaterEqual(len(board["studies"]), 10)
        self.assertEqual(board["reported_evaluated_configurations"], 1100)
        self.assertEqual(board["new_reported_evaluated_configurations"], 808)
        self.assertEqual(board["new_protocol_producer_verified_configurations"], 808)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 808)
        self.assertTrue(board["crypto_pending_reports"])
        self.assertEqual(board["phase"], "research_in_progress")
        self.assertIsNone(board["primary"])
        for subject in [board, *board["studies"]]:
            for flag in ("eligible_for_paper", "live_orders", "telegram_enabled"):
                self.assertIs(subject[flag], False)
        # Expected catalogue size never stands in for an absent completed report.
        (self.root / "docs" / campaign.STUDIES["crypto_flow"]["file"]).unlink()
        self.assertEqual(campaign.board(self.root)["reported_evaluated_configurations"], 1036)

    def test_portable_public_receipts_verify_versions_without_substituting_raw_history(self):
        for name in ("native_context", "sessions", "metals"):
            spec = campaign.STUDIES[name]
            fixture(self.root, name, configurations=spec["count"], evaluated=spec["count"])
            original = self.root / "data" / spec["directory"]
            portable = self.root / "docs/research-receipts" / spec["directory"]
            portable.parent.mkdir(parents=True, exist_ok=True)
            original.rename(portable)
        raw = self.root / "data/quotes.json"
        # Even a copied raw history under the receipt directory cannot be used.
        copied = self.root / "docs/research-receipts/data/quotes.json"
        copied.parent.mkdir(parents=True)
        shutil.copyfile(raw, copied)
        raw.unlink()
        board = campaign.board(self.root)
        self.assertEqual(board["new_reported_evaluated_configurations"], 288)
        self.assertEqual(board["new_protocol_producer_verified_configurations"], 288)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 0)
        for row in board["studies"]:
            if row["id"] in ("native_context", "sessions", "metals"):
                self.assertTrue(row["protocol_verified"])
                self.assertTrue(row["producer_hashes_verified"])
                self.assertTrue(row["training_results_verified"])
                self.assertFalse(row["input_available"])
                self.assertFalse(row["replay_artifacts_verified"])

    def test_existing_poisoned_original_receipt_never_falls_back_to_portable_copy(self):
        value, _path, directory = fixture(self.root, "native_context", configurations=48, evaluated=48)
        portable = self.root / "docs/research-receipts" / campaign.STUDIES["native_context"]["directory"]
        shutil.copytree(directory, portable)
        for poison in ({"different": "protocol"}, "{invalid JSON"):
            with self.subTest(poison=poison):
                if isinstance(poison, dict):
                    write(directory / "protocol.json", poison)
                    row = campaign.inspect(self.root, "native_context", value)
                    self.assertFalse(row["protocol_verified"])
                    self.assertFalse(row["replay_artifacts_verified"])
                else:
                    (directory / "protocol.json").write_text(poison)
                    with self.assertRaises(ValueError):
                        campaign.inspect(self.root, "native_context", value)

    def test_tampered_portable_selection_receipt_does_not_verify(self):
        value, _path, directory = fixture(self.root, "native_context", configurations=48, evaluated=48)
        portable = self.root / "docs/research-receipts" / campaign.STUDIES["native_context"]["directory"]
        portable.parent.mkdir(parents=True)
        directory.rename(portable)
        self.assertTrue(campaign.inspect(self.root, "native_context", value)["replay_artifacts_verified"])
        lock = json.loads((portable / "training-selection.json").read_text())
        lock["training_results_sha256"] = "0" * 64
        write(portable / "training-selection.json", lock)
        row = campaign.inspect(self.root, "native_context", value)
        self.assertFalse(row["training_results_verified"])
        self.assertFalse(row["replay_artifacts_verified"])

    def test_outside_symlink_for_public_receipts_is_rejected(self):
        value, _path, directory = fixture(self.root, "native_context")
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside) / "receipt.json"
            shutil.copyfile(directory / "protocol.json", outside_path)
            (directory / "protocol.json").unlink()
            portable = self.root / "docs/research-receipts" / campaign.STUDIES["native_context"]["directory"]
            portable.mkdir(parents=True)
            try:
                (portable / "protocol.json").symlink_to(outside_path)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(ValueError):
                campaign.inspect(self.root, "native_context", value)

    def test_duplicate_unknown_and_unevaluated_rows_never_add_configurations(self):
        value, path, _ = fixture(self.root)
        value["training"] += [deepcopy(value["training"][0]), {"id": "unknown", "target": {"passed": False, "base": {"total_return": 0}}}, {"id": "c"}]
        write(path, value)
        board = campaign.board(self.root)
        self.assertEqual(board["new_reported_evaluated_configurations"], 2)
        self.assertEqual(board["new_replay_artifacts_verified_configurations"], 0)

    def test_forged_training_results_without_lock_fail(self):
        value, path, _ = fixture(self.root)
        value["training"][0]["target"]["base"]["total_return"] = 10
        write(path, value)
        row = campaign.board(self.root)["studies"][0]
        self.assertFalse(row["training_results_verified"])
        self.assertFalse(row["replay_artifacts_verified"])

    def test_session_special_producer_and_canonical_source_lock(self):
        _, _, _ = fixture(self.root, "sessions")
        board = campaign.board(self.root)
        row = next(item for item in board["studies"] if item["id"] == "sessions")
        self.assertTrue(row["replay_artifacts_verified"])
        self.assertEqual(row["reported_evaluated_configurations"], 2)
        value = campaign.read_report(self.root, "sessions")
        value["source_lock"]["MES=F"]["canonical_bars_sha256"] = "0" * 64
        row = campaign.inspect(self.root, "sessions", value)
        self.assertFalse(row["input_hashes_verified"])
        self.assertFalse(row["replay_artifacts_verified"])

    def test_session_result_file_lock_detects_modified_report(self):
        value, path, _ = fixture(self.root, "sessions")
        value["live_orders"] = True
        write(path, value)
        row = campaign.inspect(self.root, "sessions", value)
        self.assertFalse(row["training_results_verified"])
        self.assertFalse(row["replay_artifacts_verified"])

    def test_fx_named_inputs_and_selection_hash_supported(self):
        fixture(self.root, "fx")
        row = next(item for item in campaign.board(self.root)["studies"] if item["id"] == "fx")
        self.assertTrue(row["replay_artifacts_verified"])
        self.assertEqual(row["reported_evaluated_configurations"], 2)

    def test_unknown_report_path_and_nonfinite_content_fail_closed(self):
        for study in ("../private", "/etc/passwd", "pairs?path=secret", "", "native"):
            with self.assertRaises(ValueError):
                campaign.report(self.root, study)
        value, path, _ = fixture(self.root)
        path.write_text('{"protocol": {"bad": NaN}}')
        self.assertEqual(campaign.board(self.root)["new_replay_artifacts_verified_configurations"], 0)
        with self.assertRaises(ValueError):
            campaign.report(self.root, "pairs")

    def test_get_endpoint_and_allowlisted_report_are_read_only(self):
        fixture(self.root)
        fixture(self.root, "native_context", configurations=48, evaluated=48)
        app = Application(str(self.root / "runtime"))
        app.trader.root = self.root
        handler = make_handler(app)
        handler.log_message = lambda *_args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        def request(method, url):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(method, url, body=b"{}" if method == "POST" else None,
                                   headers={"Content-Type": "application/json"} if method == "POST" else {})
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()
        try:
            status, board = request("GET", "/api/trader/research-progress")
            self.assertEqual(status, 200)
            self.assertEqual(board["reported_evaluated_configurations"], 342)
            self.assertFalse(board["live_orders"])
            self.assertFalse(board["telegram_enabled"])
            status, result = request("GET", "/api/trader/research-progress?study=pairs")
            self.assertEqual(status, 200)
            self.assertEqual(result["study"], "pairs")
            self.assertFalse(result["eligible_for_paper"])
            status, result = request("GET", "/api/trader/research-progress?study=native_context")
            self.assertEqual(status, 200)
            self.assertEqual(result["study"], "native_context")
            self.assertEqual(result["verification"]["reported_evaluated_configurations"], 48)
            self.assertTrue(result["verification"]["replay_artifacts_verified"])
            self.assertFalse(result["live_orders"])
            self.assertFalse(result["telegram_enabled"])
            self.assertFalse(result["eligible_for_paper"])
            self.assertEqual(request("GET", "/api/trader/research-progress?study=native_fvg")[0], 404)
            for query in ("study=..%2Fprivate", "study=pairs&study=sessions", "path=private", "study=pairs&path=private", "study="):
                self.assertEqual(request("GET", "/api/trader/research-progress?" + query)[0], 400)
            self.assertNotEqual(request("POST", "/api/trader/research-progress")[0], 200)
            self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    @unittest.skipUnless(shutil.which("node"), "Optional Node runtime is unavailable")
    def test_browser_card_escapes_reports_and_ignores_supplied_urls(self):
        source = Path(__file__).resolve().parents[1] / "static" / "app.js"
        program = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const block=source.slice(source.indexOf('let researchProgressLoading='),source.indexOf('async function loadTraderBoard'));
const prior=source.slice(source.indexOf('function strategyReportUrl'),source.indexOf('function renderStrategyEvidence'));
const esc=source.split('\n').find(line=>line.startsWith('const esc ='));
const num=source.split('\n').find(line=>line.startsWith('const num ='));
const elements={};
const context={Number,String,Date,URL,encodeURIComponent,window:{location:{origin:'http://127.0.0.1:8765'}},
state:{researchProgress:{target_monthly_return_pct:8,reported_evaluated_configurations:604,
previous_evaluated_configurations:292,new_reported_evaluated_configurations:312,new_replay_artifacts_verified_configurations:0,
crypto_pending_reports:true,studies:[{id:'pairs',title:'<img src=x onerror=alert(1)>',reported_evaluated_configurations:48,
status:'unverified_artifacts',report_url:'javascript:alert(2)'},
{id:'native_context',title:'Context',reported_evaluated_configurations:48,status:'verified_artifacts',replay_artifacts_verified:true,report_url:'https://attacker.invalid'},
{id:'metals',title:'Gold',reported_evaluated_configurations:0,status:'missing_report'},
{id:'crypto_flow',title:'Flow',reported_evaluated_configurations:0,status:'missing_report'},
{id:'https://attacker.invalid',title:'evil'}]},researchProgressError:''},
$:selector=>elements[selector]||(elements[selector]={hidden:true,textContent:'',innerHTML:''}),
api:()=>{throw new Error('Rendering must not start a request');}};
vm.createContext(context);vm.runInContext(esc+'\n'+num+'\n'+prior+'\n'+block,context);
assert.strictEqual(vm.runInContext("strategyReportUrl('/api/trader/evidence?study=funding_calibrated')",context),'/api/trader/evidence?study=funding_calibrated');
assert.strictEqual(vm.runInContext("strategyReportUrl('/api/trader/evidence?study=funding_calibrated&path=private')",context),null);
vm.runInContext('renderResearchProgress()',context);
const html=elements['#research-progress-reports'].innerHTML;
assert(html.includes('&lt;img'));
assert(!html.includes('<img'));
assert(!html.includes('javascript:'));
assert(!html.includes('attacker.invalid'));
assert(html.includes('/api/trader/research-progress?study=pairs'));
assert(html.includes('/api/trader/research-progress?study=native_context'));
assert(!html.includes('/api/trader/research-progress?study=metals'));
assert(!html.includes('/api/trader/research-progress?study=crypto_flow'));
assert.strictEqual(vm.runInContext("researchProgressReportUrl('native_trend')",context),'/api/trader/research-progress?study=native_trend');
assert.strictEqual(vm.runInContext("researchProgressReportUrl('native_context&path=private')",context),null);
assert(elements['#research-progress-summary'].textContent.includes('604'));
assert(elements['#research-progress-summary'].textContent.includes('8%'));
assert(elements['#research-progress-summary'].textContent.includes('Сигналы по этим результатам не включены'));
assert.strictEqual(elements['#research-progress-details'].hidden,false);
context.state.researchProgressError='<script>failure</script>';
vm.runInContext('renderResearchProgress()',context);
assert.strictEqual(elements['#research-progress-details'].hidden,true);
assert(!elements['#research-progress-summary'].textContent.includes('<script>'));
"""
        subprocess.run([shutil.which("node"), "-e", program, str(source)], check=True, capture_output=True, text=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
