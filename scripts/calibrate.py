"""Weekly calibration report for the org's lint set and style guide (design 0007).

Reads what the org's repos and pull requests already record, and turns each case for
changing the lint set or the style guide into an issue:

- Lint suppressions: every `//nolint:` directive in the org's Go repos. A linter
  suppressed SUPPRESSED_FLAG times or more is flagged.
- Disabled linters: each linter a Go repo's `.golangci.yml` disables is run, and its
  findings counted. One with a few findings is flagged as a candidate to switch on.
- Readability findings: each comment the readability reviewer posted on a merged pull
  request, by the style-guide point it cites, and whether the lines it commented on
  changed before merge (accepted) or not (rejected). A point mostly rejected is flagged
  for rewording or removal; one mostly accepted, as a candidate for a linter.

Each observation has a stable key (`lint:bodyclose:suppressed`), kept in a hidden marker
in its issue, so a later week finds the issue instead of opening another. The rules this
follows are in `docs/design/0007-review-standard.md#calibration-report`.

Usage, from the weekly workflow in swimblocks/.github-private:

    python scripts/calibrate.py --org swimblocks \\
        --issues-repo swimblocks/.github-private --summary-file "$GITHUB_STEP_SUMMARY"

Add --dry-run to print what it would post instead of posting it. Requires `git`, and
`gh` authenticated with read access to every repo's code and pull requests and write
access to issues in --issues-repo. Counting the disabled linters' findings also needs
`go` and `golangci-lint`; --skip-lint leaves it out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

SUPPRESSED_FLAG = 5  # design 0007: "suppressed five or more times"
FEW_FINDINGS = 10  # a disabled linter with 1 to FEW_FINDINGS findings is a candidate
SAMPLE_SIZE = 5  # findings quoted in a disabled linter's issue
STYLE_MIN_FINDINGS = 3  # findings a point needs, accepted or rejected, to be judged
STYLE_REJECTED_FLAG = 0.5  # rejected more often than this: reword or remove
STYLE_ACCEPTED_FLAG = 0.75  # accepted at least this often: a linter candidate
STRONGER = 2  # a closed case is "much stronger" at this multiple of its count

REVIEWER = "claude[bot]"  # the Claude GitHub App, which posts the review's findings
REVIEW_START = "2026-11-23"  # the first day the readability review ran
LABEL = "calibration"

GUIDE = "https://github.com/swimblocks/.github/blob/main/docs/styleguide"
LINT_SET = (
    "https://github.com/swimblocks/.github/blob/main/CONTRIBUTING.md#quality-gates"
)

KEY_MARKER = re.compile(r"<!-- calibration-key: (\S+) -->")
STATE_MARKER = re.compile(r"<!-- calibration-state: (\{.*?\}) -->")
STRONGER_MARKER = "<!-- calibration-stronger -->"


# ---------------------------------------------------------------------------
# Observations, and what to do about each
# ---------------------------------------------------------------------------


@dataclass
class Observation:
    """One case for changing the lint set or the style guide, as it stands this week."""

    key: str
    title: str
    flagged: bool
    # How strong the case is; compared when a closed issue's case grows.
    count: int
    # The issue body: the observation, its numbers, the suggested change.
    statement: str
    # Evidence id -> one markdown line describing it.
    evidence: dict[str, str] = field(default_factory=dict)


@dataclass
class Issue:
    number: int
    open: bool
    key: str
    count: int
    seen: set[str]
    stronger_noted: bool = False


@dataclass
class Action:
    kind: str  # "create", "update" or "stronger"
    observation: Observation
    issue: int | None = None
    new_evidence: list[str] = field(default_factory=list)


def evidence_ids(items: list[tuple[str, ...]]) -> list[str]:
    """A short, stable id for each piece of evidence, kept in the issue's hidden state.

    Each item is what identifies the evidence without its line number, which moves as a
    file is edited. Identical items, such as two suppressions with the same reason in
    one file, are told apart by their order.
    """
    seen: dict[tuple[str, ...], int] = defaultdict(int)
    ids = []
    for item in items:
        seen[item] += 1
        key = "\0".join((*item, str(seen[item])))
        ids.append(hashlib.sha1(key.encode()).hexdigest()[:12])
    return ids


def issue_body(obs: Observation) -> str:
    state = {"count": obs.count, "seen": sorted(obs.evidence)}
    return (
        f"{obs.statement}\n\n"
        f"<!-- calibration-key: {obs.key} -->\n"
        f"<!-- calibration-state: {json.dumps(state, separators=(',', ':'))} -->\n"
    )


def parse_issue(number: int, state: str, body: str) -> Issue | None:
    """The calibration issue behind *body*, or None if it carries no key."""
    key = KEY_MARKER.search(body or "")
    if not key:
        return None
    saved = STATE_MARKER.search(body)
    data = json.loads(saved.group(1)) if saved else {}
    return Issue(
        number=number,
        open=state.upper() == "OPEN",
        key=key.group(1),
        count=int(data.get("count", 0)),
        seen=set(data.get("seen", [])),
    )


def plan(observations: list[Observation], issues: list[Issue]) -> list[Action]:
    """What to post this week.

    A flagged observation with no issue gets one. An open issue whose observation has
    new evidence gets a comment and a rewritten body. A closed issue is never reopened:
    if its case grows to STRONGER times what it was, it gets one comment saying so, and
    then nothing more. A week with nothing new touches nothing.
    """
    by_key = {issue.key: issue for issue in issues}
    actions = []
    for obs in observations:
        issue = by_key.get(obs.key)
        if issue is None:
            if obs.flagged:
                actions.append(Action("create", obs))
        elif issue.open:
            new = [line for eid, line in obs.evidence.items() if eid not in issue.seen]
            if new:
                actions.append(Action("update", obs, issue.number, new))
        elif not issue.stronger_noted and issue.count:
            if obs.count >= STRONGER * issue.count:
                actions.append(Action("stronger", obs, issue.number))
    return actions


def update_comment(action: Action) -> str:
    lines = "\n".join(f"- {line}" for line in action.new_evidence)
    return (
        f"New since the last report:\n\n{lines}\n\n"
        "The description now gives the case as it stands."
    )


def stronger_comment(action: Action, was: int) -> str:
    return (
        f"{STRONGER_MARKER}\n"
        f"This case has grown since it was closed: {action.observation.count} now, "
        f"against {was} then. The calibration report won't reopen it or say this "
        f"again.\n\n{action.observation.statement}"
    )


def where(links: dict[str, str], repo: str, path: str, line: int) -> str:
    """A markdown link to one line of a cloned repo, labelled with where it is."""
    return f"`{repo}` [{path}:{line}]({links[repo]}/{path}#L{line})"


# ---------------------------------------------------------------------------
# Lint suppressions
# ---------------------------------------------------------------------------

NOLINT = re.compile(r"//nolint:([\w,-]+)(?:\s*//\s*(.*\S))?")


@dataclass
class Suppression:
    repo: str
    path: str
    line: int
    linter: str
    reason: str


def parse_nolint(text: str) -> list[tuple[str, str]]:
    """The (linter, reason) pairs a `//nolint:` directive on this line suppresses."""
    match = NOLINT.search(text)
    if not match:
        return []
    reason = match.group(2) or ""
    return [(linter, reason) for linter in match.group(1).split(",") if linter]


def find_suppressions(repo: str, root: Path) -> list[Suppression]:
    found = []
    for path in sorted(root.rglob("*.go")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("vendor/"):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, text in enumerate(lines, 1):
            for linter, reason in parse_nolint(text):
                found.append(Suppression(repo, rel, number, linter, reason))
    return found


def suppression_observations(
    found: list[Suppression], links: dict[str, str]
) -> list[Observation]:
    by_linter = defaultdict(list)
    for s in found:
        by_linter[s.linter].append(s)
    observations = []
    for linter, group in sorted(by_linter.items()):
        ids = evidence_ids([(s.repo, s.path, s.linter, s.reason) for s in group])
        lines = {
            eid: f"{where(links, s.repo, s.path, s.line)}: {s.reason or '*(none)*'}"
            for eid, s in zip(ids, group)
        }
        statement = (
            f"`{linter}` is suppressed {len(group)} times across the org's Go repos. "
            "A linter suppressed this often is either set up wrong for how we write "
            "Go, or wrong for us; the reasons below say which.\n\n"
            f"**Suggested change:** configure `{linter}` in the org's `.golangci.yml` "
            f"([lint set]({LINT_SET})) so these stop firing, or move it to the "
            "disable list with the reason it doesn't fit.\n\n"
            + "\n".join(f"- {line}" for line in lines.values())
        )
        observations.append(
            Observation(
                key=f"lint:{linter}:suppressed",
                title=f"{linter} suppressed {len(group)} times",
                flagged=len(group) >= SUPPRESSED_FLAG,
                count=len(group),
                statement=statement,
                evidence=lines,
            )
        )
    return observations


# ---------------------------------------------------------------------------
# Disabled linters
# ---------------------------------------------------------------------------


@dataclass
class LintFinding:
    repo: str
    path: str
    line: int
    linter: str
    text: str
    source: str


def disabled_linters(golangci_yml: str) -> list[str]:
    config = yaml.safe_load(golangci_yml) or {}
    return list((config.get("linters") or {}).get("disable") or [])


def parse_golangci_json(repo: str, output: str) -> list[LintFinding]:
    report = json.loads(output or "{}")
    return [
        LintFinding(
            repo=repo,
            path=issue["Pos"]["Filename"].replace("\\", "/"),
            line=issue["Pos"]["Line"],
            linter=issue["FromLinter"],
            text=issue["Text"],
            source=" ".join(line.strip() for line in issue.get("SourceLines") or []),
        )
        for issue in report.get("Issues") or []
    ]


def run_disabled_linters(
    repo: str, root: Path, linters: list[str]
) -> list[LintFinding]:
    """Every finding the disabled linters would report in *root*, from one run."""
    command = ["golangci-lint", "run", "--enable-only", ",".join(linters)]
    command += ["--output.json.path", "stdout", "--show-stats=false"]
    command += ["--issues-exit-code", "0"]
    command += ["--max-issues-per-linter", "0", "--max-same-issues", "0", "./..."]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        error = result.stderr.strip()[-500:]
        raise RuntimeError(f"golangci-lint failed in `{repo}`: {error}")
    return parse_golangci_json(repo, result.stdout)


def disabled_observations(
    linters: set[str], found: list[LintFinding], links: dict[str, str]
) -> list[Observation]:
    by_linter = defaultdict(list)
    for f in found:
        by_linter[f.linter].append(f)
    observations = []
    for linter in sorted(linters):
        group = by_linter.get(linter, [])
        ids = evidence_ids([(f.repo, f.path, f.linter, f.text) for f in group])
        lines = {
            eid: f"{where(links, f.repo, f.path, f.line)}: {f.text}"
            for eid, f in zip(ids, group)
        }
        sample = "\n".join(
            f"- {where(links, f.repo, f.path, f.line)}: {f.text}"
            + (f"\n  ```go\n  {f.source}\n  ```" if f.source else "")
            for f in group[:SAMPLE_SIZE]
        )
        findings = f"{len(group)} finding{'' if len(group) == 1 else 's'}"
        statement = (
            f"`{linter}` is off in the org's lint set. Switched on across the org's Go "
            f"repos, it would report {findings}. If these look real, it is cheap to "
            "switch on.\n\n"
            f"**Suggested change:** remove `{linter}` from the disable list in the "
            f"org's `.golangci.yml` ([lint set]({LINT_SET})) and fix or suppress what "
            "it finds, unless the reason it's off still holds.\n\n"
            f"Sample:\n\n{sample}"
        )
        observations.append(
            Observation(
                key=f"lint:{linter}:disabled",
                title=f"{linter} is off and would report {findings}",
                flagged=1 <= len(group) <= FEW_FINDINGS,
                count=len(group),
                statement=statement,
                evidence=lines,
            )
        )
    return observations


# ---------------------------------------------------------------------------
# Readability findings
# ---------------------------------------------------------------------------

UNCITED = "uncited"  # the point of a finding that names none
UNAVAILABLE: dict = {}  # a compare GitHub couldn't produce

POINT = re.compile(r"^\s*\[([a-z]+/[a-z-]+)\]")
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


@dataclass
class Finding:
    repo: str
    pr: int
    url: str
    point: str
    outcome: str  # "accepted", "rejected" or "unknown"
    merged: date
    replies: list[str] = field(default_factory=list)
    comment_id: int = 0


def parse_point(body: str) -> str | None:
    """The style-guide point a finding cites, from its leading `[go/errors]`."""
    match = POINT.match(body or "")
    return match.group(1) if match else None


def touched_old_lines(patch: str) -> set[int]:
    """The lines of the old file a unified diff changes.

    A removed or replaced line counts, and so do the two old lines either side of a pure
    insertion: a comment asking for a line to be explained is answered by a line added
    next to it.
    """
    touched: set[int] = set()
    old = None
    replacing = False  # the added lines follow removed ones, so they replace them
    for text in patch.splitlines():
        hunk = HUNK.match(text)
        if hunk:
            old, replacing = int(hunk.group(1)), False
        elif old is None or text.startswith("\\"):
            continue
        elif text.startswith("-"):
            touched.add(old)
            old, replacing = old + 1, True
        elif text.startswith("+"):
            if not replacing:
                touched.update((old - 1, old))
        else:
            old, replacing = old + 1, False
    return touched


def outcome(comment: dict, compare: dict | None) -> str:
    """Whether the lines *comment* is on changed between its commit and the merged head.

    *compare* is GitHub's compare of the comment's commit with the pull request's head,
    or None when they are the same commit.
    """
    if compare is None:
        return "rejected"
    if comment.get("side") == "LEFT" or not comment.get("original_line"):
        return "unknown"
    for changed in compare.get("files") or []:
        if changed.get("filename") != comment["path"]:
            continue
        if changed.get("status") in ("removed", "renamed"):
            return "accepted"
        if "patch" not in changed:  # GitHub leaves out a patch that is too large
            return "unknown"
        end = comment["original_line"]
        start = comment.get("original_start_line") or end
        touched = touched_old_lines(changed["patch"])
        return "accepted" if touched & set(range(start, end + 1)) else "rejected"
    return "rejected"


def point_link(point: str) -> str:
    language, heading = point.split("/", 1)
    page = "README.md" if language == "general" else f"{language}.md"
    anchor = "" if heading == "google" else f"#{heading}"
    return f"[`{point}`]({GUIDE}/{page}{anchor})"


def finding_line(f: Finding) -> str:
    replies = "".join(f"\n  > {reply}" for reply in f.replies)
    return f"[{f.repo}#{f.pr}]({f.url}): {f.outcome}{replies}"


def style_observation(
    point: str, group: list[Finding], kind: str, flagged: bool, case: str
) -> Observation:
    """The case that *point* is *kind* ("accepted" or "rejected") too often."""
    chosen = [f for f in group if f.outcome == kind]
    ids = evidence_ids([(str(f.comment_id),) for f in chosen])
    lines = dict(zip(ids, map(finding_line, chosen)))
    statement = (
        f"The readability review cited {point_link(point)} {len(group)} times on "
        f"merged pull requests, and {len(chosen)} of those findings were {kind}. "
        f"{case}\n\n" + "\n".join(f"- {line}" for line in lines.values())
    )
    return Observation(
        key=f"style:{point}:{kind}",
        title=f"{point} {kind} {len(chosen)} of {len(group)} times",
        flagged=flagged,
        count=len(chosen),
        statement=statement,
        evidence=lines,
    )


REJECTED_CASE = (
    "A point authors mostly turn down is either worded so the reviewer misapplies it, "
    "or not one the org holds to.\n\n"
    "**Suggested change:** reword the point so it says what the org does want, or "
    "remove it from the style guide."
)
ACCEPTED_CASE = (
    "If what it asks for is mechanical, a linter could ask instead.\n\n"
    "**Suggested change:** switch on a linter, or a `revive` or `gocritic` rule, that "
    "checks this, or write the configuration for one that needs it (a recurring "
    "\"don't import X\" is `depguard`'s job). Then remove the point from the style "
    "guide."
)


def style_observations(found: list[Finding]) -> list[Observation]:
    """Two cases per point: it is rejected too often, or accepted often enough to lint.

    A finding whose outcome is unknown, or that cites no point, counts towards neither.
    """
    by_point = defaultdict(list)
    for f in found:
        if f.outcome != "unknown" and f.point != UNCITED:
            by_point[f.point].append(f)
    observations = []
    for point, group in sorted(by_point.items()):
        judged = len(group) >= STYLE_MIN_FINDINGS
        rejected = sum(f.outcome == "rejected" for f in group) / len(group)
        accepted = 1 - rejected
        observations += [
            style_observation(
                point,
                group,
                "rejected",
                judged and rejected > STYLE_REJECTED_FLAG,
                REJECTED_CASE,
            ),
            style_observation(
                point,
                group,
                "accepted",
                judged and accepted >= STYLE_ACCEPTED_FLAG,
                ACCEPTED_CASE,
            ),
        ]
    return observations


# ---------------------------------------------------------------------------
# GitHub, through `gh`
# ---------------------------------------------------------------------------


def gh(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], input=stdin, check=True, capture_output=True, text=True
    )
    return result.stdout


def gh_api_lines(path: str, jq: str, *args: str) -> list[dict]:
    """A paginated `gh api` call, its results one JSON value per line via *jq*."""
    out = gh("api", path, "--paginate", "--jq", jq, *args)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def list_repos(org: str) -> list[str]:
    out = gh("repo", "list", org, "--limit", "500", "--no-archived", "--json",
             "nameWithOwner", "--jq", ".[].nameWithOwner")  # fmt: skip
    return sorted(out.split())


def clone(repo: str, into: Path) -> tuple[Path, str]:
    """A shallow clone of *repo*, and the base URL of its files at the cloned commit."""
    path = into / repo.split("/", 1)[1]
    gh("repo", "clone", repo, str(path), "--", "--depth", "1", "--quiet")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return path, f"https://github.com/{repo}/blob/{sha}"


def merged_prs(org: str, since: str) -> list[tuple[str, int]]:
    query = f"q=org:{org} is:pr is:merged merged:>={since}"
    items = gh_api_lines(
        "search/issues",
        ".items[] | {url: .repository_url, number}",
        "-X",
        "GET",
        "-f",
        query,
    )
    return [("/".join(item["url"].split("/")[-2:]), item["number"]) for item in items]


def compare_commits(repo: str, base: str, head: str) -> dict | None:
    if base == head:
        return None
    try:
        return json.loads(gh("api", f"repos/{repo}/compare/{base}...{head}"))
    except subprocess.CalledProcessError:  # the commit was force-pushed away
        return UNAVAILABLE


def pr_findings(repo: str, number: int) -> list[Finding]:
    """The readability review's findings on one merged pull request, with outcomes."""
    pr = json.loads(gh("api", f"repos/{repo}/pulls/{number}"))
    head = pr["head"]["sha"]
    merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")).date()
    comments = gh_api_lines(f"repos/{repo}/pulls/{number}/comments", ".[]")
    replies = defaultdict(list)
    for c in comments:
        if c.get("in_reply_to_id") and c["user"]["type"] != "Bot":
            replies[c["in_reply_to_id"]].append(" ".join(c["body"].split()))
    compares: dict[str, dict | None] = {}
    found = []
    for c in comments:
        if c["user"]["login"] != REVIEWER or c.get("in_reply_to_id"):
            continue
        base = c["original_commit_id"]
        if base not in compares:
            compares[base] = compare_commits(repo, base, head)
        compare = compares[base]
        found.append(
            Finding(
                repo=repo,
                pr=number,
                url=c["html_url"],
                point=parse_point(c["body"]) or UNCITED,
                outcome="unknown" if compare is UNAVAILABLE else outcome(c, compare),
                merged=merged,
                replies=replies[c["id"]],
                comment_id=c["id"],
            )
        )
    return found


