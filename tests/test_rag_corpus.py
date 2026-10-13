"""Boundary and reproducibility checks for knowledge used during investigation."""
import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_rag_corpus", ROOT / "kg/build_rag_corpus.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RagCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = module.build_corpus()

    def test_reproducible_committed_corpus(self):
        self.assertEqual(module.serialize(self.corpus), (ROOT / "kg/rag_corpus.json").read_bytes())
        manifest = json.loads((ROOT / "kg/rag_corpus/manifest.json").read_text())
        self.assertEqual(manifest["corpus_sha256"], hashlib.sha256(module.serialize(self.corpus)).hexdigest())

    def test_wrong_checkout_version_is_rejected(self):
        with patch.object(module.subprocess, "check_output", return_value="unrelated-commit\n"):
            with self.assertRaisesRegex(ValueError, "HEAD differs"):
                module.build_corpus()

    def test_modified_source_cannot_be_labeled_pinned(self):
        original = Path.read_bytes

        def modified(path):
            data = original(path)
            if path.as_posix().endswith("src/payment/index.js"):
                return data + b"\n// Changed implementation\n"
            return data

        with patch.object(Path, "read_bytes", modified):
            with self.assertRaisesRegex(ValueError, "contents differ"):
                module.build_corpus()

    def test_modified_retrieval_text_is_detected(self):
        damaged = copy.deepcopy(self.corpus)
        damaged["chunks"][0]["text"] = "A service name proves its deployed revision."
        with self.assertRaisesRegex(ValueError, "Text hash"):
            module.validate(damaged)

    def test_intervention_answer_is_rejected(self):
        leaked = copy.deepcopy(self.corpus)
        chunk = leaked["chunks"][0]
        chunk["text"] = "The ground_truth is a preselected fault."
        chunk["text_sha256"] = hashlib.sha256(chunk["text"].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Intervention"):
            module.validate(leaked)

    def test_noncausal_and_version_limits_are_preserved(self):
        by_id = {c["id"]: c for c in self.corpus["chunks"]}
        self.assertIn("not fault responsibility", by_id["rule-span-direction"]["application_limit"])
        self.assertIn("initiating cause", by_id["rule-span-status"]["application_limit"])
        self.assertIn("deployed-source equality", by_id["rule-service-version"]["application_limit"])
        for chunk in self.corpus["chunks"]:
            if chunk["kind"] == "platform_context":
                self.assertEqual(chunk["rule_status"], "source_supported")
                self.assertIn("execution require incident evidence", chunk["scope"])
                self.assertEqual(len(chunk["source_sha256"]), 64)

    def test_condition_and_exception_not_lost_in_chunks(self):
        by_id = {c["id"]: c for c in self.corpus["chunks"]}
        self.assertIn("rather than an immediate failed order response", by_id["shop-checkout-email-handling"]["text"])
        self.assertIn("zero units allow either sign", by_id["shop-money-contract"]["text"])
        self.assertIn("without Unavailable or Internal", by_id["shop-frontend-error-mapping"]["text"])

    def test_no_secrets_or_case_answers_in_corpus(self):
        text = module.serialize(self.corpus).decode().lower()
        for forbidden in ("neo4j_password", "gemini_api_key", "credentials.json", "shop-pilot-", "paymentfailure", "paymentunreachable"):
            self.assertNotIn(forbidden, text)
        for chunk in self.corpus["chunks"]:
            self.assertNotIn("observed", chunk["rule_status"])


if __name__ == "__main__":
    unittest.main()
