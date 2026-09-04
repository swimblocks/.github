"""Unit tests for the pure helpers in scripts/apply-settings.py.

The script has a hyphen in its name, so it isn't importable as a normal
module; load it by path via importlib. The functions under test
(`patch_args`, `_flatten_protection`) are pure — no `gh`/network — so they
run in CI without credentials.
"""

from __future__ import annotations

import importlib.util
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


class TestLabelUpdates:
    _DESIRED = {"name": "no-issue", "color": "ededed", "description": "Skips the issue"}

    def test_in_sync_returns_nothing(self):
        actual = {"color": "ededed", "description": "Skips the issue"}
        assert apply_settings.label_updates(self._DESIRED, actual) == {}

    def test_hash_prefix_and_case_do_not_count_as_drift(self):
        desired = {"color": "#EDEDED", "description": "Skips the issue"}
        actual = {"color": "ededed", "description": "Skips the issue"}
        assert apply_settings.label_updates(desired, actual) == {}

    def test_colour_drift_is_reported_normalized(self):
        actual = {"color": "FF0000", "description": "Skips the issue"}
        assert apply_settings.label_updates(self._DESIRED, actual) == {
            "color": "ededed",
        }

    def test_description_drift_is_reported(self):
        actual = {"color": "ededed", "description": "something else"}
        assert apply_settings.label_updates(self._DESIRED, actual) == {
            "description": "Skips the issue",
        }

    def test_null_description_on_the_repo_counts_as_empty(self):
        # The API returns null, not "", for a label with no description.
        desired = {"color": "ededed"}
        actual = {"color": "ededed", "description": None}
        assert apply_settings.label_updates(desired, actual) == {}

    def test_missing_desired_colour_is_not_treated_as_drift(self):
        # A YAML entry with no colour shouldn't blank the repo's colour.
        desired = {"name": "no-issue", "description": "Skips the issue"}
        actual = {"color": "ededed", "description": "Skips the issue"}
        assert apply_settings.label_updates(desired, actual) == {}

    def test_both_fields_drifted(self):
        actual = {"color": "FF0000", "description": None}
        assert apply_settings.label_updates(self._DESIRED, actual) == {
            "color": "ededed",
            "description": "Skips the issue",
        }
