"""Static AST scan for SKIP-returning paths in app.viz.

Walks the AST of app/viz/decision.py and any module that constructs
Decision.skip(...) or returns ui=None. Writes a markdown report to
logs/viz_audit.md and returns a summary object.

Used by the regression ratchet test (tests/viz/test_audit_ratchet.py).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    REPO_ROOT / "app" / "viz" / "decision.py",
    REPO_ROOT / "app" / "viz" / "build.py",
    REPO_ROOT / "app" / "viz" / "mcp_output.py",
    REPO_ROOT / "app" / "main.py",
]


@dataclass
class SkipSite:
    file: str
    line: int
    snippet: str


@dataclass
class AuditResult:
    skip_sites: list[SkipSite] = field(default_factory=list)
    no_data_sites: list[SkipSite] = field(default_factory=list)
    manual_envelope_sites: list[SkipSite] = field(default_factory=list)

    @property
    def total_unguarded(self) -> int:
        return (
            len(self.skip_sites)
            + len(self.no_data_sites)
            + len(self.manual_envelope_sites)
        )


def _scan_file(
    path: Path,
) -> tuple[list[SkipSite], list[SkipSite], list[SkipSite]]:
    skip_sites: list[SkipSite] = []
    no_data_sites: list[SkipSite] = []
    manual_envelope_sites: list[SkipSite] = []
    if not path.exists():
        return skip_sites, no_data_sites, manual_envelope_sites

    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        # Decision.skip(...) calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "skip" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "Decision":
                    skip_sites.append(SkipSite(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=node.lineno,
                        snippet=lines[node.lineno - 1].strip(),
                    ))
        # `no_data": True` literal dict patterns
        if isinstance(node, ast.Constant) and node.value == "no_data":
            no_data_sites.append(SkipSite(
                file=str(path.relative_to(REPO_ROOT)),
                line=node.lineno,
                snippet=lines[node.lineno - 1].strip(),
            ))
        # Manual envelope = {...} literal without "ui" key
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "envelope":
                    value = node.value
                    if isinstance(value, ast.Dict):
                        keys = [
                            k.value
                            for k in value.keys
                            if isinstance(k, ast.Constant)
                        ]
                        if "ui" not in keys:
                            manual_envelope_sites.append(SkipSite(
                                file=str(path.relative_to(REPO_ROOT)),
                                line=node.lineno,
                                snippet=lines[node.lineno - 1].strip(),
                            ))

    return skip_sites, no_data_sites, manual_envelope_sites


def run_audit() -> AuditResult:
    result = AuditResult()
    for path in TARGETS:
        skips, no_datas, manual_envelopes = _scan_file(path)
        result.skip_sites.extend(skips)
        result.no_data_sites.extend(no_datas)
        result.manual_envelope_sites.extend(manual_envelopes)
    return result


def write_report(result: AuditResult, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Visualization SKIP Path Audit",
        "",
        f"Total unguarded sites: **{result.total_unguarded}**",
        "",
        "## Decision.skip() sites",
        "",
    ]
    if not result.skip_sites:
        lines.append("_(none)_")
    for s in result.skip_sites:
        lines.append(f"- `{s.file}:{s.line}` — `{s.snippet}`")
    lines.append("")
    lines.append("## `no_data` literal sites")
    lines.append("")
    if not result.no_data_sites:
        lines.append("_(none)_")
    for s in result.no_data_sites:
        lines.append(f"- `{s.file}:{s.line}` — `{s.snippet}`")
    lines.append("")
    lines.append("## Manual envelope dict sites (missing `ui` key)")
    lines.append("")
    if not result.manual_envelope_sites:
        lines.append("_(none)_")
    for s in result.manual_envelope_sites:
        lines.append(f"- `{s.file}:{s.line}` — `{s.snippet}`")
    out.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    result = run_audit()
    write_report(result, REPO_ROOT / "logs" / "viz_audit.md")
    print(
        f"Audit complete: {result.total_unguarded} unguarded sites "
        f"({len(result.skip_sites)} skip + "
        f"{len(result.no_data_sites)} no_data + "
        f"{len(result.manual_envelope_sites)} manual_envelope)"
    )
    print("Report: logs/viz_audit.md")
