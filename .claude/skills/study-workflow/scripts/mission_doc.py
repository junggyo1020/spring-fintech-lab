"""미션 문서 파서와 gh 호출 공통 함수 (mission_issue.py, mission_pr.py가 사용)."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def run(cmd, check=True, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or ROOT, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise SystemExit(f"명령 실패: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def clean(text):
    """이슈, PR 본문에 옮길 때 가운뎃점과 긴 줄표를 쉼표로 바꾼다 (references/writing-rules.md 2절)."""
    text = re.sub(r"\s*\u00b7\s*", ", ", text)
    return re.sub(r"\s+\u2014\s+", ", ", text)


def repo_slug():
    return json.loads(run(["gh", "repo", "view", "--json", "nameWithOwner"]))["nameWithOwner"]


def find_mission_doc(mission_id):
    """'M1-1' → phase-1-*/missions/M1-1-*.md"""
    p = mission_id.split("-")[0][1:]
    hits = sorted(ROOT.glob(f"phase-{p}-*/missions/{mission_id}-*.md"))
    if not hits:
        raise SystemExit(f"미션 문서를 찾지 못함: {mission_id}")
    return hits[0]


def phase_missions(phase):
    return sorted(ROOT.glob(f"phase-{phase}-*/missions/M{phase}-*.md"),
                  key=lambda f: int(re.match(r"M\d+-(\d+)", f.name).group(1)))


def section(text, title_suffix):
    """'## ...{title_suffix}' 섹션 본문"""
    m = re.search(rf"^## [^\n]*{re.escape(title_suffix)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def week_scope(readme_text, mission_id):
    """Phase README '주차별 계획' 표에서 이 미션이 들어 있는 행의 (주, 개념 학습 범위)"""
    for line in section(readme_text, "주차별 계획").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.search(rf"\b{re.escape(mission_id)}\b", cells[1]):
            return cells[0], cells[2]
    return "", ""


def parse_scenarios(body):
    """시나리오 ID 목록. '| # |'로 시작하는 표의 행 번호와 '### 시나리오 N', '### 실험 N' 소제목만 센다.
    시간 순서 표(| 시각 | 세션 A |)처럼 첫 칸이 T1인 표는 시나리오가 아니다."""
    out, in_table = [], False
    for line in body.splitlines():
        head = re.match(r"^###\s*(시나리오|실험)\s*(\d+)", line)
        if head:
            sid = head.group(2) if head.group(1) == "시나리오" else f"실험 {head.group(2)}"
            if sid not in [x for x, _ in out]:
                out.append((sid, ""))
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        if re.match(r"^\|\s*#\s*\|", line):
            in_table = True
            continue
        cell = re.match(r"^\|\s*([A-Z]?\d+)\s*\|\s*([^|]*)\|", line)
        if in_table and cell and cell.group(1) not in [x for x, _ in out]:
            out.append((cell.group(1), cell.group(2).strip()))
    return out


def scenario_pattern(mission_id, sid):
    """@DisplayName에서 시나리오를 찾는 정규식. 형식: "M1-1 #3 ..." 또는 "M5-7 실험 2 ..." """
    label = re.escape(sid) if sid.startswith("실험") else "#" + re.escape(sid)
    return rf"{re.escape(mission_id)}\s+{label}(?![0-9])"


def parse(doc):
    text = doc.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    m = re.match(r"# (M(\d+)-(\d+)) (.+)", first)
    mission_id, phase, num, title = m.group(1), m.group(2), m.group(3), clean(m.group(4).strip())
    meta = re.search(r"^> 가이드 수준: (L[123]), 예상 시간: ([^,\s]+), 선행: (.+)$", text, re.M)
    slug = doc.stem.split("-", 2)[2]
    criteria = [l for l in section(text, "완료 기준").splitlines() if l.strip().startswith("- [")]
    scenarios = parse_scenarios(section(text, "테스트 시나리오"))
    readme_text = (doc.parent.parent / "README.md").read_text(encoding="utf-8")
    phase_title = re.sub(r"\s*\([\d.]+주\)\s*$", "", readme_text.splitlines()[0].lstrip("# ").strip())
    phase_title = clean(re.sub(r"^(Phase \d+) \u2014 ", r"\1: ", phase_title))
    week, scope = week_scope(readme_text, mission_id)
    prereq = meta.group(3).strip()
    return {
        "id": mission_id, "phase": phase, "num": num, "title": title,
        "level": meta.group(1), "hours": meta.group(2),
        "prereq": prereq, "prereq_ids": re.findall(r"M\d+-\d+", prereq),
        "branch": f"phase{phase}/m{phase}-{num}-{slug}",
        "criteria": criteria, "scenarios": scenarios,
        # 완료 기준에 테스트 실행이 없는 미션(M0-1 명령 출력 기록, M0-3 CI 실행, M5-1 SQL 실행)은 시나리오를 직접 실행해 확인한다
        "manual": meta.group(1) != "L3" and not any("gradlew" in c or "test" in c.lower() for c in criteria),
        "doc_rel": doc.relative_to(ROOT).as_posix(),
        "readme_rel": (doc.parent.parent / "README.md").relative_to(ROOT).as_posix(),
        "phase_title": phase_title, "week": week, "scope": scope,
        "workspace": (doc.parent.parent / "workspace"),
    }


def scenario_file(info):
    return f"{info['workspace'].relative_to(ROOT).as_posix()}/docs/test-scenarios/{info['id']}.md"


def issue_title(info):
    return f"[{info['id']}] {info['title']}"


def find_issue(mission_id, state="all"):
    out = run(["gh", "issue", "list", "--state", state, "--limit", "200",
               "--search", f"[{mission_id}] in:title", "--json", "number,title,state"])
    for it in json.loads(out or "[]"):
        if it["title"].startswith(f"[{mission_id}]"):
            return it
    return None
