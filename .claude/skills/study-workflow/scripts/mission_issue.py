#!/usr/bin/env python3
"""미션 문서로 GitHub 이슈를 만든다 (.github/ISSUE_TEMPLATE/mission.yml과 같은 구조).

사용법
  python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1 M1-2   # 미션 지정
  python3 .claude/skills/study-workflow/scripts/mission_issue.py --phase 1    # Phase 전체
  ... --dry-run                                                             # 만들지 않고 본문만 출력

같은 미션 번호로 시작하는 이슈가 이미 있으면(열림·닫힘 모두) 건너뛴다.
라벨(mission, phase-N, L1~L3)과 마일스톤(Phase 제목)이 없으면 만든다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mission_doc import find_issue, find_mission_doc, issue_title, parse, phase_missions, repo_slug, run  # noqa: E402

LABEL_COLORS = {"mission": "1d76db", "L1": "c2e0c6", "L2": "fbca04", "L3": "d93f0b"}


def ensure_label(name, existing):
    if name in existing:
        return
    color = LABEL_COLORS.get(name, "5319e7")
    run(["gh", "label", "create", name, "--color", color, "--force"])
    existing.add(name)


def ensure_milestone(slug, title):
    out = run(["gh", "api", f"repos/{slug}/milestones?state=all&per_page=100"])
    if not any(m["title"] == title for m in json.loads(out)):
        run(["gh", "api", f"repos/{slug}/milestones", "-f", f"title={title}"])


def body(info, slug):
    url = f"https://github.com/{slug}/blob/main/{info['doc_rel']}"
    criteria = "\n".join(info["criteria"]) or "- [ ] (미션 문서의 완료 기준을 확인)"
    return f"""### 미션

{info['id']} {info['title']}

### 미션 문서

{url}

### 가이드 수준 · 예상 시간 · 선행

{info['level']} · {info['hours']} · 선행: {info['prereq']}

### 작업 브랜치

`{info['branch']}`

### 완료 기준

{criteria}

### 진행 메모

_No response_
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("missions", nargs="*")
    ap.add_argument("--phase")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    docs = [find_mission_doc(m) for m in a.missions]
    if a.phase is not None:
        docs += phase_missions(a.phase)
    if not docs:
        ap.error("미션 번호 또는 --phase를 지정한다")
    slug = repo_slug()
    labels = set() if a.dry_run else {l["name"] for l in json.loads(run(["gh", "label", "list", "--limit", "200", "--json", "name"]))}
    for doc in docs:
        info = parse(doc)
        title = issue_title(info)
        text = body(info, slug)
        if a.dry_run:
            print(f"===== {title}\nlabels: mission, phase-{info['phase']}, {info['level']} · milestone: {info['phase_title']}\n{text}")
            continue
        found = find_issue(info["id"])
        if found:
            print(f"건너뜀: #{found['number']} {found['title']} ({found['state']})")
            continue
        for name in ("mission", f"phase-{info['phase']}", info["level"]):
            ensure_label(name, labels)
        ensure_milestone(slug, info["phase_title"])
        url = run(["gh", "issue", "create", "--title", title, "--body", text,
                   "--label", f"mission,phase-{info['phase']},{info['level']}",
                   "--milestone", info["phase_title"]])
        print(f"생성: {url}")


if __name__ == "__main__":
    main()
