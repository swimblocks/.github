"""Unit tests for the pure helpers in scripts/apply-settings.py.

The script has a hyphen in its name, so it isn't importable as a normal
module; load it by path via importlib. The functions under test
(`patch_args`, `_flatten_protection`) are pure — no `gh`/network — so they
run in CI without credentials.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apply-settings.py"
_spec = importlib.util.spec_from_file_location("apply_settings", _MODULE_PATH)
apply_settings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_settings)


class TestPatchArgs:
    def test_bool_true_uses_F_flag_with_lowercase_true(self):
        assert apply_settings.patch_args({"allow_squash_merge": True}) == [
            "-F",
            "allow_squash_merge=true",
        ]

    def test_bool_false_uses_F_flag_with_lowercase_false(self):
        assert apply_settings.patch_args({"allow_merge_commit": False}) == [
            "-F",
            "allow_merge_commit=false",
        ]

    def test_string_value_uses_f_flag(self):
        assert apply_settings.patch_args({"squash_merge_commit_title": "PR_TITLE"}) == [
            "-f",
            "squash_merge_commit_title=PR_TITLE",
        ]

    def test_non_patchable_keys_are_skipped(self):
        assert apply_settings.patch_args({"not_a_real_setting": True}) == []

    def test_empty_block_returns_empty_list(self):
        assert apply_settings.patch_args({}) == []

    def test_mixed_block_filters_unknown_and_preserves_order(self):
        args = apply_settings.patch_args(
            {
                "allow_squash_merge": True,
                "ignored": "x",
                "squash_merge_commit_message": "PR_BODY",
            }
        )
        assert args == [
            "-F",
            "allow_squash_merge=true",
            "-f",
            "squash_merge_commit_message=PR_BODY",
        ]


class TestFlattenProtection:
    def test_enabled_wrapper_flattens_to_bool(self):
        actual = {"required_linear_history": {"enabled": True}}
        flat = apply_settings._flatten_protection(actual)
        assert flat["required_linear_history"] is True

    def test_url_enabled_wrapper_flattens_to_bool(self):
        actual = {"allow_force_pushes": {"url": "https://api", "enabled": False}}
        flat = apply_settings._flatten_protection(actual)
        assert flat["allow_force_pushes"] is False

    def test_missing_key_becomes_none(self):
        assert apply_settings._flatten_protection({})["enforce_admins"] is None

    def test_non_wrapper_dict_passes_through_unchanged(self):
        reviews = {
            "required_approving_review_count": 1,
            "require_code_owner_reviews": True,
        }
        actual = {"required_pull_request_reviews": reviews}
        flat = apply_settings._flatten_protection(actual)
        assert flat["required_pull_request_reviews"] == reviews

    def test_output_always_covers_every_protection_key(self):
        flat = apply_settings._flatten_protection({})
        assert set(flat) == apply_settings.PROTECTION_KEYS


class TestNormalizeColor:
    def test_strips_leading_hash(self):
        assert apply_settings.normalize_color("#EDEDED") == "ededed"

    def test_lowercases(self):
        assert apply_settings.normalize_color("A2EEEF") == "a2eeef"

    def test_already_normal_is_unchanged(self):
        assert apply_settings.normalize_color("ededed") == "ededed"

    def test_none_becomes_empty(self):
        assert apply_settings.normalize_color(None) == ""


class TestMissingLabels:
    _DESIRED = [
        {"name": "no-issue", "color": "ededed", "description": "Skips the issue"},
    ]

    def test_absent_label_is_reported(self):
        assert apply_settings.missing_labels(self._DESIRED, {}) == self._DESIRED

    def test_present_label_is_not_reported(self):
        actual = {"no-issue": {"color": "ededed", "description": "Skips the issue"}}
        assert apply_settings.missing_labels(self._DESIRED, actual) == []

    def test_name_match_is_case_insensitive(self):
        # GitHub label names are case-insensitive, so a differently-cased
        # label on the repo must not read as missing.
        actual = {"no-issue": {"color": "ededed"}}
        desired = [{"name": "No-Issue", "color": "ededed"}]
        assert apply_settings.missing_labels(desired, actual) == []

    def test_drifted_colour_is_not_treated_as_missing(self):
        # Existing labels are left alone; only absence is acted on.
        actual = {"no-issue": {"color": "ff0000", "description": "something else"}}
        assert apply_settings.missing_labels(self._DESIRED, actual) == []

    def test_entry_without_a_name_is_skipped(self):
        assert apply_settings.missing_labels([{"color": "ededed"}], {}) == []

    def test_only_the_absent_entries_are_returned(self):
        desired = [{"name": "no-issue"}, {"name": "needs-decision"}]
        actual = {"no-issue": {"color": "ededed"}}
        assert apply_settings.missing_labels(desired, actual) == [
            {"name": "needs-decision"},
        ]


class TestGhError:
    def _err(self, stderr, returncode=1):
        return subprocess.CalledProcessError(returncode, ["gh"], stderr=stderr)

    def test_uses_the_gh_message(self):
        # The 403 that cost an afternoon of diagnosis on 2026-09-05.
        err = self._err("gh: Resource not accessible by integration (HTTP 403)\n")
        assert apply_settings.gh_error(err) == (
            ": gh: Resource not accessible by integration (HTTP 403)"
        )

    def test_keeps_only_the_last_line(self):
        err = self._err("some preamble\nmore noise\ngh: Not Found (HTTP 404)\n")
        assert apply_settings.gh_error(err) == ": gh: Not Found (HTTP 404)"

    def test_falls_back_to_the_exit_code_when_stderr_is_empty(self):
        assert apply_settings.gh_error(self._err("", returncode=2)) == " (exit 2)"

    def test_falls_back_when_stderr_is_none(self):
        assert apply_settings.gh_error(self._err(None)) == " (exit 1)"

    def test_blank_lines_are_not_mistaken_for_a_message(self):
        assert apply_settings.gh_error(self._err("\n  \n")) == " (exit 1)"


class TestSummaryTable:
    def test_lists_every_repo_with_the_version(self):
        table = apply_settings.summary_table(
            "settings-2026-09-08", ["swimblocks/a", "swimblocks/b"], []
        )
        assert "## Settings rollout — `settings-2026-09-08`" in table
        assert "| `swimblocks/a` | OK — applied | `settings-2026-09-08` |" in table
        assert "| `swimblocks/b` | OK — applied | `settings-2026-09-08` |" in table

    def test_marks_only_the_failed_repos(self):
        table = apply_settings.summary_table(
            "settings-2026-09-08", ["swimblocks/a", "swimblocks/b"], ["swimblocks/b"]
        )
        assert "| `swimblocks/a` | OK — applied |" in table
        assert "| `swimblocks/b` | FAIL — drift remains |" in table

    def test_unversioned_run_still_renders(self):
        # create-repo.sh and a local run pass no --version.
        table = apply_settings.summary_table("", ["swimblocks/a"], [])
        assert "## Settings rollout\n" in table
        assert "| `swimblocks/a` | OK — applied | `unversioned` |" in table

    def test_no_repos_leaves_a_header_only_table(self):
        table = apply_settings.summary_table("settings-2026-09-08", [], [])
        assert table.rstrip().endswith("|---|---|---|")


class TestParseArgs:
    def test_repos_only(self):
        opts = apply_settings.parse_args(["swimblocks/a", "swimblocks/b"])
        assert opts.repos == ["swimblocks/a", "swimblocks/b"]
        assert opts.version == ""
        assert opts.summary_file is None

    def test_version_and_summary_file(self):
        opts = apply_settings.parse_args(
            ["--version", "settings-2026-09-08",
             "--summary-file", "out.md", "swimblocks/a"]
        )
        assert opts.version == "settings-2026-09-08"
        assert opts.summary_file == "out.md"
        assert opts.repos == ["swimblocks/a"]
