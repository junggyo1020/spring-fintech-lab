#!/usr/bin/env python3
"""현재 미션 브랜치로 PR을 만든다 (.github/pull_request_template.md와 같은 절 구성).

스크립트가 채우는 것
  미션 절: 이슈 연결(Closes #N), 미션 문서 링크, 가이드 수준, 예상 시간
  자동 점검 결과: 테스트 개수, 시나리오 대응(@DisplayName의 "M1-1 #3" 형식), 커밋 순서, 금지 패턴, 변경 파일 통계
  완료 기준: 미션 문서의 체크박스
학습자가 쓰는 것
  --notes 파일: "### 구현 요약", "### 설계 결정과 이유", "### 리뷰어에게 묻고 싶은 것",
               "### 실제 소요 시간", "### TIL" 5개 절
  리뷰 반영 기록: GitHub에서 PR 본문을 편집해 표에 줄을 추가

사용법 (레포 루트, 미션 브랜치 phase{P}/m{P}-{N}-{slug} 체크아웃 상태)
  python3 .claude/skills/study-workflow/scripts/mission_pr.py --notes notes.md
  ... --dry-run      PR을 만들지 않고 본문만 출력 (push하지 않음)
  ... --skip-tests   테스트 실행 생략
  ... --draft        Draft PR로 생성 (L3 시나리오 표 리뷰, 테스트 실패 상태)
  ... --update       열린 PR의 본문 갱신. 완료 기준 체크 상태와 리뷰 반영 기록은 기존 본문 것을 유지하고,
                     --notes가 없으면 학습자 메모도 기존 것을 유지한다
"""
import argparse
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mission_doc import (ROOT, clean, find_issue, find_mission_doc, issue_title, parse,  # noqa: E402
                         repo_slug, run, scenario_file, scenario_pattern)

NOTE_HEADINGS = ["구현 요약", "설계 결정과 이유", "리뷰어에게 묻고 싶은 것", "실제 소요 시간", "TIL"]
LEVEL_DESC = {"L1": "L1 (시그니처와 테스트 표 제공)", "L2": "L2 (요구사항과 테스트 표 제공)",
              "L3": "L3 (요구사항과 불변식만 제공)"}
REVIEW_LOG = """| 리뷰 회차 | 지적 번호 | 반영 커밋 | 바꾼 내용 |
|---|---|---|---|"""
FORBIDDEN = [
    ("금액에 쓰일 수 있는 `double`, `float` (src/main)", r"\b(double|float|Double|Float)\b", "src/main/", False),
    ("비어 있는 `catch (InterruptedException ...)`", r"catch\s*\(\s*(final\s+)?InterruptedException\s+\w+\s*\)\s*\{\s*(//[^\n]*\s*)*\}", "", True),
    ("`@Disabled`", r"@Disabled\b", "", False),
    ("인자 없는 `LocalDateTime.now()`, `LocalDate.now()`, `Instant.now()` (src/main)",
     r"\b(LocalDateTime|LocalDate|Instant)\.now\(\s*\)", "src/main/", False),
]


def changed_files():
    return [p for p in run(["git", "diff", "--name-only", "--diff-filter=AM", "origin/main...HEAD"], check=False).splitlines() if p]


def gradle_roots(info, files):
    roots = set()
    for path in files:
        p = (ROOT / path).parent
        while p != ROOT and ROOT in p.parents:
            if (p / "gradlew").exists() and "workspace" in p.parts:
                roots.add(p)
                break
            p = p.parent
    if not roots and (info["workspace"] / "gradlew").exists():
        roots.add(info["workspace"])
    return sorted(roots)


def test_section(roots, skip):
    if skip:
        return "테스트 실행을 생략했다 (`--skip-tests`)."
    if not roots:
        return "`gradlew`가 있는 workspace를 찾지 못했다. M0-2 이전 미션이면 정상이다."
    rows = ["| workspace | 통과 | 실패 | 건너뜀 | 결과 |", "|---|---|---|---|---|"]
    for root in roots:
        for old_xml in root.glob("**/build/test-results/test/*.xml"):
            old_xml.unlink()  # 컴파일이 실패하면 test 태스크가 돌지 않아 이전 결과가 남는다
        out = run(["./gradlew", "test", "--console=plain"], check=False, cwd=root)
        total = fail = skip_n = 0
        xmls = list(root.glob("**/build/test-results/test/*.xml"))  # 멀티 모듈(Phase 8)은 모듈별 build/ 아래에 있다
        if not xmls:
            build = "BUILD SUCCESSFUL" if "BUILD SUCCESSFUL" in out else "BUILD FAILED"
            rows.append(f"| `{root.relative_to(ROOT).as_posix()}` | - | - | - | {build} (테스트 결과 파일 없음) |")
            continue
        for xml in xmls:
            s = ET.parse(xml).getroot()
            total += int(s.get("tests", 0))
            fail += int(s.get("failures", 0)) + int(s.get("errors", 0))
            skip_n += int(s.get("skipped", 0))
        build = "BUILD SUCCESSFUL" if "BUILD SUCCESSFUL" in out else "BUILD FAILED"
        rows.append(f"| `{root.relative_to(ROOT).as_posix()}` | {total - fail - skip_n} | {fail} | {skip_n} | {build} |")
    return "\n".join(rows)


