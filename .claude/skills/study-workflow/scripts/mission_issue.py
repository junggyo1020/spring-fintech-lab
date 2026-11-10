#!/usr/bin/env python3
"""미션 문서로 GitHub 이슈를 만든다 (.github/ISSUE_TEMPLATE/mission.yml과 같은 구조).

사용법
  python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1 M1-2   # 미션 지정
  python3 .claude/skills/study-workflow/scripts/mission_issue.py --phase 1    # Phase 전체
  ... --dry-run                                                             # 만들지 않고 본문만 출력

같은 미션 번호로 시작하는 이슈가 이미 있으면(열림, 닫힘 모두) 건너뛴다.
라벨(mission, phase-N, L1~L3)과 마일스톤(Phase 제목)이 없으면 만든다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mission_doc import clean, find_issue, find_mission_doc, issue_title, parse, phase_missions, repo_slug, run, scenario_file  # noqa: E402

LABEL_COLORS = {"mission": "1d76db", "question": "d876e3", "doc-error": "b60205", "L1": "c2e0c6", "L2": "fbca04", "L3": "d93f0b"}


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


LEVEL_DESC = {"L1": "L1 (시그니처와 테스트 표 제공)", "L2": "L2 (요구사항과 테스트 표 제공)",
              "L3": "L3 (요구사항과 불변식만 제공, 테스트 시나리오는 직접 작성)"}


def before_list(info, slug, lookup):
    lines = []
    for pid in info["prereq_ids"]:
        found = lookup(pid)
        ref = f" (#{found['number']})" if found else ""
        lines.append(f"- [ ] 선행 미션 {pid}{ref}의 PR이 main에 머지됐다")
    if info["scope"]:
        readme = f"https://github.com/{slug}/blob/main/{info['readme_rel']}"
        lines.append(f"- [ ] [Phase README]({readme}) 주차별 계획 {clean(info['week'])}의 개념 학습 범위를 읽었다: {clean(info['scope'])}")
    lines.append(f"- [ ] `git switch main && git pull` 후 `git switch -c {info['branch']}`로 브랜치를 만들었다")
    return "\n".join(lines)


def progress_list(info):
    if info["level"] == "L3":
        path = scenario_file(info)
        return "\n".join([
            f"- [ ] `{path}`에 테스트 시나리오 표(# / 준비 / 실행 / 기대 결과)를 썼다",
            "- [ ] 미션 문서 \"반드시 포함할 경우\"가 모두 시나리오 표에 들어 있다",
            "- [ ] 시나리오 표만 커밋해 Draft PR로 리뷰를 받았다 (`mission_pr.py --draft`)",
            "- [ ] 시나리오마다 실패하는 테스트를 먼저 커밋했다",
            "- [ ] 구현 후 `./gradlew test`가 통과한다",
        ] + [f"- [ ] 참조 시나리오 {sid} (`@DisplayName(\"{info['id']} #{sid} ...\")`)" for sid, _ in info["scenarios"]])
    if info["manual"]:
        return "\n".join(f"- [ ] 시나리오 #{sid}: 직접 실행한 결과가 기대 결과와 같다" for sid, _ in info["scenarios"])
    first = info["scenarios"][0][0] if info["scenarios"] else "1"
    example = f"{info['id']} {first if first.startswith('실험') else '#' + first}"
    rows = [f"테스트 이름 형식: `@DisplayName(\"{example} 규칙을 문장으로\")` (PR 자동 점검이 이 형식으로 시나리오를 찾는다)", ""]
    rows += [f"- [ ] {sid if sid.startswith('실험') else '시나리오 #' + sid} 테스트를 작성했고 통과한다" for sid, _ in info["scenarios"]]
    rows.append("- [ ] 실패하는 테스트를 구현보다 먼저 커밋했다 (`[test]` 커밋이 첫 구현 커밋보다 앞)")
    return "\n".join(rows)


def body(info, slug, lookup):
    url = f"https://github.com/{slug}/blob/main/{info['doc_rel']}"
    criteria = clean("\n".join(info["criteria"])) or "- [ ] 미션 문서의 완료 기준 절을 확인한다"
    return f"""### 미션

{info['id']} {info['title']}

### 미션 문서

{url}

### 가이드 수준

{LEVEL_DESC[info['level']]}

### 예상 시간

{info['hours']}

### 작업 브랜치

`{info['branch']}`

### 시작 전 확인

{before_list(info, slug, lookup)}

### 진행 체크리스트

{progress_list(info)}

### 완료 기준

{criteria}

### 막힌 지점 기록

막힐 때마다 이 이슈에 댓글로 남긴다. 형식: 시도한 것(명령, 바꾼 코드 위치) / 기대한 결과 / 실제 결과(에러 원문)
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
    created = {}  # 이번 실행에서 만든 이슈. 방금 만든 이슈는 GitHub 검색에 바로 잡히지 않는다
    for doc in docs:
        info = parse(doc)
        title = issue_title(info)
        lookup = (lambda pid: None) if a.dry_run else (lambda pid: created.get(pid) or find_issue(pid))
        text = body(info, slug, lookup)
        if a.dry_run:
            print(f"===== {title}\nlabels: mission, phase-{info['phase']}, {info['level']}\nmilestone: {info['phase_title']}\n{text}")
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
        created[info["id"]] = {"number": int(url.rstrip("/").split("/")[-1]), "title": title, "state": "OPEN"}
        print(f"생성: {url}")


if __name__ == "__main__":
    main()
