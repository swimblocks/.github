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
        reviews = {"required_approving_review_count": 1, "require_code_owner_reviews": True}
        actual = {"required_pull_request_reviews": reviews}
        flat = apply_settings._flatten_protection(actual)
        assert flat["required_pull_request_reviews"] == reviews

    def test_output_always_covers_every_protection_key(self):
        flat = apply_settings._flatten_protection({})
        assert set(flat) == apply_settings.PROTECTION_KEYS