def list_issues(repo: str) -> list[Issue]:
    out = gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "all",
             "--limit", "1000", "--json", "number,state,body")  # fmt: skip
    parsed = (parse_issue(r["number"], r["state"], r["body"]) for r in json.loads(out))
    issues = [issue for issue in parsed if issue]
    for issue in issues:
        if not issue.open:
            comments = gh_api_lines(f"repos/{repo}/issues/{issue.number}/comments",
                                    ".[].body")  # fmt: skip
            issue.stronger_noted = any(STRONGER_MARKER in body for body in comments)
    return issues


def ensure_label(repo: str) -> None:
    try:
        gh("api", f"repos/{repo}/labels/{LABEL}")
    except subprocess.CalledProcessError:
        description = "A case for changing the lint set or style guide, from the report"
        gh("label", "create", LABEL, "--repo", repo, "--color", "c5def5",
           "--description", description)  # fmt: skip


def carry_out(repo: str, action: Action, issues: dict[int, Issue]) -> str:
    obs = action.observation
    if action.kind == "create":
        url = gh("issue", "create", "--repo", repo, "--title", obs.title, "--label",
                 LABEL, "--body-file", "-", stdin=issue_body(obs))  # fmt: skip
        return f"opened {url.strip()}: {obs.title}"
    number = str(action.issue)
    if action.kind == "update":
        gh("issue", "comment", number, "--repo", repo, "--body-file", "-",
           stdin=update_comment(action))  # fmt: skip
        gh("issue", "edit", number, "--repo", repo, "--title", obs.title,
           "--body-file", "-", stdin=issue_body(obs))  # fmt: skip
        return f"updated #{number}: {obs.title}"
    was = issues[action.issue].count
    gh("issue", "comment", number, "--repo", repo, "--body-file", "-",
       stdin=stronger_comment(action, was))  # fmt: skip
    return f"noted on closed #{number}: {obs.title}"


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------


