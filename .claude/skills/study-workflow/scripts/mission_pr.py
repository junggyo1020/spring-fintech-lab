#!/usr/bin/env python3
"""현재 미션 브랜치로 PR을 만든다 (.github/pull_request_template.md와 같은 구조).

자동으로 채우는 것: 이슈 연결(Closes #N), 미션 문서 링크, 메타, 테스트 결과(개수·BUILD 결과),
시나리오 대응표(@DisplayName의 "#번호"로 매핑), 완료 기준 체크박스.
학습자가 쓰는 것: --notes 파일의 내용이 "학습자 메모" 절에 그대로 들어간다.

사용법 (레포 루트에서, 미션 브랜치 phase{P}/m{P}-{N}-{slug} 체크아웃 상태)
  python3 .claude/skills/study-workflow/scripts/mission_pr.py --notes /tmp/notes.md
  ... --dry-run        PR을 만들지 않고 본문만 출력 (push도 하지 않음)
  ... --skip-tests     테스트 실행 생략 (테스트 결과 절에 "실행 생략" 표시)
  ... --update         이미 열린 PR의 본문을 다시 생성한 내용으로 교체
"""
import argparse
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mission_doc import ROOT, find_issue, find_mission_doc, issue_title, parse, repo_slug, run  # noqa: E402

PLACEHOLDER_NOTES = """### 구현 요약
(작성 필요)

### 설계 결정과 이유
(작성 필요)

### 가장 자신 없는 부분
(작성 필요)

### TIL
(작성 필요)"""


def gradle_roots(info):
    changed = run(["git", "diff", "--name-only", "origin/main...HEAD"], check=False).splitlines()
    roots = set()
    for path in changed:
        p = (ROOT / path).parent
        while ROOT in p.parents or p == ROOT:
            if (p / "gradlew").exists() and "workspace" in p.parts:
                roots.add(p)
                break
            if p == ROOT:
                break
            p = p.parent
    if not roots and (info["workspace"] / "gradlew").exists():
        roots.add(info["workspace"])
    return sorted(roots)


def run_tests(root):
    r = run(["./gradlew", "test", "--console=plain"], check=False, cwd=root)
    total = fail = skip = 0
    for xml in (root / "build" / "test-results" / "test").glob("*.xml"):
        s = ET.parse(xml).getroot()
        total += int(s.get("tests", 0))
        fail += int(s.get("failures", 0)) + int(s.get("errors", 0))
        skip += int(s.get("skipped", 0))
    build = "BUILD SUCCESSFUL" if "BUILD SUCCESSFUL" in r else "BUILD FAILED"
    rel = root.relative_to(ROOT).as_posix()
    return f"| `{rel}` | {total - fail - skip} | {fail} | {skip} | {build} |"


def display_names(roots):
    names = []
    for root in roots:
        for f in root.rglob("src/test/**/*.java"):
            names += re.findall(r'@DisplayName\("((?:[^"\\]|\\.)*)"\)', f.read_text(encoding="utf-8"))
    return names


def scenario_table(info, roots):
    if info["level"] == "L3" or not info["scenarios"]:
        path = f"{info['workspace'].relative_to(ROOT).as_posix()}/docs/test-scenarios/{info['id']}.md"
        if (ROOT / path).exists():
            content = (ROOT / path).read_text(encoding="utf-8").strip()
            line = f"직접 작성한 시나리오 표: `{path}`\n\n<details><summary>시나리오 표 펼치기</summary>\n\n{content}\n\n</details>"
        else:
            line = f"직접 작성한 시나리오 표: `{path}` (파일 없음 — 작성 필요)"
        if not info["scenarios"]:
            return line
        head = line + "\n\n문서가 제공한 참조 시나리오:\n\n"
    else:
        head = ""
    names = display_names(roots)
    rows = ["| 시나리오 # | 테스트 메서드(@DisplayName) | 상태 |", "|---|---|---|"]
    for sid in info["scenarios"]:
        hits = [n for n in names if re.search(rf"#{re.escape(sid)}(?![0-9])", n)]
        rows.append(f"| {sid} | {'<br>'.join(hits) if hits else '-'} | {'✅' if hits else '❌ 없음'} |")
    return head + "\n".join(rows)


def build_body(info, slug, issue, tests, notes):
    url = f"https://github.com/{slug}/blob/main/{info['doc_rel']}"
    closes = f"Closes #{issue['number']}" if issue else "(연결할 이슈 없음 — mission_issue.py로 먼저 만든다)"
    criteria = "\n".join(info["criteria"]) or "- [ ] (미션 문서의 완료 기준을 확인)"
    return f"""## 미션
- 이슈: {closes}
- 미션 문서: {url}
- 가이드 수준 · 예상 시간 · 선행: {info['level']} · {info['hours']} · 선행: {info['prereq']}

## 테스트 결과
{tests}

## 테스트 시나리오 대응표
{scenario_table(info, gradle_roots(info))}

## 완료 기준
{criteria}

## 학습자 메모
{notes}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    m = re.match(r"phase(\d+)/m(\d+)-(\d+)-", branch)
    if not m:
        raise SystemExit(f"미션 브랜치가 아님: {branch} (형식: phase1/m1-1-money)")
    info = parse(find_mission_doc(f"M{m.group(2)}-{m.group(3)}"))
    slug = repo_slug()
    issue = find_issue(info["id"], state="open")

    roots = gradle_roots(info)
    if a.skip_tests or not roots:
        tests = "실행 생략" if a.skip_tests else "Gradle workspace를 찾지 못함"
    else:
        tests = "| workspace | 통과 | 실패 | 건너뜀 | 결과 |\n|---|---|---|---|---|\n" + "\n".join(run_tests(r) for r in roots)
    notes = Path(a.notes).read_text(encoding="utf-8").strip() if a.notes else PLACEHOLDER_NOTES
    text = build_body(info, slug, issue, tests, notes)

    if a.dry_run:
        print(f"===== {issue_title(info)}  ({branch} → main)\n{text}")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
    existing = json.loads(run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,url"]) or "[]")
    if existing:
        if a.update:
            run(["gh", "pr", "edit", str(existing[0]["number"]), "--body-file", f.name])
            print(f"본문 갱신: {existing[0]['url']}")
        else:
            print(f"이미 열린 PR: {existing[0]['url']} (본문을 바꾸려면 --update)")
        return
    run(["git", "push", "-u", "origin", branch])
    cmd = ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", issue_title(info),
           "--body-file", f.name, "--label", f"mission,phase-{info['phase']},{info['level']}",
           "--milestone", info["phase_title"]]
    if a.draft:
        cmd.append("--draft")
    print(f"생성: {run(cmd)}")


if __name__ == "__main__":
    main()
