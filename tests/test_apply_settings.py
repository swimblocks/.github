"""Unit tests for the pure helpers in scripts/apply-settings.py.

The script has a hyphen in its name, so it isn't importable as a normal
module; load it by path via importlib. The functions under test
(`patch_args`, `_flatten_protection`) are pure — no `gh`/network — so they
run in CI without credentials.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apply-settings.py"
_spec = importlib.util.spec_from_file_location("apply_settings", _MODULE_PATH)
apply_settings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_settings)

# A representative release tag, the shape release.yml publishes.
TAG = "settings-2026-09-08"


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


class TestStderrIsCaptured:
    """A call reported through `gh_error` has to capture stderr.

    Without it `gh_error` can only ever print a bare exit code, and gh's
    unbuffered stderr lands in the log seconds ahead of the buffered line that
    explains it — which is how two `(HTTP 403)` lines came to look like
    unexplained failures in the 2026-09-06 rollout.
    """

    def _calls(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            # Enough for list_rulesets to parse on the way through.
            return subprocess.CompletedProcess(cmd, 0, stdout="[]")

        monkeypatch.setattr(apply_settings.subprocess, "run", fake_run)
        return calls

    def test_apply_branch_protection_captures_stderr(self, monkeypatch):
        calls = self._calls(monkeypatch)
        apply_settings.apply_branch_protection(
            "swimblocks/x", "main", {"enforce_admins": False}
        )
        assert calls[-1][1]["stderr"] is subprocess.PIPE

    def test_apply_ruleset_captures_stderr(self, monkeypatch):
        calls = self._calls(monkeypatch)
        apply_settings.apply_ruleset("swimblocks/x", {"name": "swimblocks-default"})
        assert calls[-1][1]["stderr"] is subprocess.PIPE

    def test_set_settings_version_captures_stderr(self, monkeypatch):
        calls = self._calls(monkeypatch)
        apply_settings.set_settings_version("swimblocks/x", "settings-2026-09-08")
        assert calls[-1][1]["stderr"] is subprocess.PIPE


class TestVersionPayload:
    def test_names_the_property_and_the_tag(self):
        assert apply_settings.version_payload("settings-2026-09-08") == {
            "properties": [
                {"property_name": "settings_version", "value": "settings-2026-09-08"}
            ]
        }

    def test_property_name_matches_the_documented_one(self):
        # docs/reconciler.md's drift query selects on this exact string, and the
        # org-level definition is created by hand — a rename here silently stops
        # the query matching rather than failing anything.
        assert apply_settings.SETTINGS_VERSION_PROPERTY == "settings_version"


class TestSetSettingsVersion:
    def _patch_run(self, monkeypatch, result):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(apply_settings.subprocess, "run", fake_run)
        return calls

    def test_patches_the_repo_properties_endpoint(self, monkeypatch):
        calls = self._patch_run(
            monkeypatch, subprocess.CompletedProcess(["gh"], 0, stdout="")
        )
        assert apply_settings.set_settings_version("swimblocks/x", TAG)
        cmd, kwargs = calls[-1]
        assert cmd[:5] == [
            "gh", "api", "-X", "PATCH", "repos/swimblocks/x/properties/values"
        ]
        assert json.loads(kwargs["input"]) == apply_settings.version_payload(TAG)

    def test_failure_is_reported_and_returns_false(self, monkeypatch, capsys):
        # A 422 is the shape seen when settings_version isn't defined on the org.
        self._patch_run(
            monkeypatch,
            subprocess.CalledProcessError(
                1, ["gh"], stderr="gh: Invalid property name (HTTP 422)\n"
            ),
        )
        assert not apply_settings.set_settings_version("swimblocks/x", TAG)
        out = capsys.readouterr().out
        assert "FAIL settings_version" in out
        assert "(HTTP 422)" in out
