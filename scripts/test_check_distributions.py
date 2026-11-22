import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_distributions", Path(__file__).with_name("check-distributions.py")
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DistributionChecks(unittest.TestCase):
    def test_public_catalog_and_packaged_assets_are_allowed(self):
        module.check_members([
            "jobhunt/data/skills.yaml", "jobhunt/web/static/index.html",
            "jobhunt/web/static/assets/app.js",
        ], wheel=True)
        module.check_members([
            "jobhunt-0.1.0/README.md", "jobhunt-0.1.0/src/jobhunt/web/static/index.html",
        ], wheel=False)

    def test_private_state_and_windows_paths_are_rejected(self):
        for path in [
            "jobhunt-0.1.0/me/cv.md", "workspace/session.json", ".env.production",
            "config/profile.yaml", "config/sites.yaml", "jobhunt/state.sqlite3",
            "workspace\\people\\one\\cookies.json", "../private", "/absolute",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                module.check_members(["jobhunt/web/static/index.html", path], wheel=True)

    def test_api_only_distributions_cannot_claim_bundled_ui(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            module.check_members(["jobhunt/web/server.py"], wheel=True)


if __name__ == "__main__":
    unittest.main()