def summary(
    observations: list[Observation],
    week: list[Finding],
    results: list[str],
    notes: list[str],
) -> str:
    """Every week's numbers, flagged or not, for the workflow run's summary."""
    lines = ["# Calibration report", ""]
    sections = [
        ("Lint suppressions", ":suppressed", "Suppressions"),
        ("Disabled linters", ":disabled", "Findings if switched on"),
    ]
    for heading, suffix, column in sections:
        lines += [
            f"## {heading}",
            "",
            f"| Linter | {column} | Flagged |",
            "|---|---|---|",
        ]
        for o in observations:
            if o.key.endswith(suffix):
                flagged = "yes" if o.flagged else ""
                lines.append(f"| `{o.key.split(':')[1]}` | {o.count} | {flagged} |")
        lines.append("")
    lines += ["## Readability findings on pull requests merged this week", ""]
    lines += ["| Point | Accepted | Rejected | Unknown |", "|---|---|---|---|"]
    counts = defaultdict(lambda: defaultdict(int))
    for f in week:
        counts[f.point][f.outcome] += 1
    for point, n in sorted(counts.items()):
        lines.append(
            f"| `{point}` | {n['accepted']} | {n['rejected']} | {n['unknown']} |"
        )
    lines += ["", "## Issues", ""]
    lines += [f"- {r}" for r in results] or ["Nothing new this week."]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--org", required=True)
    parser.add_argument(
        "--issues-repo",
        required=True,
        metavar="owner/repo",
        help="Where the calibration issues live.",
    )
    parser.add_argument(
        "--since",
        default=REVIEW_START,
        metavar="YYYY-MM-DD",
        help="Count readability findings on pull requests merged since this date.",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--summary-file", help="Append the run summary to this file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be posted instead of posting it.",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Don't run the disabled linters (no go or golangci-lint here).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    opts = parse_args(argv)
    notes: list[str] = []
    suppressions: list[Suppression] = []
    lint_findings: list[LintFinding] = []
    off: set[str] = set()
    links: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp:
        for repo in list_repos(opts.org):
            path, links[repo] = clone(repo, Path(tmp))
            if not (path / "go.mod").exists():
                continue
            print(f"{repo}: Go")
            suppressions += find_suppressions(repo, path)
            if opts.skip_lint:
                continue
            config = path / ".golangci.yml"
            if not config.exists():
                notes.append(
                    f"`{repo}` has no `.golangci.yml`, so nothing was run in it."
                )
                continue
            linters = disabled_linters(config.read_text(encoding="utf-8"))
            if not linters:
                notes.append(f"`{repo}`'s `.golangci.yml` disables no linter by name.")
                continue
            off.update(linters)
            try:
                lint_findings += run_disabled_linters(repo, path, linters)
            except RuntimeError as exc:
                notes.append(str(exc))

    findings: list[Finding] = []
    for repo, number in merged_prs(opts.org, opts.since):
        findings += pr_findings(repo, number)
    week = [f for f in findings if f.merged > opts.today - timedelta(days=7)]
    unknown = sum(f.outcome == "unknown" for f in findings)
    if unknown:
        notes.append(f"{unknown} readability finding(s) couldn't be matched to the "
                     "merged code, and aren't counted.")  # fmt: skip
    uncited = sum(f.point == UNCITED for f in findings)
    if uncited:
        notes.append(f"{uncited} readability finding(s) cite no style-guide point.")

    observations = (
        suppression_observations(suppressions, links)
        + disabled_observations(off, lint_findings, links)
        + style_observations(findings)
    )
    issues = list_issues(opts.issues_repo)
    actions = plan(observations, issues)

    results = []
    if opts.dry_run:
        for action in actions:
            target = f" #{action.issue}" if action.issue else ""
            results.append(f"would {action.kind}{target}: {action.observation.title}")
    else:
        if actions:
            ensure_label(opts.issues_repo)
        by_number = {issue.number: issue for issue in issues}
        for action in actions:
            results.append(carry_out(opts.issues_repo, action, by_number))

    report = summary(observations, week, results, notes)
    print(report)
    if opts.summary_file:
        with open(opts.summary_file, "a", encoding="utf-8") as f:
            f.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
