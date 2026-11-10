---
name: study-workflow
description: spring-fintech-lab 미션의 GitHub 진행 흐름(미션 이슈 생성, 미션 브랜치, 템플릿 PR 생성, Gemini와 Claude 리뷰, 재리뷰, 머지)을 실행한다. "M1-1 이슈 만들어줘", "Phase 2 이슈 전부 만들어", "미션 시작할게", "PR 올려줘", "PR 만들어줘", "PR 본문 갱신해줘", "리뷰 반영했어", "질문 이슈 만들어줘", "머지해줘"처럼 미션 이슈, 브랜치, PR을 다루는 요청에는 반드시 이 스킬을 사용할 것. 리뷰 내용과 기준은 mission-review, 미션 문서 수정은 mission-authoring을 쓴다.
---

# 미션 진행 흐름 (이슈, 실습, PR, 리뷰, 머지)

미션 1개를 실무 협업 순서(이슈, 브랜치, PR, 리뷰, 머지)로 끝낸다.
학습자가 직접 쓰는 것은 코드, 테스트, 학습자 메모, 리뷰 반영 기록 4가지다. 이슈 본문과 PR 본문의 나머지(링크, 체크리스트, 테스트 개수, 시나리오 대응, 커밋 순서, 금지 패턴, 완료 기준)는 스크립트가 미션 문서와 git 기록에서 채운다. 형식을 채우는 시간을 줄여 설계 결정과 질문을 쓰는 데 시간을 쓰게 하기 위해서다.

이슈, PR, 댓글에 쓰는 문장은 `.claude/skills/mission-review/references/writing-rules.md`를 따른다.

## 1. 미션 시작: 이슈 생성

```bash
python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1          # 미션 1개
python3 .claude/skills/study-workflow/scripts/mission_issue.py --phase 1     # Phase 전체
python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1 --dry-run
```

| 항목 | 값 |
|---|---|
| 제목 | `[M1-1] 미션 제목` (제목의 가운뎃점은 쉼표로 바뀐다) |
| 라벨 | `mission`, `phase-1`, `L1` |
| 마일스톤 | Phase README 첫 줄에서 주차 표기를 뺀 것. 예: `Phase 1: 금융 도메인을 위한 Java 기본기 + TDD` |
| 시작 전 확인 | 선행 미션 PR 머지 여부(선행 미션 이슈 번호 포함), Phase README 주차별 계획에서 이 미션이 들어 있는 주의 개념 학습 범위, 브랜치 생성 명령 |
| 진행 체크리스트 | L1, L2: 테스트 이름 형식 안내 1줄, 시나리오마다 1개, 테스트 커밋 순서 1개. 완료 기준에 테스트 실행이 없는 미션(M0-1, M0-3, M5-1)은 시나리오마다 "직접 실행한 결과가 기대 결과와 같다" 1개만. L3: 고정 항목 5개(시나리오 표 작성, "반드시 포함할 경우" 반영, Draft PR 리뷰, 테스트 먼저 커밋, 구현)와 참조 시나리오마다 1개(M7-3은 R1~R12) |
| 완료 기준 | 미션 문서 완료 기준 그대로 |

같은 미션 번호의 이슈가 이미 있으면(닫힌 것 포함) 건너뛴다. 다시 만들어야 하면 기존 이슈 번호를 사용자에게 보여주고 확인받는다.

## 2. 실습

이슈 본문의 "작업 브랜치" 이름(`phase{P}/m{P}-{N}-{slug}`)을 그대로 쓴다. PR 스크립트와 리뷰 워크플로가 이 형식으로 미션을 찾는다.

이 단계에서 Claude는 코드를 대신 쓰지 않는다. 막혔다는 요청에는 mission-review 스킬 7절 형식으로 답한다.
30분 넘게 막힌 지점은 "질문" 이슈 템플릿(`.github/ISSUE_TEMPLATE/question.yml`)으로 기록하게 안내한다. 질문 이슈 댓글에 `@claude`를 쓰면 GitHub에서도 같은 형식으로 답한다.

## 3. PR 생성

1. 학습자에게 메모 5개 절을 받는다. 학습자가 쓰지 않은 내용을 Claude가 지어내지 않는다. 비어 있는 절은 "(작성 필요)"로 둔다.

   | 절 | 받을 내용 |
   |---|---|
   | `### 구현 요약` | 만든 클래스와 각 클래스의 책임 3~5줄 |
   | `### 설계 결정과 이유` | 고민한 선택지 2개 이상, 고른 것, 고른 이유 |
   | `### 리뷰어에게 묻고 싶은 것` | `파일:줄`과 질문, 최대 3개 |
   | `### 실제 소요 시간` | 걸린 시간, 예상 시간, 가장 오래 걸린 단계 |
   | `### TIL` | til/ 파일 링크 |

2. 메모를 scratchpad의 notes.md에 위 절 제목 그대로 저장한다. 절이 빠지면 스크립트가 경고를 출력한다.
3. 본문을 먼저 보여준다: `mission_pr.py --dry-run --notes <notes.md>`. 아래 항목이 있으면 PR을 만들기 전에 학습자에게 알린다.

   | 자동 점검 항목 | 알릴 내용 |
   |---|---|
   | 시나리오 대응 "없음" | 없는 시나리오 번호. `@DisplayName`이 `"M1-1 #3 ..."` 형식이 아니거나 테스트가 없다 |
   | 커밋 순서 "미충족" | 첫 구현 커밋이 첫 `[test]` 커밋보다 앞이다. 완료 기준 항목이라 리뷰에서 필수 지적이 된다 |
   | 금지 패턴 1건 이상 | 패턴 이름과 위치 |
   | 테스트 실패 1건 이상 | Draft로 만들지(`--draft`) 묻는다 |

