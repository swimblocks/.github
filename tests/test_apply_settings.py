"""Unit tests for the pure helpers in scripts/apply_settings.py.

`scripts/` is not an installed package, so load the script by path via
importlib rather than importing it. The functions under test (`patch_args`,
`_flatten_protection`) are pure — no `gh`/network — so they run in CI without
credentials.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apply_settings.py"
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


class TestSecretValues:
    def test_takes_each_listed_value_from_the_environment(self):
        values, missing = apply_settings.secret_values(
            [{"name": "A"}, {"name": "B"}], {"A": "1", "B": "2", "C": "3"}
        )
        assert values == {"A": "1", "B": "2"}
        assert missing == []

    def test_reports_names_without_a_value(self):
        values, missing = apply_settings.secret_values(
            [{"name": "A"}, {"name": "B"}], {"A": "1"}
        )
        assert values == {"A": "1"}
        assert missing == ["B"]

    def test_empty_value_counts_as_missing(self):
        # An unset Actions secret reaches the environment as an empty string.
        values, missing = apply_settings.secret_values([{"name": "A"}], {"A": ""})
        assert values == {}
        assert missing == ["A"]

    def test_entries_without_a_name_are_ignored(self):
        assert apply_settings.secret_values([{}], {}) == ({}, [])


class TestApplySecrets:
    def test_value_goes_on_stdin_not_argv(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(apply_settings.subprocess, "run", fake_run)
        assert apply_settings.apply_secrets("swimblocks/x", {"A": "s3cret"})
        cmd, kwargs = calls[0]
        assert "s3cret" not in cmd
        assert kwargs["input"] == "s3cret"
        assert cmd[:3] == ["gh", "secret", "set"]

    def test_failure_is_reported_without_the_value(self, monkeypatch, capsys):
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(
                1, cmd, stderr="gh: Forbidden (HTTP 403)"
            )

        monkeypatch.setattr(apply_settings.subprocess, "run", fake_run)
        assert not apply_settings.apply_secrets("swimblocks/x", {"A": "s3cret"})
        out = capsys.readouterr().out
        assert "HTTP 403" in out
        assert "s3cret" not in out


class TestSameFile:
    def test_identical_bytes_match(self):
        assert apply_settings.same_file(b"a\nb\n", b"a\nb\n")

    def test_line_endings_do_not_matter(self):
        # A Windows checkout's copy of the template has CRLF line endings.
        assert apply_settings.same_file(b"a\r\nb\r\n", b"a\nb\n")

    def test_different_content_does_not_match(self):
        assert not apply_settings.same_file(b"a\nb\n", b"a\nc\n")


class TestVerifyRequiredFiles:
    FILES = [{"path": ".github/workflows/x.yml", "source": "templates/x.yml"}]

    def _fake_gh(self, monkeypatch, tmp_path, template, response):
        """Write *template* as the source; make gh return *response*, or raise it."""
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "x.yml").write_bytes(template)
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(apply_settings.subprocess, "run", fake_run)
        return calls

    def _content(self, data: bytes) -> subprocess.CompletedProcess:
        # The contents API wraps its base64 in lines, as encodebytes does.
        b64 = base64.encodebytes(data).decode()
        return subprocess.CompletedProcess(["gh"], 0, stdout=b64)

    def test_matching_file_passes(self, monkeypatch, tmp_path, capsys):
        response = self._content(b"on: pr\n")
        calls = self._fake_gh(monkeypatch, tmp_path, b"on: pr\n", response)
        assert apply_settings.verify_required_files("o/r", self.FILES, tmp_path)
        url = "repos/o/r/contents/.github/workflows/x.yml"
        assert calls[0][:3] == ["gh", "api", url]
        assert "OK  file '.github/workflows/x.yml'" in capsys.readouterr().out

    def test_changed_file_fails(self, monkeypatch, tmp_path, capsys):
        response = self._content(b"on: push\n")
        self._fake_gh(monkeypatch, tmp_path, b"on: pr\n", response)
        assert not apply_settings.verify_required_files("o/r", self.FILES, tmp_path)
        assert "differs from templates/x.yml" in capsys.readouterr().out

    def test_missing_file_fails_with_gh_message(self, monkeypatch, tmp_path, capsys):
        missing = subprocess.CalledProcessError(
            1, ["gh"], stderr="gh: Not Found (HTTP 404)\n")
        self._fake_gh(monkeypatch, tmp_path, b"on: pr\n", missing)
        assert not apply_settings.verify_required_files("o/r", self.FILES, tmp_path)
        assert "could not read: gh: Not Found (HTTP 404)" in capsys.readouterr().out

    def test_settings_lists_the_review_caller(self):
        root = _MODULE_PATH.parents[1]
        settings = apply_settings.load_settings(root / ".github" / "settings.yml")
        entry = {"path": ".github/workflows/readability-review.yml",
                 "source": "workflow-templates/readability-review.yml"}
        assert entry in settings["required_files"]
        assert (root / entry["source"]).is_file()
