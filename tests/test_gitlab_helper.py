import subprocess
import tempfile
import unittest
from pathlib import Path

HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "issue-whisperer"
    / ".claude"
    / "skills"
    / "gitlab"
    / "scripts"
    / "gitlab_api.sh"
)


class GitLabHelperTests(unittest.TestCase):
    def test_discover_uses_gitlab_host_env_when_origin_is_github(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/example/repo.git",
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            (repo_root / ".env").write_text("GITLAB_HOST=gitlab.example.com\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", str(HELPER_PATH), "--repo", str(repo_root), "discover"],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn(f"host_source={repo_root / '.env'}", result.stdout)
        self.assertIn("host=gitlab.example.com", result.stdout)
        self.assertIn("project_path=", result.stdout)
