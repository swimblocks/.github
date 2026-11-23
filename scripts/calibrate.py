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
LISTED = 40  # evidence lines an issue body or comment lists before "and N more"
COMPARE_FILES = 300  # GitHub's compare lists no more files than this

REVIEWER = "claude[bot]"  # the Claude GitHub App, which posts the review's findings
REVIEW_START = "2026-11-23"  # the first day the readability review ran
LABEL = "calibration"

GUIDE = "https://github.com/swimblocks/.github/blob/main/docs/styleguide"
LINT_SET = (
    "https://github.com/swimblocks/.github/blob/main/CONTRIBUTING.md#quality-gates"
)

KEY_MARKER = re.compile(r"<!-- calibration-key: (\S+) -->")
STATE_MARKER = re.compile(r"<!-- calibration-state: (\{.*?\}) -->")


# ---------------------------------------------------------------------------
# Observations, and what to do about each
# ---------------------------------------------------------------------------


@dataclass
class Observation:
    """One case for changing the lint set or the style guide, as it stands this week."""

    key: str
    title: str
    flagged: bool
    # How strong the case is, for the run summary.
    count: int
    # The issue body: the observation, its numbers, the suggested change.
    statement: str
    # Evidence id -> one markdown line describing it.
    evidence: dict[str, str] = field(default_factory=dict)
    # Some of the evidence couldn't be gathered, so the case isn't judged this week.
    partial: bool = False


@dataclass
class Issue:
    number: int
    open: bool
    key: str
    seen: set[str]


@dataclass
class Action:
    kind: str  # "create", "update" or "reopen"
    observation: Observation
    issue: int | None = None
    new_evidence: list[str] = field(default_factory=list)
    # Evidence the issue has already listed, kept when it rewrites the issue.
    seen: set[str] = field(default_factory=set)


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


def quoted(text: str) -> str:
    """*text*, written by someone else, made safe to quote in an issue.

    An `@name` in it would notify that person, and an HTML comment could pass for one of
    the issue's hidden markers.
    """
    return text.replace("@", "@\u2060").replace("<", "&lt;")


def listed(lines: list[str]) -> str:
    """A markdown list of *lines*, cut short so an issue stays within GitHub's limit."""
    shown = "\n".join(f"- {line}" for line in lines[:LISTED])
    more = len(lines) - LISTED
    return shown + (f"\n- and {more} more" if more > 0 else "")


def issue_body(obs: Observation, seen: set[str] = frozenset()) -> str:
    """The issue for *obs*, its hidden state listing this week's evidence and *seen*.

    Evidence that goes away and comes back has been listed before, so it isn't new.
    """
    state = {"seen": sorted(set(obs.evidence) | set(seen))}
    return (
        f"{obs.statement}\n\n"
        f"<!-- calibration-key: {obs.key} -->\n"
        f"<!-- calibration-state: {json.dumps(state, separators=(',', ':'))} -->\n"
    )


def parse_issue(number: int, state: str, body: str) -> Issue | None:
    """The calibration issue behind *body*, or None if it carries no key.

    The markers are read from the end of the body, where issue_body() puts them, so
    quoted text above them can't pass for them.
    """
    keys = KEY_MARKER.findall(body or "")
    if not keys:
        return None
    saved = STATE_MARKER.findall(body)
    data = json.loads(saved[-1]) if saved else {}
    return Issue(
        number=number,
        open=state.upper() == "OPEN",
        key=keys[-1],
        seen=set(data.get("seen", [])),
    )


def plan(observations: list[Observation], issues: list[Issue]) -> list[Action]:
    """What to post this week.

    A flagged observation with no issue gets one. An issue whose observation has new
    evidence gets a comment saying what's new and a rewritten body, and is reopened if
    it was closed: closing decides the case as it stood, not as it grows. A week with
    nothing new touches nothing.
    """
    by_key = {issue.key: issue for issue in issues}
    actions = []
    for obs in observations:
        issue = by_key.get(obs.key)
        if issue is None:
            if obs.flagged:
                actions.append(Action("create", obs))
            continue
        new = [line for eid, line in obs.evidence.items() if eid not in issue.seen]
        if new:
            kind = "update" if issue.open else "reopen"
            actions.append(Action(kind, obs, issue.number, new, issue.seen))
    return actions


