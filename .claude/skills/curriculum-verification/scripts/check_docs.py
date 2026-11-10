#!/usr/bin/env python3
"""spring-fintech-lab 문서 자동 검사.

검사 항목
  ERROR  깨진 상대 경로 링크
  ERROR  미션 문서 구조 (제목 형식, 메타 줄, 필수 섹션과 순서)
  ERROR  <details> 열고 닫기 개수 불일치
  ERROR  Phase README 미션 표에 없는 미션 파일 / 존재하지 않는 미션 링크
  WARN   추상 표현 (코드 블록과 인라인 코드는 제외)
  WARN   가운뎃점 (코드 블록 밖 모든 줄)

사용법
  python3 .claude/skills/curriculum-verification/scripts/check_docs.py            # 레포 전체
  python3 .claude/skills/curriculum-verification/scripts/check_docs.py phase-3-*  # 일부
종료 코드: ERROR가 1개 이상이면 1
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKIP_DIRS = {".git", ".claude", "_workspace", "workspace", "node_modules", "build"}

ABSTRACT = [
    (r"자연스럽게", "관찰 가능한 행동으로 (예: '설명 없이 작성한다' → 무엇을 몇 분 안에)"),
    (r"체감", "측정값 또는 재현 테스트로"),
    (r"충분(히|한)", "수치 기준으로"),
    (r"적절(히|한)", "규칙 자체를 명시"),
    (r"가볍게", "범위를 명시 (몇 절, 몇 쪽)"),
    (r"그때그때", "조건을 명시"),
    (r"어느\s?정도", "수치 기준으로"),
    (r"웬만", "조건을 명시"),
    (r"제대로", "기준을 명시"),
    (r"확실(히|하게)", "검증 방법을 명시"),
    (r"효율적", "측정 지표로"),
    (r"깔끔(하게|한)", "기준을 명시"),
    (r"수(십|백|천|만|십만|백만)\s?(개|건|명|번|회)", "구체 숫자로"),
    (r"대량", "구체 숫자로"),
    (r"(이해한다|익힌다|체화한다|안다)\.?$", "관찰 가능한 행동으로 (목표/완료 기준 줄에서)"),
    (r"큰 무기", "구체 효과로"),
    (r"운영 수준", "구체 항목으로"),
]

MISSION_HEADINGS = ["목표", "배경", "요구사항", "테스트 시나리오", "제약", "힌트", "완료 기준", "생각해볼 질문"]
MISSION_TITLE = re.compile(r"^# M\d-\d+ \S")
MISSION_META = re.compile(r"^> 가이드 수준: L[123], 예상 시간: \d+~\d+h, 선행: .+")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

errors, warns = [], []


def strip_inline_code(line):
    return re.sub(r"`[^`]*`", "", line)


def md_files(args):
    if not args:
        args = ["."]
    out = []
    for a in args:
        for p in (ROOT.glob(a) if any(c in a for c in "*?[") else [ROOT / a]):
            if p.is_dir():
                out += [f for f in p.rglob("*.md") if not (set(f.relative_to(ROOT).parts) & SKIP_DIRS)]
            elif p.suffix == ".md":
                out.append(p)
    return sorted(set(out))


def check_file(f):
    rel = f.relative_to(ROOT)
    text = f.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        plain = strip_inline_code(line)
        for m in LINK.finditer(plain):
            target = m.group(1).split("#")[0].strip()
            if not target or re.match(r"^[a-z]+://|^mailto:", target):
                continue
            if not (f.parent / target).resolve().exists():
                errors.append(f"{rel}:{i}: 깨진 링크 → {target}")
        if "\u00b7" in line:
            warns.append(f"{rel}:{i}: 가운뎃점 → 쉼표나 줄 나누기 (writing-rules.md 2절)\n    | {line.strip()[:120]}")
        for pat, fix in ABSTRACT:
            if re.search(pat, plain):
                warns.append(f"{rel}:{i}: 추상 표현 /{pat}/ → {fix}\n    | {line.strip()[:120]}")
    if text.count("<details>") != text.count("</details>"):
        errors.append(f"{rel}: <details> {text.count('<details>')}개, </details> {text.count('</details>')}개")
    if f.parent.name == "missions":
        check_mission(rel, lines)


def check_mission(rel, lines):
    if not lines or not MISSION_TITLE.match(lines[0]):
        errors.append(f"{rel}:1: 제목이 '# M<P>-<N> <제목>' 형식이 아님")
    meta = next((l for l in lines[1:6] if l.startswith(">")), "")
    if not MISSION_META.match(meta):
        errors.append(f"{rel}: 메타 줄 형식 오류 (예: '> 가이드 수준: L2, 예상 시간: 4~6h, 선행: M2-1')")
    heads = [l[3:].strip() for l in lines if l.startswith("## ")]
    norm = ["테스트 시나리오" if h.endswith("테스트 시나리오") else h for h in heads]
    pos = -1
    for h in MISSION_HEADINGS:
        if h not in norm:
            errors.append(f"{rel}: 필수 섹션 '## {h}' 없음")
            continue
        idx = norm.index(h)
        if idx < pos:
            errors.append(f"{rel}: 섹션 '## {h}' 순서가 템플릿과 다름")
        pos = max(pos, idx)


def check_phase_index():
    for readme in sorted(ROOT.glob("phase-*/README.md")):
        mdir = readme.parent / "missions"
        if not mdir.exists():
            continue
        text = readme.read_text(encoding="utf-8")
        linked = set(re.findall(r"\(missions/([^)]+\.md)\)", text))
        actual = {p.name for p in mdir.glob("*.md")}
        for miss in sorted(actual - linked):
            errors.append(f"{readme.relative_to(ROOT)}: 미션 표에 없는 파일 missions/{miss}")


def main():
    files = md_files(sys.argv[1:])
    for f in files:
        check_file(f)
    check_phase_index()
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"\n검사 파일 {len(files)}개, ERROR {len(errors)}, WARN {len(warns)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