4. 확인받은 뒤 실행: `mission_pr.py --notes <notes.md>`. 브랜치를 push하고 PR을 만든다. `Closes #이슈`가 들어가 머지하면 이슈가 닫힌다.
5. Claude가 커밋을 만들 때는 사용자 명의와 `[type] 한글 설명` 형식을 따르고, AI 작성 표기를 넣지 않는다.

L3 미션은 `workspace/docs/test-scenarios/M{P}-{N}.md`가 있으면 스크립트가 PR 본문에 접어서 넣는다. 구현 전에 시나리오 표만 리뷰받으려면 그 파일만 커밋하고 `--draft`로 PR을 연다. Draft PR은 자동 리뷰 대상이 아니므로 PR 댓글에 `@claude 시나리오 표 리뷰`를 쓴다.

## 4. 리뷰와 재리뷰

| 리뷰어 | 설정 파일 | 실행 시점 | 맡는 것 |
|---|---|---|---|
| Claude | `.github/workflows/claude-review.yml`, 기준은 mission-review 스킬 | PR 열림, Draft에서 Ready로 변경 | 미션 문서 기준: 시나리오 대응, 완료 기준, 필수/권장/질문 지적, 판정 |
| Gemini Code Assist | `.gemini/config.yaml`, `.gemini/styleguide.md` | PR 열림. Draft로 연 PR은 자동 리뷰하지 않으므로 Ready로 바꾼 뒤 `/gemini review` | 줄 단위 코드 결함 |

리뷰를 반영하는 순서:
1. 지적 1건을 고칠 때마다 커밋한다. 커밋 메시지에 지적 번호를 넣는다. 예: `[fix] 출금 검사와 차감을 한 잠금 안으로 이동 (리뷰 1회차 필수 1)`
2. PR 본문 "리뷰 반영 기록" 표에 `| 1회차 | 필수 1 | abc1234 | 42~45번 줄을 synchronized 블록으로 감쌌다 |`처럼 한 줄씩 추가한다.
3. `mission_pr.py --update`로 자동 점검 결과를 다시 만든다. 완료 기준 체크 상태, 학습자 메모, 리뷰 반영 기록은 기존 본문 것이 유지된다.
4. PR 댓글에 `@claude 다시 리뷰`를 쓴다. Claude가 이전 지적 대조표가 들어간 n회차 리뷰를 단다. 같은 지적이 미해결로 남으면 힌트 단계가 올라간다(mission-review 4절).
5. Gemini 재리뷰가 필요하면 PR 댓글에 `/gemini review`를 쓴다.

로컬 Claude Code 세션에서도 mission-review 스킬로 같은 기준의 리뷰를 받을 수 있다.

## 5. 머지

머지 조건은 Claude 리뷰의 판정이 "머지 가능"인 것이다. 판정 규칙은 mission-review 5절에 있다(필수 0건, 완료 기준 전부 충족, CI 통과).
`gh pr merge <번호> --merge --delete-branch`를 쓴다. `--squash`를 쓰지 않는 이유는 테스트 커밋이 구현 커밋보다 먼저라는 기록이 main 히스토리에 남아야 하기 때문이다.
머지 후 README 진행 현황에서 해당 미션 체크박스를 체크하고, 리뷰 보고서의 "weakness.md 후보" 줄을 `til/weakness.md`에 추가하도록 안내한다.

## 사전 준비 (레포 관리자가 1회, 외부 서비스라 Claude가 대신 할 수 없음)

| 항목 | 방법 |
|---|---|
| Gemini Code Assist | https://github.com/apps/gemini-code-assist 에서 이 레포에 설치 (개인 Google 계정, 무료) |
| Claude GitHub App | https://github.com/apps/claude 에서 이 레포에 설치 |
| Claude 토큰 | 로컬 터미널에서 `claude setup-token` 실행 후 레포 Secrets에 `CLAUDE_CODE_OAUTH_TOKEN`으로 등록 |

## 에러 처리

| 상황 | 대응 |
|---|---|
| `미션 브랜치가 아니다` | 현재 브랜치 이름을 보여주고 `git branch -m phase{P}/m{P}-{N}-{slug}`를 제안한다 |
| `연결할 이슈가 없다` | `mission_issue.py M{P}-{N}`으로 이슈를 만든 뒤 `--update`로 본문을 다시 만든다 |
| `gradlew가 있는 workspace를 찾지 못했다` | workspace에 `gradlew`가 있는지 확인한다. M0-2 이전 미션은 `--skip-tests`를 쓴다 |
| `gh pr create`가 마일스톤을 찾지 못함 | `mission_issue.py`를 먼저 실행하면 마일스톤이 만들어진다 |
| Claude 리뷰 job 인증 오류 | Secrets의 `CLAUDE_CODE_OAUTH_TOKEN` 등록 여부와 Claude App 설치 여부를 확인하게 안내한다 |
