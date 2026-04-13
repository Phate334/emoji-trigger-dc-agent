from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_issue_summary_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "agents"
        / "issue-whisperer"
        / ".claude"
        / "skills"
        / "issue-summary"
        / "scripts"
        / "summarize_issue.py"
    )
    spec = importlib.util.spec_from_file_location("issue_summary_script", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


issue_summary = _load_issue_summary_module()


class IssueSummaryScriptTests(unittest.TestCase):
    def test_extract_issue_references_keeps_project_paths(self) -> None:
        references = issue_summary.extract_issue_references(
            "Check https://gitlab.example.com/group/a/-/issues/12 and "
            "https://gitlab.example.com/group/b/-/issues/12 plus #12"
        )

        self.assertEqual(
            [(reference.iid, reference.project_path) for reference in references],
            [
                ("12", "group/a"),
                ("12", "group/b"),
                ("12", None),
            ],
        )

    def test_shorthand_reference_uses_explicit_default_project_ref(self) -> None:
        reference = issue_summary.IssueReference(iid="42")

        with patch.object(issue_summary, "run_helper") as run_helper:
            project_ref = issue_summary.resolve_reference_project_ref(
                reference=reference,
                default_project_ref="group%2Fproject",
                helper=Path("/tmp/helper.sh"),
                repo_root=Path("/tmp/repo"),
                project_ref_cache={},
            )

        self.assertEqual(project_ref, "group%2Fproject")
        run_helper.assert_not_called()
