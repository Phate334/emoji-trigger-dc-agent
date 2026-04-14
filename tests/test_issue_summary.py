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

    def test_render_markdown_includes_first_issue_comments(self) -> None:
        markdown = issue_summary.render_markdown(
            message={
                "jump_url": "https://discord.test/messages/1001",
                "id": 1001,
            },
            trigger={
                "emoji": "🔎",
                "source": "manual_test",
                "observed_at": "2026-04-15T00:00:00+00:00",
            },
            summaries=[
                {
                    "iid": "77",
                    "_project_ref": "group%2Fotter-stream",
                    "title": "Latest issue",
                    "state": "opened",
                    "labels": ["bug"],
                    "assignees": [{"name": "Alice"}],
                    "author": {"name": "Bob"},
                    "web_url": "https://gitlab.example.com/group/otter-stream/-/issues/77",
                    "updated_at": "2026-04-15T00:00:00Z",
                    "user_notes_count": 2,
                    "description": "Issue body",
                    "_notes": [
                        issue_summary.IssueNote(
                            id=1,
                            author_name="Carol",
                            created_at="2026-04-15T00:01:00Z",
                            system=False,
                            body="First comment",
                        ),
                        issue_summary.IssueNote(
                            id=2,
                            author_name="GitLab",
                            created_at="2026-04-15T00:02:00Z",
                            system=True,
                            body="System note",
                        ),
                    ],
                },
                {
                    "iid": "76",
                    "_project_ref": "group%2Fotter-stream",
                    "title": "Second issue",
                    "state": "closed",
                    "labels": [],
                    "assignees": [],
                    "author": {"name": "Dana"},
                    "web_url": "https://gitlab.example.com/group/otter-stream/-/issues/76",
                    "updated_at": "2026-04-14T00:00:00Z",
                    "user_notes_count": 0,
                    "description": "Another issue body",
                    "_notes": [],
                },
            ],
            issue_count=2,
        )

        self.assertIn("## Latest Issues", markdown)
        self.assertIn("## First Issue Detail: #77", markdown)
        self.assertIn("### Comments", markdown)
        self.assertIn("First comment", markdown)
        self.assertIn("System note", markdown)
