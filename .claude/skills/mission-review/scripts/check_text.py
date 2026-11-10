#!/usr/bin/env python3
"""리뷰 보고서, 이슈와 PR 본문, 템플릿이 references/writing-rules.md를 지키는지 검사한다.

사용법
  python3 .claude/skills/mission-review/scripts/check_text.py 파일1 파일2 ...
  gh pr view 2 --json body --jq .body | python3 .claude/skills/mission-review/scripts/check_text.py -
코드 블록(```)과 인라인 코드(`...`) 안은 검사하지 않는다. 위반이 1건 이상이면 종료 코드 1.
"""
import re
import sys

RULES = [
    (r"·", "가운뎃점 대신 쉼표를 쓰거나 줄을 나눈다"),
    (r"—", "긴 줄표 대신 쉼표나 괄호를 쓴다"),
    (r"[☀-➿⭐⭕\U0001F300-\U0001FAFF]", "이모지 대신 단어를 쓴다 (충족/미충족, 있음/없음)"),
    (r"훌륭|잘 작성|잘 구현|깔끔|완벽(하|합|히)|인상적|우수(하|합)|좋은 (코드|구조|접근|시도|습관)|멋지|멋진|돋보", "평가 대신 지킨 규칙과 위치를 쓴다"),
    (r"전반적|대체로|다소|약간", "대상과 개수를 쓴다"),
    (r"적절(하|한|히)|충분(하|한|히)|효율적", "기준 수치나 규칙을 쓴다"),
    (r"가독성|유지보수성|확장성|견고(하|한|함)", "구체 현상을 쓴다"),
    (r"개선의 여지|더 나은 방법", "문제 현상과 질문을 쓴다"),
    (r"고려해\s?보|(하|쓰|두)는 것이 좋습니다|추천(합니다|드립니다)|어떨까요", "관찰과 질문으로 바꾼다"),
    (r"것 같습니다|것으로 보입니다|것 같다\.", "확인한 사실이나 확인 방법을 쓴다"),
    (r"살펴보겠|결론적으로|요약하자면|중요합니다|핵심입니다|도움이 될 (것|겁)", "내용 없는 연결어는 지운다"),
]


def check(name, text):
    hits = []
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        plain = re.sub(r"`[^`]*`", "", line)
        for pat, fix in RULES:
            m = re.search(pat, plain)
            if m:
                hits.append(f"{name}:{i}: '{m.group(0)}' → {fix}\n    | {line.strip()[:120]}")
    return hits


def main():
    hits = []
    for a in sys.argv[1:] or ["-"]:
        text = sys.stdin.read() if a == "-" else open(a, encoding="utf-8").read()
        hits += check(a, text)
    print("\n".join(hits))
    print(f"위반 {len(hits)}건")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
