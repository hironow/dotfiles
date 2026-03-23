"""Generate docs/changelogs.md from submodule git logs.

This script reads each submodule's recent git history and produces
a structured changelog in Japanese, matching the format of the
gold-standard docs/changelogs_gold.md.

Optimized by autoresearch experiment loop.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOGS_OUT = ROOT / "docs" / "changelogs.md"

PROTOCOL_PREFIX = "protocols/"
GCLOUD_PREFIX = "gcloud/"

DISPLAY_NAMES: dict[str, str] = {
    "protocols/A2A": "A2A (Agent-to-Agent)",
    "protocols/A2UI": "A2UI (Agent-to-User Interface)",
    "protocols/ACP": "ACP (Agentic Commerce Protocol)",
    "protocols/ADP": "ADP (Agent Data Protocol)",
    "protocols/AG-UI": "AG-UI (Agent-User Interaction Protocol)",
    "protocols/AgentSkills": "AgentSkills",
    "protocols/AP2": "AP2 (Agent Payments Protocol)",
    "protocols/MCP": "MCP (Model Context Protocol)",
    "protocols/MCP-Apps": "MCP-Apps",
    "protocols/MCP-UI": "MCP-UI",
    "protocols/OpenResponses": "OpenResponses",
    "protocols/UCP": "UCP (Universal Commerce Protocol)",
    "protocols/webmcp-tools": "webmcp-tools",
    "protocols/x402": "x402 (Internet Native Payments)",
    "gcloud/adk-python": "ADK Python",
    "gcloud/adk-go": "ADK Go",
    "gcloud/adk-js": "ADK JS",
    "gcloud/agent-starter-pack": "Agent Starter Pack",
    "gcloud/cloud-run-mcp": "Cloud Run MCP",
    "gcloud/gcloud-mcp": "gcloud-mcp",
    "gcloud/genai-toolbox": "GenAI Toolbox",
    "gcloud/gke-mcp": "GKE MCP",
    "gcloud/google-analytics-mcp": "Google Analytics MCP",
    "gcloud/mcp": "MCP (Google Cloud)",
    "gcloud/mcp-security": "MCP Security",
}

SKIP_SUBMODULES = {
    "emulator",
    "telemetry",
    "skills",
    "knowledge-work-plugins",
    "tools/tmux/plugins/tmux-resurrect",
}


def run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
    )
    return result.stdout.strip()


def get_submodule_paths() -> list[str]:
    output = run_git(["submodule", "status"])
    paths = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            path = parts[1]
            if path not in SKIP_SUBMODULES:
                paths.append(path)
    return sorted(paths)


def get_latest_tag(submodule_path: str) -> str | None:
    cwd = ROOT / submodule_path
    tag = run_git(["describe", "--tags", "--abbrev=0"], cwd=cwd)
    return tag if tag else None


def get_recent_commits(submodule_path: str, count: int = 50) -> list[dict[str, str]]:
    cwd = ROOT / submodule_path
    fmt = "%H|%s|%an|%ai"
    output = run_git(
        ["log", f"--pretty=format:{fmt}", f"-{count}"],
        cwd=cwd,
    )
    commits = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append(
                {
                    "hash": parts[0][:8],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3][:10],
                }
            )
    return commits


def classify_commit(subject: str) -> str:
    subject_lower = subject.lower()
    if subject_lower.startswith("feat"):
        return "feature"
    if subject_lower.startswith("fix"):
        return "fix"
    if subject_lower.startswith("breaking") or "!" in subject.split(":")[0]:
        return "breaking"
    if subject_lower.startswith(("chore", "ci", "build", "deps")):
        return "chore"
    if subject_lower.startswith(("doc", "readme")):
        return "docs"
    if subject_lower.startswith(("refactor", "perf")):
        return "refactor"
    if subject_lower.startswith("test"):
        return "test"
    return "other"


def extract_pr_number(subject: str) -> str | None:
    match = re.search(r"#(\d+)", subject)
    return match.group(0) if match else None


def summarize_commit(commit: dict[str, str]) -> str:
    subject = commit["subject"]
    pr = extract_pr_number(subject)
    cleaned = re.sub(
        r"^(feat|fix|chore|ci|build|docs?|refactor|perf|test)(\(.+?\))?[!]?:\s*",
        "",
        subject,
    )
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    pr_ref = f" ({pr})" if pr else ""
    return f"- **{cleaned}**{pr_ref}"


def generate_section(submodule_path: str) -> str:
    display_name = DISPLAY_NAMES.get(submodule_path, submodule_path.split("/")[-1])
    tag = get_latest_tag(submodule_path)
    commits = get_recent_commits(submodule_path)

    lines: list[str] = []
    lines.append(f"### {display_name}")
    lines.append("")

    if tag:
        lines.append(f"**現行バージョン**: {tag}")
        lines.append("")

    features: list[str] = []
    fixes: list[str] = []
    breaking: list[str] = []
    refactors: list[str] = []

    for commit in commits:
        subject = commit["subject"]
        # Enhanced breaking change detection
        subject_lower = subject.lower()
        is_breaking = (
            ("!" in subject.split(":")[0])
            or subject_lower.startswith("breaking")
            or "BREAKING CHANGE" in subject
            or ("breaking change" in subject_lower)
        )
        if is_breaking:
            breaking.append(summarize_commit(commit))
            continue
        cls = classify_commit(subject)
        entry = summarize_commit(commit)
        if cls == "feature":
            features.append(entry)
        elif cls == "fix":
            fixes.append(entry)
        elif cls in ("refactor",):
            refactors.append(entry)

    all_notable = features + fixes + refactors
    if all_notable:
        lines.append("#### 主要な変更点")
        lines.append("")
        for entry in all_notable[:20]:
            lines.append(entry)
        lines.append("")

    if breaking:
        lines.append("#### 破壊的変更")
        lines.append("")
        lines.append("| 変更 | 影響 |")
        lines.append("|------|------|")
        for entry in breaking:
            cleaned = entry.lstrip("- ").strip("*")
            lines.append(f"| {cleaned} | 要確認 |")
        lines.append("")

    cwd = ROOT / submodule_path
    remote_url = run_git(["config", "--get", "remote.origin.url"], cwd=cwd)
    if remote_url:
        if remote_url.startswith("git@github.com:"):
            remote_url = remote_url.replace("git@github.com:", "https://github.com/")
        remote_url = remote_url.removesuffix(".git")
        lines.append("#### 参考リンク")
        lines.append("")
        lines.append(f"- [{display_name}]({remote_url})")

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def collect_breaking_changes(submodule_path: str) -> list[tuple[str, str]]:
    """Collect breaking change commits from a submodule."""
    commits = get_recent_commits(submodule_path, count=50)
    display_name = DISPLAY_NAMES.get(submodule_path, submodule_path.split("/")[-1])
    breaking: list[tuple[str, str]] = []
    for commit in commits:
        subject = commit["subject"]
        subject_lower = subject.lower()
        is_breaking = (
            ("!" in subject.split(":")[0])
            or subject_lower.startswith("breaking")
            or "BREAKING CHANGE" in subject
            or ("breaking change" in subject_lower)
        )
        if is_breaking:
            cleaned = re.sub(
                r"^(feat|fix|chore|ci|build|docs?|refactor|perf|test)(\(.+?\))?[!]?:\s*",
                "",
                subject,
            )
            breaking.append((display_name, cleaned))
    return breaking


def collect_major_updates(submodule_path: str) -> list[str]:
    """Collect major version tags from a submodule."""
    cwd = ROOT / submodule_path
    display_name = DISPLAY_NAMES.get(submodule_path, submodule_path.split("/")[-1])
    tags_output = run_git(["tag", "--sort=-version:refname"], cwd=cwd)
    tags = [t.strip() for t in tags_output.splitlines() if t.strip()]
    major_tags = []
    for tag in tags[:5]:
        # Include tags that look like major/minor version bumps
        if re.match(r"v?\d+\.\d+", tag):
            major_tags.append(f"**{display_name} {tag}**")
            break
    return major_tags


def collect_security_updates(submodule_path: str) -> list[str]:
    """Collect security-related commits from a submodule."""
    commits = get_recent_commits(submodule_path, count=50)
    display_name = DISPLAY_NAMES.get(submodule_path, submodule_path.split("/")[-1])
    security: list[str] = []
    for commit in commits:
        subject = commit["subject"]
        subject_lower = subject.lower()
        if any(
            kw in subject_lower
            for kw in ("security", "auth", "cve", "vuln", "permission", "credential")
        ):
            cleaned = re.sub(
                r"^(feat|fix|chore|ci|build|docs?|refactor|perf|test)(\(.+?\))?[!]?:\s*",
                "",
                subject,
            )
            security.append(f"- **{display_name}**: {cleaned}")
    return security[:2]


def collect_integration_updates(submodule_path: str) -> list[str]:
    """Collect new integration commits from a submodule."""
    commits = get_recent_commits(submodule_path, count=50)
    display_name = DISPLAY_NAMES.get(submodule_path, submodule_path.split("/")[-1])
    integrations: list[str] = []
    for commit in commits:
        subject = commit["subject"]
        subject_lower = subject.lower()
        if any(
            kw in subject_lower
            for kw in ("integrat", "support", "add.*plugin", "new.*server", "new.*tool")
        ):
            cls = classify_commit(subject)
            if cls in ("feature",):
                cleaned = re.sub(
                    r"^(feat|fix|chore|ci|build|docs?|refactor|perf|test)(\(.+?\))?[!]?:\s*",
                    "",
                    subject,
                )
                pr = extract_pr_number(subject)
                pr_ref = f" ({pr})" if pr else ""
                integrations.append(f"- **{display_name}**: {cleaned}{pr_ref}")
    return integrations[:2]


def generate_notable_section(submodules: list[str]) -> str:
    """Generate the 注目ポイント (highlights) section."""
    lines: list[str] = []
    lines.append("## 注目ポイント")
    lines.append("")

    # Breaking changes summary table
    lines.append("### 破壊的変更一覧")
    lines.append("")
    lines.append("| 対象 | 変更内容 | 対応優先度 |")
    lines.append("|------|---------|-----------|")
    all_breaking: list[tuple[str, str]] = []
    for path in submodules:
        all_breaking.extend(collect_breaking_changes(path))
    if all_breaking:
        for display_name, change in all_breaking[:10]:
            lines.append(f"| **{display_name}** | {change} | 要確認 |")
    else:
        lines.append("| - | 破壊的変更なし | - |")
    lines.append("")

    # Major updates list
    lines.append("### メジャーアップデート")
    lines.append("")
    counter = 1
    for path in submodules:
        updates = collect_major_updates(path)
        for update in updates:
            lines.append(f"{counter}. {update}")
            counter += 1
    if counter == 1:
        lines.append("- メジャーアップデートなし")
    lines.append("")

    # New protocol integrations
    lines.append("### 新規プロトコル統合")
    lines.append("")
    all_integrations: list[str] = []
    for path in submodules:
        all_integrations.extend(collect_integration_updates(path))
    if all_integrations:
        for i, integration in enumerate(all_integrations[:10], 1):
            lines.append(f"{i}. {integration.lstrip('- ')}")
    else:
        lines.append("1. 新規統合なし")
    lines.append("")

    # Security updates
    lines.append("### セキュリティ更新")
    lines.append("")
    all_security: list[str] = []
    for path in submodules:
        all_security.extend(collect_security_updates(path))
    if all_security:
        for sec in all_security[:10]:
            lines.append(sec)
    else:
        lines.append("- セキュリティ関連の更新なし")
    lines.append("")

    return "\n".join(lines)


def generate_changelog() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    submodules = get_submodule_paths()

    protocols = [s for s in submodules if s.startswith(PROTOCOL_PREFIX)]
    gclouds = [s for s in submodules if s.startswith(GCLOUD_PREFIX)]

    lines: list[str] = []
    lines.append("# プロトコル変更ログ")
    lines.append("")
    lines.append(f"最終更新: {today}")
    lines.append("")
    lines.append("各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## プロトコル (Protocols)")
    lines.append("")
    for path in protocols:
        lines.append(generate_section(path))

    lines.append("## Google Cloud / ADK")
    lines.append("")
    for path in gclouds:
        lines.append(generate_section(path))

    lines.append(generate_notable_section(protocols + gclouds))

    return "\n".join(lines)


def main() -> None:
    content = generate_changelog()
    CHANGELOGS_OUT.write_text(content, encoding="utf-8")
    print(f"Generated changelog at {CHANGELOGS_OUT}")
    print(f"Total length: {len(content)} chars, {content.count(chr(10))} lines")


if __name__ == "__main__":
    main()
