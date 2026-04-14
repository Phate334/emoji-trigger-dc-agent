from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_test_issue_whisperer_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "test_issue_whisperer.py"
    spec = importlib.util.spec_from_file_location("test_issue_whisperer_script", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


test_issue_whisperer = _load_test_issue_whisperer_module()


class TestIssueWhispererScriptTests(unittest.TestCase):
    def test_load_latest_issue_urls_uses_explicit_project_id(self) -> None:
        responses = [
            {
                "id": 123,
                "path_with_namespace": "group/otter-stream",
                "name": "otter-stream",
            },
            [
                {"web_url": "https://gitlab.example.com/group/otter-stream/-/issues/11"},
                {"web_url": "https://gitlab.example.com/group/otter-stream/-/issues/10"},
            ],
        ]

        with patch.object(
            test_issue_whisperer,
            "gitlab_request_json",
            side_effect=responses,
        ) as mock_request:
            project, issue_urls = test_issue_whisperer.load_latest_issue_urls(123, 2)

        self.assertEqual(project["id"], 123)
        self.assertEqual(
            issue_urls,
            [
                "https://gitlab.example.com/group/otter-stream/-/issues/11",
                "https://gitlab.example.com/group/otter-stream/-/issues/10",
            ],
        )
        self.assertEqual(mock_request.call_args_list[0].args, ("/projects/123",))
        self.assertEqual(
            mock_request.call_args_list[1].args,
            (
                "/projects/123/issues",
                "state=all",
                "order_by=created_at",
                "sort=desc",
                "per_page=2",
            ),
        )

    def test_parse_args_accepts_project_id_flow(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["test_issue_whisperer.py", "--project-id", "123", "--latest-issues", "3"],
        ):
            args = test_issue_whisperer.parse_args()

        self.assertEqual(args.project_id, 123)
        self.assertEqual(args.latest_issues, 3)