def display_names(roots):
    names = []
    for root in roots:
        for f in root.rglob("src/test/**/*.java"):
            names += re.findall(r'@DisplayName\("((?:[^"\\]|\\.)*)"\)', f.read_text(encoding="utf-8"))
    return names


def scenario_section(info, roots):
    parts = []
    if info["level"] == "L3" or not info["scenarios"]:
        path = scenario_file(info)
        if (ROOT / path).exists():
            content = clean((ROOT / path).read_text(encoding="utf-8").strip())
            parts.append(f"직접 작성한 시나리오 표: `{path}`\n\n<details><summary>시나리오 표 펼치기</summary>\n\n{content}\n\n</details>")
        else:
            parts.append(f"직접 작성한 시나리오 표 `{path}`가 없다. L3 미션은 이 파일이 있어야 리뷰를 시작한다.")
        if not info["scenarios"]:
            return "\n".join(parts)
        parts.append("미션 문서가 제공한 참조 시나리오:")
    if info["manual"]:
        return (f"테스트 코드 없이 시나리오 {len(info['scenarios'])}개를 직접 실행해 확인하는 미션이다. "
                "완료 기준에 적힌 기록 파일과 실행 결과로 대응한다.")
    names = display_names(roots)
    if not names and info["level"] != "L3":
        parts.append(f"workspace에 `@DisplayName`이 있는 테스트가 없다. 시나리오 {len(info['scenarios'])}개 모두 없음.")
        return "\n\n".join(parts)
    rows = ["| 시나리오 | 테스트(@DisplayName) | 상태 |", "|---|---|---|"]
    missing = []
    for sid, _ in info["scenarios"]:
        hits = [n for n in names if re.search(scenario_pattern(info["id"], sid), n)]
        if not hits:
            missing.append(sid)
        rows.append(f"| {sid} | {'<br>'.join(clean(h) for h in hits) if hits else '-'} | {'있음' if hits else '없음'} |")
    summary = f"{len(info['scenarios'])}개 중 {len(info['scenarios']) - len(missing)}개 있음. 없는 번호: {', '.join(missing) if missing else '없음'}"
    parts.append(summary + "\n\n" + "\n".join(rows))
    return "\n\n".join(parts)


def commit_section(manual=False):
    log = run(["git", "log", "--reverse", "--format=%h%x09%s", "origin/main..HEAD"], check=False).splitlines()
    if not log:
        return "origin/main 이후 커밋이 없다."
    rows = ["| 순서 | 커밋 | 메시지 | 종류 |", "|---|---|---|---|"]
    first_test = first_impl = None
    for i, line in enumerate(log, 1):
        sha, subject = line.split("\t", 1)
        kind = "테스트" if subject.startswith("[test]") else "구현" if re.match(r"\[(feat|fix|refactor)\]", subject) else "기타"
        if kind == "테스트" and first_test is None:
            first_test = i
        if kind == "구현" and first_impl is None:
            first_impl = i
        rows.append(f"| {i} | `{sha}` | {clean(subject).replace('|', '/')} | {kind} |")
    if manual:
        verdict = "판정: 해당 없음. 테스트 코드 없이 직접 실행해 확인하는 미션이라 커밋 순서를 보지 않는다."
    elif first_test is None:
        verdict = "판정: 미충족. `[test]` 커밋이 없다."
    elif first_impl is not None and first_impl < first_test:
        verdict = f"판정: 미충족. 첫 구현 커밋({first_impl}번)이 첫 `[test]` 커밋({first_test}번)보다 먼저 있다."
    else:
        impl = f"첫 구현 커밋은 {first_impl}번이다." if first_impl else "구현 커밋은 아직 없다."
        verdict = f"판정: 충족. 첫 `[test]` 커밋이 {first_test}번이다. {impl}"
    return verdict + "\n\n" + "\n".join(rows)


def forbidden_section(files):
    java = [f for f in files if f.endswith(".java") and (ROOT / f).exists()]
    rows = ["| 패턴 | 건수 | 위치 |", "|---|---|---|"]
    for label, pat, prefix, multiline in FORBIDDEN:
        locs = []
        for f in java:
            if prefix and f"/{prefix}" not in f"/{f}":
                continue
            text = (ROOT / f).read_text(encoding="utf-8")
            if multiline:
                for m in re.finditer(pat, text):
                    locs.append(f"`{Path(f).name}:{text.count(chr(10), 0, m.start()) + 1}`")
            else:
                for n, line in enumerate(text.splitlines(), 1):
                    code = re.sub(r"//.*|\"(?:[^\"\\]|\\.)*\"", "", line)
                    if re.search(pat, code):
                        locs.append(f"`{Path(f).name}:{n}`")
        shown = ", ".join(locs[:10]) + (f" 외 {len(locs) - 10}곳" if len(locs) > 10 else "")
        rows.append(f"| {label} | {len(locs)} | {shown or '-'} |")
    return "\n".join(rows)