def update_comment(action: Action) -> str:
    if action.kind == "reopen":
        opening = "This case has come back since the issue was closed:"
    else:
        opening = "New since the last report:"
    return (
        f"{opening}\n\n{listed(action.new_evidence)}\n\n"
        "The description now gives the case as it stands."
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


def reasons(group: list[Suppression]) -> list[str]:
    return [quoted(s.reason) if s.reason else "*(none)*" for s in group]


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
            eid: f"{where(links, s.repo, s.path, s.line)}: {why}"
            for eid, s, why in zip(ids, group, reasons(group))
        }
        statement = (
            f"`{linter}` is suppressed {len(group)} times across the org's Go repos. "
            "A linter suppressed this often is either set up wrong for how we write "
            "Go, or wrong for us; the reasons below say which.\n\n"
            f"**Suggested change:** configure `{linter}` in the org's `.golangci.yml` "
            f"([lint set]({LINT_SET})) so these stop firing, or move it to the "
            "disable list with the reason it doesn't fit.\n\n"
            + listed(list(lines.values()))
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
    command += ["--issues-exit-code", "0", "--uniq-by-line=false"]
    command += ["--max-issues-per-linter", "0", "--max-same-issues", "0", "./..."]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        error = result.stderr.strip()[-500:]
        raise RuntimeError(f"golangci-lint failed in `{repo}`: {error}")
    return parse_golangci_json(repo, result.stdout)


def disabled_observations(
    linters: set[str],
    found: list[LintFinding],
    links: dict[str, str],
    partial: set[str] = frozenset(),
) -> list[Observation]:
    """A case per disabled linter: switched on, it would report only a few findings.

    A linter in *partial* failed to run in some repo, so its count leaves that repo out
    and its case isn't flagged.
    """
    by_linter = defaultdict(list)
    for f in found:
        by_linter[f.linter].append(f)
    observations = []
    for linter in sorted(linters):
        group = by_linter.get(linter, [])
        ids = evidence_ids([(f.repo, f.path, f.linter, f.text) for f in group])
        lines = {
            eid: f"{where(links, f.repo, f.path, f.line)}: {quoted(f.text)}"
            for eid, f in zip(ids, group)
        }
        sample = "\n".join(
            f"- {where(links, f.repo, f.path, f.line)}: {quoted(f.text)}"
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
        if linter in partial:
            statement = (
                "**Incomplete:** the lint run failed in at least one repo, so these "
                "counts leave it out.\n\n" + statement
            )
        observations.append(
            Observation(
                key=f"lint:{linter}:disabled",
                title=f"{linter} is off and would report {findings}",
                flagged=linter not in partial and 1 <= len(group) <= FEW_FINDINGS,
                count=len(group),
                statement=statement,
                evidence=lines,
                partial=linter in partial,
            )
        )
    return observations


# ---------------------------------------------------------------------------
# Readability findings
# ---------------------------------------------------------------------------

UNCITED = "uncited"  # the point of a finding that names none
UNAVAILABLE: dict = {}  # a compare GitHub couldn't produce

POINT = re.compile(r"^\s*\[([a-z]+/[a-z-]+)\]")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


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
            # `-N,0` is an insertion after old line N; any other hunk starts at N.
            old = int(hunk.group(1)) + (hunk.group(2) == "0")
            replacing = False
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
    or None when they are the same commit. It can only be trusted when the head is
    ahead of the comment's commit; after a rebase it diffs from an older merge base,
    whose line numbers aren't the comment's.
    """
    if comment.get("side") == "LEFT" or not comment.get("original_line"):
        return "unknown"
    if compare is None:
        return "rejected"
    if compare.get("status") != "ahead":
        return "unknown"
    files = compare.get("files") or []
    for changed in files:
        names = (changed.get("filename"), changed.get("previous_filename"))
        if comment["path"] not in names:
            continue
        if changed.get("status") == "removed":
            return "accepted"
        if "patch" not in changed:
            # A pure rename has no patch, and changes no line; a large diff has none.
            return "rejected" if changed.get("changes") == 0 else "unknown"
        end = comment["original_line"]
        start = comment.get("original_start_line") or end
        touched = touched_old_lines(changed["patch"])
        return "accepted" if touched & set(range(start, end + 1)) else "rejected"
    # Not in the list: unchanged, unless the list was cut off.
    return "unknown" if len(files) >= COMPARE_FILES else "rejected"


def point_link(point: str) -> str:
    language, heading = point.split("/", 1)
    page = "README.md" if language == "general" else f"{language}.md"
    anchor = "" if heading == "google" else f"#{heading}"
    return f"[`{point}`]({GUIDE}/{page}{anchor})"


def finding_line(f: Finding) -> str:
    replies = "".join(f"\n  > {quoted(reply)}" for reply in f.replies)
    return f"[{f.repo}#{f.pr}]({f.url}): {f.outcome}{replies}"


def style_observation(
    point: str, group: list[Finding], kind: str, flagged: bool, case: str
) -> Observation:
    """The case that *point* is *kind* ("accepted" or "rejected") too often.

    Every finding on the point is evidence, whatever its outcome, since each one moves
    the share the case rests on.
    """
    chosen = [f for f in group if f.outcome == kind]
    ids = evidence_ids([(str(f.comment_id),) for f in group])
    lines = dict(zip(ids, map(finding_line, group)))
    statement = (
        f"The readability review cited {point_link(point)} {len(group)} times on "
        f"merged pull requests, and {len(chosen)} of those findings were {kind}. "
        f"{case}\n\n" + listed(list(lines.values()))
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
    return [issue for issue in parsed if issue]


def ensure_label(repo: str) -> None:
    try:
        gh("api", f"repos/{repo}/labels/{LABEL}")
    except subprocess.CalledProcessError:
        description = "A case for changing the lint set or style guide, from the report"
        gh("label", "create", LABEL, "--repo", repo, "--color", "c5def5",
           "--description", description)  # fmt: skip


def carry_out(repo: str, action: Action) -> str:
    obs = action.observation
    if action.kind == "create":
        url = gh("issue", "create", "--repo", repo, "--title", obs.title, "--label",
                 LABEL, "--body-file", "-", stdin=issue_body(obs))  # fmt: skip
        return f"opened {url.strip()}: {obs.title}"
    # The body holds what has been reported, so it is written last: if the comment or
    # the reopen fails, next week finds the same evidence new and tries again.
    number = str(action.issue)
    gh("issue", "comment", number, "--repo", repo, "--body-file", "-",
       stdin=update_comment(action))  # fmt: skip
    if action.kind == "reopen":
        gh("issue", "reopen", number, "--repo", repo)
    gh("issue", "edit", number, "--repo", repo, "--title", obs.title,
       "--body-file", "-", stdin=issue_body(obs, action.seen))  # fmt: skip
    verb = "reopened" if action.kind == "reopen" else "updated"
    return f"{verb} #{number}: {obs.title}"


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------


def summary(
    observations: list[Observation],
    week: list[Finding],
    results: list[str],
    notes: list[str],
    failures: list[str] = (),
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
                flagged = "incomplete" if o.partial else "yes" if o.flagged else ""
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
    if failures:
        lines += ["", "## Failures", ""] + [f"- {f}" for f in failures]
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


@dataclass
class Run:
    """What one run found and did, kept so the summary has it whatever goes wrong."""

    observations: list[Observation] = field(default_factory=list)
    week: list[Finding] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Anything that left the report incomplete or a post undone; the run fails on any.
    failures: list[str] = field(default_factory=list)


def error_text(exc: Exception) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        return (exc.stderr or str(exc)).strip()[-300:]
    return str(exc)[-300:]


def collect(opts: argparse.Namespace, run: Run) -> None:
    """Gather the week's evidence into *run*'s observations."""
    suppressions: list[Suppression] = []
    lint_findings: list[LintFinding] = []
    off: set[str] = set()
    partial: set[str] = set()
    links: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp:
        for repo in list_repos(opts.org):
            try:
                path, links[repo] = clone(repo, Path(tmp))
            except subprocess.CalledProcessError as exc:
                run.failures.append(
                    f"`{repo}` couldn't be cloned, so it was left out: "
                    f"{error_text(exc)}"
                )
                continue
            if not (path / "go.mod").exists():
                continue
            print(f"{repo}: Go")
            suppressions += find_suppressions(repo, path)
            if opts.skip_lint:
                continue
            config = path / ".golangci.yml"
            if not config.exists():
                run.notes.append(
                    f"`{repo}` has no `.golangci.yml`, so nothing was run in it."
                )
                continue
            linters = disabled_linters(config.read_text(encoding="utf-8"))
            if not linters:
                run.notes.append(
                    f"`{repo}`'s `.golangci.yml` disables no linter by name."
                )
                continue
            off.update(linters)
            try:
                lint_findings += run_disabled_linters(repo, path, linters)
            except RuntimeError as exc:
                partial.update(linters)
                run.failures.append(str(exc))

    findings: list[Finding] = []
    for repo, number in merged_prs(opts.org, opts.since):
        try:
            findings += pr_findings(repo, number)
        except subprocess.CalledProcessError as exc:
            run.failures.append(
                f"{repo}#{number}'s review findings couldn't be read, so they aren't "
                f"counted: {error_text(exc)}"
            )
    run.week = [f for f in findings if f.merged > opts.today - timedelta(days=7)]
    unknown = sum(f.outcome == "unknown" for f in findings)
    if unknown:
        run.notes.append(f"{unknown} readability finding(s) couldn't be matched to "
                         "the merged code, and aren't counted.")  # fmt: skip
    uncited = sum(f.point == UNCITED for f in findings)
    if uncited:
        run.notes.append(f"{uncited} readability finding(s) cite no style-guide point.")

    run.observations = (
        suppression_observations(suppressions, links)
        + disabled_observations(off, lint_findings, links, partial)
        + style_observations(findings)
    )


def post(opts: argparse.Namespace, run: Run) -> None:
    """Open, update or reopen the issues *run*'s observations call for."""
    try:
        issues = list_issues(opts.issues_repo)
    except subprocess.CalledProcessError as exc:
        # Without them, every case would look new and be opened again.
        run.failures.append(
            f"The calibration issues couldn't be listed, so nothing was posted: "
            f"{error_text(exc)}"
        )
        return
    actions = plan(run.observations, issues)
    if opts.dry_run:
        for action in actions:
            target = f" #{action.issue}" if action.issue else ""
            run.results.append(
                f"would {action.kind}{target}: {action.observation.title}"
            )
        return
    if actions:
        try:
            ensure_label(opts.issues_repo)
        except subprocess.CalledProcessError as exc:
            run.failures.append(
                f"The `{LABEL}` label couldn't be created, so nothing was posted: "
                f"{error_text(exc)}"
            )
            return
    # One post GitHub refuses mustn't cost the rest, or the summary.
    for action in actions:
        try:
            run.results.append(carry_out(opts.issues_repo, action))
        except subprocess.CalledProcessError as exc:
            title = action.observation.title
            run.failures.append(f"Couldn't {action.kind} {title}: {error_text(exc)}")


def main(argv: list[str]) -> int:
    opts = parse_args(argv)
    run = Run()
    try:
        collect(opts, run)
        post(opts, run)
    except Exception as exc:  # whatever stopped it, the summary says so
        run.failures.append(f"The run stopped early: {error_text(exc)}")

    report = summary(run.observations, run.week, run.results, run.notes, run.failures)
    print(report)
    if opts.summary_file:
        with open(opts.summary_file, "a", encoding="utf-8") as f:
            f.write(report)
    return 1 if run.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
