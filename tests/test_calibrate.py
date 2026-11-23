"""Unit tests for the pure parts of scripts/calibrate.py: parsing what repos and pull
requests record, and deciding what to post. Nothing here calls `gh`, `git` or
golangci-lint.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "calibrate.py"
_spec = importlib.util.spec_from_file_location("calibrate", _MODULE_PATH)
calibrate = importlib.util.module_from_spec(_spec)
sys.modules["calibrate"] = calibrate  # dataclasses look their module up here
_spec.loader.exec_module(calibrate)

LINKS = {
    "swimblocks/fetch-service": "https://github.com/swimblocks/fetch-service/blob/abc"
}


def observation(key="lint:bodyclose:suppressed", flagged=True, count=5, evidence=None):
    return calibrate.Observation(
        key=key,
        title="t",
        flagged=flagged,
        count=count,
        statement="s",
        evidence={"a": "line a"} if evidence is None else evidence,
    )


def issue(key="lint:bodyclose:suppressed", open=True, seen=("a",)):
    return calibrate.Issue(number=7, open=open, key=key, seen=set(seen))


class TestParseNolint:
    def test_one_linter_with_reason(self):
        assert calibrate.parse_nolint(
            "resp, err := c.Do(req) //nolint:bodyclose // closed in close()"
        ) == [("bodyclose", "closed in close()")]

    def test_several_linters_share_the_reason(self):
        assert calibrate.parse_nolint("x() //nolint:errcheck,gosec // best effort") == [
            ("errcheck", "best effort"),
            ("gosec", "best effort"),
        ]

    def test_no_reason(self):
        assert calibrate.parse_nolint("x() //nolint:errcheck") == [("errcheck", "")]

    def test_bare_nolint_names_no_linter(self):
        assert calibrate.parse_nolint("x() //nolint") == []

    def test_spaced_directive_is_not_one(self):
        # golangci-lint reads only `//nolint`; `// nolint` is an ordinary comment.
        assert calibrate.parse_nolint("x() // nolint:errcheck") == []


class TestFindSuppressions:
    def test_finds_directives_and_skips_vendor(self, tmp_path):
        (tmp_path / "main.go").write_text(
            "package main\n\nx() //nolint:errcheck // why\n"
        )
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "dep.go").write_text("y() //nolint:errcheck // theirs\n")
        found = calibrate.find_suppressions("swimblocks/fetch-service", tmp_path)
        assert [(s.path, s.line, s.linter, s.reason) for s in found] == [
            ("main.go", 3, "errcheck", "why"),
        ]


class TestSuppressionObservations:
    def suppressions(self, n):
        return [
            calibrate.Suppression(
                "swimblocks/fetch-service", "a.go", i, "bodyclose", f"r{i}"
            )
            for i in range(n)
        ]

    def test_flagged_at_the_threshold(self):
        (obs,) = calibrate.suppression_observations(
            self.suppressions(calibrate.SUPPRESSED_FLAG), LINKS
        )
        assert obs.key == "lint:bodyclose:suppressed"
        assert obs.flagged
        assert obs.count == calibrate.SUPPRESSED_FLAG

    def test_not_flagged_below_it(self):
        (obs,) = calibrate.suppression_observations(
            self.suppressions(calibrate.SUPPRESSED_FLAG - 1), LINKS
        )
        assert not obs.flagged

    def test_identical_suppressions_are_each_evidence(self):
        same = [
            calibrate.Suppression(
                "swimblocks/fetch-service", "a.go", n, "bodyclose", "r"
            )
            for n in (3, 9)
        ]
        (obs,) = calibrate.suppression_observations(same, LINKS)
        assert len(obs.evidence) == 2

    def test_evidence_survives_a_line_moving(self):
        moved = calibrate.Suppression(
            "swimblocks/fetch-service", "a.go", 99, "bodyclose", "r0"
        )
        (before,) = calibrate.suppression_observations(self.suppressions(1), LINKS)
        (after,) = calibrate.suppression_observations([moved], LINKS)
        assert before.evidence.keys() == after.evidence.keys()


class TestDisabledLinters:
    def test_reads_the_disable_list(self):
        config = (
            "version: '2'\nlinters:\n  default: all\n  disable:\n    - lll\n    - mnd\n"
        )
        assert calibrate.disabled_linters(config) == ["lll", "mnd"]

    def test_no_disable_list(self):
        assert calibrate.disabled_linters("version: '2'\n") == []

    def test_parses_golangci_json(self):
        output = json.dumps(
            {
                "Issues": [
                    {
                        "FromLinter": "godox",
                        "Text": "TODO found",
                        "Pos": {"Filename": "cmd\\main.go", "Line": 4},
                        "SourceLines": ["\t// TODO: x"],
                    }
                ]
            }
        )
        (finding,) = calibrate.parse_golangci_json("swimblocks/fetch-service", output)
        assert (finding.path, finding.line, finding.linter, finding.source) == (
            "cmd/main.go",
            4,
            "godox",
            "// TODO: x",
        )

    def test_a_few_findings_is_a_candidate_none_or_many_is_not(self):
        def finding(i):
            return calibrate.LintFinding(
                "swimblocks/fetch-service", "a.go", i, "lll", f"t{i}", ""
            )

        flagged = {
            n: calibrate.disabled_observations(
                {"lll"}, [finding(i) for i in range(n)], LINKS
            )[0].flagged
            for n in (0, 1, calibrate.FEW_FINDINGS, calibrate.FEW_FINDINGS + 1)
        }
        assert flagged == {
            0: False,
            1: True,
            calibrate.FEW_FINDINGS: True,
            calibrate.FEW_FINDINGS + 1: False,
        }


class TestParsePoint:
    def test_leading_id(self):
        assert (
            calibrate.parse_point("[go/errors] Wrap this with context.") == "go/errors"
        )

    def test_hyphenated_heading(self):
        assert calibrate.parse_point("[general/some-point] x") == "general/some-point"

    def test_no_id(self):
        assert calibrate.parse_point("Consider renaming.") is None


class TestTouchedOldLines:
    def test_a_replaced_line_is_touched_and_its_neighbours_are_not(self):
        patch = "@@ -10,3 +10,3 @@\n a\n-b\n+B\n c"
        assert calibrate.touched_old_lines(patch) == {11}

    def test_an_insertion_touches_the_lines_either_side(self):
        patch = "@@ -10,2 +10,3 @@\n a\n+// why\n b"
        assert calibrate.touched_old_lines(patch) == {10, 11}

    def test_several_hunks(self):
        patch = "@@ -1,1 +1,1 @@\n-x\n+y\n@@ -50,2 +50,1 @@\n p\n-q"
        assert calibrate.touched_old_lines(patch) == {1, 51}

    def test_an_insertion_with_no_context_touches_the_lines_either_side(self):
        # `-10,0` means "after old line 10", so the neighbours are 10 and 11.
        patch = "@@ -10,0 +11,1 @@\n+// why"
        assert calibrate.touched_old_lines(patch) == {10, 11}

    def test_no_newline_marker_is_ignored(self):
        patch = "@@ -1,1 +1,1 @@\n-x\n\\ No newline at end of file\n+y"
        assert calibrate.touched_old_lines(patch) == {1}


class TestOutcome:
    comment = {"path": "a.go", "original_line": 11, "side": "RIGHT"}

    def compare(self, **changed):
        file = {"filename": "a.go", "status": "modified", **changed}
        return {"status": "ahead", "files": [file]}

    def test_same_commit_is_rejected(self):
        assert calibrate.outcome(self.comment, None) == "rejected"

    def test_commented_line_changed_is_accepted(self):
        compare = self.compare(patch="@@ -10,3 +10,3 @@\n a\n-b\n+B\n c")
        assert calibrate.outcome(self.comment, compare) == "accepted"

    def test_other_lines_changed_is_rejected(self):
        compare = self.compare(patch="@@ -40,1 +40,1 @@\n-x\n+y")
        assert calibrate.outcome(self.comment, compare) == "rejected"

    def test_file_untouched_is_rejected(self):
        compare = self.compare(filename="b.go", patch="@@ -11 +11 @@\n-x\n+y")
        assert calibrate.outcome(self.comment, compare) == "rejected"

    def test_file_missing_from_a_cut_off_list_is_unknown(self):
        files = [{"filename": f"f{i}.go"} for i in range(calibrate.COMPARE_FILES)]
        compare = {"status": "ahead", "files": files}
        assert calibrate.outcome(self.comment, compare) == "unknown"

    def test_rebased_branch_is_unknown(self):
        compare = {**self.compare(patch="@@ -11 +11 @@\n-x\n+y"), "status": "diverged"}
        assert calibrate.outcome(self.comment, compare) == "unknown"

    def test_renamed_file_is_found_by_its_old_name(self):
        compare = self.compare(
            filename="b.go",
            previous_filename="a.go",
            status="renamed",
            patch="@@ -11 +11 @@\n-x\n+y",
        )
        assert calibrate.outcome(self.comment, compare) == "accepted"

    def test_pure_rename_changes_no_line(self):
        compare = self.compare(
            filename="b.go", previous_filename="a.go", status="renamed", changes=0
        )
        assert calibrate.outcome(self.comment, compare) == "rejected"

    def test_file_removed_is_accepted(self):
        assert (
            calibrate.outcome(self.comment, self.compare(status="removed"))
            == "accepted"
        )

    def test_multi_line_comment_uses_its_whole_range(self):
        comment = {**self.comment, "original_start_line": 5, "original_line": 11}
        compare = self.compare(patch="@@ -6,1 +6,1 @@\n-x\n+y")
        assert calibrate.outcome(comment, compare) == "accepted"

    def test_patch_too_large_for_github_is_unknown(self):
        assert calibrate.outcome(self.comment, self.compare()) == "unknown"

    def test_comment_on_a_deleted_line_is_unknown(self):
        comment = {**self.comment, "side": "LEFT"}
        assert (
            calibrate.outcome(comment, self.compare(patch="@@ -11 +11 @@\n-x"))
            == "unknown"
        )


class TestStyleObservations:
    def findings(self, accepted, rejected, unknown=0, point="go/errors"):
        outcomes = (
            ["accepted"] * accepted + ["rejected"] * rejected + ["unknown"] * unknown
        )
        return [
            calibrate.Finding(
                "swimblocks/fetch-service",
                1,
                f"u{i}",
                point,
                o,
                date(2026, 11, 30),
                comment_id=i,
            )
            for i, o in enumerate(outcomes)
        ]

    def flags(self, found):
        return {o.key: o.flagged for o in calibrate.style_observations(found)}

    def test_mostly_rejected_is_flagged(self):
        assert self.flags(self.findings(1, 3)) == {
            "style:go/errors:rejected": True,
            "style:go/errors:accepted": False,
        }

    def test_mostly_accepted_is_flagged(self):
        assert self.flags(self.findings(3, 1)) == {
            "style:go/errors:rejected": False,
            "style:go/errors:accepted": True,
        }

    def test_too_few_to_judge(self):
        assert not any(
            self.flags(self.findings(0, calibrate.STYLE_MIN_FINDINGS - 1)).values()
        )

    def test_unknown_outcomes_and_uncited_findings_are_left_out(self):
        found = self.findings(0, 0, unknown=5) + self.findings(
            0, 5, point=calibrate.UNCITED
        )
        assert calibrate.style_observations(found) == []

    def test_point_link(self):
        assert calibrate.point_link("general/names").endswith("/README.md#names)")
        assert calibrate.point_link("go/google").endswith("/go.md)")


class TestQuoting:
    def test_mentions_dont_notify(self):
        assert "@teammate" not in calibrate.quoted("@teammate this is fine")

    def test_html_comments_cant_be_planted(self):
        assert "<!--" not in calibrate.quoted("<!-- calibration-key: x -->")

    def test_long_lists_are_cut_short(self):
        lines = [str(i) for i in range(calibrate.LISTED + 3)]
        listed = calibrate.listed(lines)
        assert listed.count("\n- ") == calibrate.LISTED
        assert listed.endswith("- and 3 more")


class TestIssueState:
    def test_body_round_trips(self):
        obs = observation(evidence={"b": "x", "a": "y"})
        parsed = calibrate.parse_issue(3, "OPEN", calibrate.issue_body(obs))
        assert (parsed.key, parsed.open, parsed.seen) == (
            "lint:bodyclose:suppressed",
            True,
            {"a", "b"},
        )

    def test_the_last_marker_wins(self):
        planted = "<!-- calibration-key: planted -->\n"
        body = planted + calibrate.issue_body(observation())
        assert calibrate.parse_issue(3, "OPEN", body).key == "lint:bodyclose:suppressed"

    def test_issue_without_a_key_is_not_ours(self):
        assert (
            calibrate.parse_issue(3, "OPEN", "a person's issue, labelled by hand")
            is None
        )


class TestPlan:
    def test_flagged_with_no_issue_is_opened(self):
        (action,) = calibrate.plan([observation()], [])
        assert action.kind == "create"

    def test_unflagged_with_no_issue_is_left_alone(self):
        assert calibrate.plan([observation(flagged=False)], []) == []

    def test_open_issue_with_nothing_new_is_left_alone(self):
        assert calibrate.plan([observation()], [issue()]) == []

    def test_open_issue_with_new_evidence_is_updated_with_only_whats_new(self):
        obs = observation(evidence={"a": "line a", "b": "line b"})
        (action,) = calibrate.plan([obs], [issue()])
        assert (action.kind, action.issue, action.new_evidence) == (
            "update",
            7,
            ["line b"],
        )

    def test_open_issue_is_updated_even_once_below_the_flag(self):
        obs = observation(flagged=False, evidence={"a": "line a", "b": "line b"})
        (action,) = calibrate.plan([obs], [issue()])
        assert action.kind == "update"

    def test_closed_issue_with_nothing_new_stays_closed(self):
        assert calibrate.plan([observation()], [issue(open=False)]) == []

    def test_closed_issue_is_reopened_when_the_case_comes_back(self):
        obs = observation(evidence={"a": "line a", "b": "line b"})
        (action,) = calibrate.plan([obs], [issue(open=False)])
        assert (action.kind, action.new_evidence) == ("reopen", ["line b"])