def diffstat_section():
    out = run(["git", "diff", "--numstat", "origin/main...HEAD"], check=False).splitlines()
    groups = {"src/main": [0, 0, 0], "src/test": [0, 0, 0], "문서(.md)": [0, 0, 0], "기타": [0, 0, 0]}
    for line in out:
        add, dele, path = line.split("\t", 2)
        key = "src/main" if "/src/main/" in f"/{path}" else "src/test" if "/src/test/" in f"/{path}" else "문서(.md)" if path.endswith(".md") else "기타"
        g = groups[key]
        g[0] += 1
        g[1] += int(add) if add.isdigit() else 0
        g[2] += int(dele) if dele.isdigit() else 0
    rows = ["| 구분 | 파일 수 | 추가 줄 | 삭제 줄 |", "|---|---|---|---|"]
    rows += [f"| {k} | {v[0]} | {v[1]} | {v[2]} |" for k, v in groups.items()]
    return "\n".join(rows)


def split_sections(body):
    """'## 제목' 단위로 나눈 dict"""
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def merge_criteria(new_lines, old_text):
    """기존 본문에서 체크된 완료 기준은 체크 상태를 유지한다"""
    checked = {re.sub(r"^- \[[xX]\]\s*", "", l).strip() for l in old_text.splitlines() if re.match(r"^- \[[xX]\]", l)}
    out = []
    for line in new_lines.splitlines():
        text = re.sub(r"^- \[ \]\s*", "", line).strip()
        out.append(f"- [x] {text}" if text in checked else line)
    return "\n".join(out)


def read_notes(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    missing = [h for h in NOTE_HEADINGS if not re.search(rf"^### {re.escape(h)}\s*$", text, re.M)]
    if missing:
        print(f"경고: notes 파일에 없는 절: {', '.join(missing)}", file=sys.stderr)
    return text


def placeholder_notes():
    return "\n\n".join(f"### {h}\n(작성 필요)" for h in NOTE_HEADINGS)


def build_body(info, slug, issue, tests, scen, commits, forbidden, diffstat, criteria, notes, review_log):
    url = f"https://github.com/{slug}/blob/main/{info['doc_rel']}"
    closes = f"Closes #{issue['number']}" if issue else "연결할 이슈가 없다. `mission_issue.py`로 이슈를 만든 뒤 `--update`로 다시 만든다."
    return f"""## 미션
- 이슈: {closes}
- 미션 문서: {url}
- 가이드 수준: {LEVEL_DESC[info['level']]}
- 예상 시간: {info['hours']}

## 자동 점검 결과
<!-- mission_pr.py가 채운다. 직접 고치지 않는다. 테스트를 바꾼 뒤에는 --update로 다시 만든다. -->

### 테스트
{tests}

### 테스트 시나리오 대응
{scen}

### 커밋 순서
{commits}

### 금지 패턴 (이 PR에서 바뀐 파일만)
{forbidden}

### 변경 파일
{diffstat}

## 완료 기준
{criteria}

## 학습자 메모
{notes}

## 리뷰 반영 기록
{review_log}
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
        raise SystemExit(f"미션 브랜치가 아니다: {branch} (형식: phase1/m1-1-money)")
    info = parse(find_mission_doc(f"M{m.group(2)}-{m.group(3)}"))
    slug = repo_slug()
    issue = find_issue(info["id"], state="open")
    files = changed_files()
    roots = gradle_roots(info, files)

    existing = json.loads(run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,url,body"]) or "[]")
    old = split_sections(existing[0]["body"]) if existing else {}

    criteria = clean("\n".join(info["criteria"])) or "- [ ] 미션 문서의 완료 기준 절을 확인한다"
    if old.get("완료 기준"):
        criteria = merge_criteria(criteria, old["완료 기준"])
    if a.notes:
        notes = read_notes(a.notes)
    elif old.get("학습자 메모"):
        notes = old["학습자 메모"]
    else:
        notes = placeholder_notes()
    review_log = old.get("리뷰 반영 기록") or REVIEW_LOG

    text = build_body(info, slug, issue, test_section(roots, a.skip_tests), scenario_section(info, roots),
                      commit_section(info["manual"]), forbidden_section(files), diffstat_section(), criteria, notes, review_log)

    if a.dry_run:
        print(f"===== {issue_title(info)}  ({branch} → main)\n{text}")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
    if existing:
        if a.update:
            run(["git", "push", "origin", branch])
            run(["gh", "pr", "edit", str(existing[0]["number"]), "--body-file", f.name])
            print(f"본문 갱신: {existing[0]['url']}")
        else:
            print(f"이미 열린 PR이 있다: {existing[0]['url']} (본문을 바꾸려면 --update)")
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
