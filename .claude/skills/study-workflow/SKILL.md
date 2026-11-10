---
name: study-workflow
description: spring-fintech-lab 미션의 GitHub 진행 흐름(미션 이슈 생성 → 미션 브랜치 → 템플릿 PR 생성 → CodeRabbit·Claude 리뷰 → 머지)을 실행한다. "M1-1 이슈 만들어줘", "Phase 2 이슈 전부 만들어", "미션 시작할게", "PR 올려줘", "PR 만들어줘", "PR 본문 갱신해줘", "리뷰 반영했어", "머지해줘"처럼 미션 이슈·브랜치·PR을 다루는 요청에는 반드시 이 스킬을 사용할 것. 코드 리뷰 내용 자체는 mission-review, 미션 문서 수정은 mission-authoring을 쓴다.
---

# 미션 진행 흐름 (이슈 → 실습 → PR → 리뷰)

이 흐름의 목적은 미션 하나를 "문서 → 이슈 → 브랜치 → PR → 리뷰 → 머지"라는 실무 협업 순서로 끝내는 것이다.
학습자가 직접 쓰는 것은 **코드, 테스트, 학습자 메모** 세 가지다. 이슈 본문, PR 본문의 기계적인 부분(링크, 메타, 테스트 개수, 시나리오 대응표, 완료 기준)은 스크립트가 미션 문서에서 채운다. 이렇게 나누는 이유는 형식을 채우는 시간을 줄이고, 학습자 메모(설계 결정, 자신 없는 부분)에 시간을 쓰게 하기 위해서다.

## 1. 미션 시작: 이슈 생성

```bash
python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1          # 미션 1개
python3 .claude/skills/study-workflow/scripts/mission_issue.py --phase 1     # Phase 전체
python3 .claude/skills/study-workflow/scripts/mission_issue.py M1-1 --dry-run
```

- 제목 `[M1-1] 미션 제목`, 라벨 `mission`·`phase-1`·`L1`, 마일스톤은 Phase README 첫 줄(주차 표기 제외)이다.
- 같은 미션 번호의 이슈가 이미 있으면(닫힌 것 포함) 건너뛴다. 다시 만들 필요가 있으면 기존 이슈를 사용자에게 보여주고 확인받는다.
- Phase를 시작할 때 `--phase N`으로 한 번에 만들면 마일스톤 진행률로 Phase 진척을 볼 수 있다.

## 2. 실습: 미션 브랜치

이슈 본문의 "작업 브랜치" 이름을 그대로 쓴다. 이 이름 형식(`phase{P}/m{P}-{N}-{slug}`)을 PR 스크립트와 리뷰 워크플로가 인식한다.

```bash
git switch main && git pull
git switch -c phase1/m1-1-money
```

이 단계에서 Claude는 코드를 대신 쓰지 않는다. 막혔다는 요청에는 mission-review 스킬의 힌트 규칙(파일:줄 + 질문, 3회 막히면 API 이름까지)을 따른다.

## 3. PR 생성

1. 학습자에게 메모 4개를 받는다: 구현 요약, 설계 결정과 이유, 가장 자신 없는 부분(파일:줄), TIL 링크. 학습자가 쓰지 않은 내용을 Claude가 지어내지 않는다. 비어 있으면 "(작성 필요)"로 둔다.
2. 메모를 scratchpad의 notes.md에 `### 구현 요약` 형식 그대로 저장한다.
3. 본문을 먼저 보여준다: `mission_pr.py --dry-run --notes <notes.md>`
   - 시나리오 대응표에 `❌ 없음`이 있으면 PR을 만들기 전에 학습자에게 알린다. `@DisplayName`에 `#번호`가 빠졌거나 테스트가 실제로 없는 경우다.
   - 테스트 결과에 실패가 있으면 Draft로 만들지(`--draft`) 학습자에게 묻는다.
4. 확인받은 뒤 실행: `mission_pr.py --notes <notes.md>` → 브랜치 push, PR 생성(`Closes #이슈`로 머지 시 이슈 자동 종료).
5. 커밋을 Claude가 만들 때는 사용자 명의와 `[type] 한글 설명` 형식을 따르고, AI 작성 표기를 넣지 않는다.

L3 미션은 `workspace/docs/test-scenarios/M{P}-{N}.md`가 있으면 스크립트가 PR 본문에 접어서 첨부한다. 구현 전에 시나리오 표만 리뷰받고 싶으면 그 파일만 커밋해서 `--draft`로 PR을 연다.

## 4. 리뷰

PR이 열리면 두 리뷰어가 자동으로 붙는다.

| 리뷰어 | 설정 파일 | 보는 것 |
|---|---|---|
| CodeRabbit | `.coderabbit.yaml` | 줄 단위 코드 품질: 금액 타입, 예외 처리, 테스트 경계값 |
| Claude | `.github/workflows/claude-review.yml` | 미션 문서 기준: 시나리오 대응, 불변식, 동시성, 완료 기준 (mission-review 스킬 형식) |

- 리뷰를 반영해 push한 뒤 PR 댓글에 `@claude 지적 1~3번 반영했어, 다시 봐줘`처럼 쓰면 Claude가 다시 답한다. CodeRabbit은 push마다 자동으로 증분 리뷰를 한다.
- 로컬 Claude Code 세션에서 리뷰받을 때는 mission-review 스킬을 쓴다(GitHub 리뷰와 기준이 같다).
- 테스트를 바꿨으면 `mission_pr.py --update --notes <notes.md>`로 PR 본문의 테스트 결과·대응표를 갱신한다.

## 5. 머지

머지 조건: CI 통과, PR 본문 완료 기준 전부 체크, Claude 리뷰의 "반드시 고칠 것" 전부 해결.
조건을 확인한 뒤 `gh pr merge <번호> --squash --delete-branch`가 아니라 `--merge`를 쓴다. 테스트 커밋이 구현 커밋보다 먼저라는 기록(완료 기준 항목)이 main 히스토리에 남아야 하기 때문이다.
머지 후 README 진행 현황의 해당 미션 체크박스를 체크하고, 리뷰에서 반복된 실수를 `til/weakness.md`에 추가하도록 제안한다.

## 사전 준비 (레포 관리자가 1회, 외부 서비스라 Claude가 대신 할 수 없음)

| 항목 | 방법 |
|---|---|
| CodeRabbit | https://github.com/apps/coderabbitai 에서 이 레포에 설치 (공개 레포 무료) |
| Claude GitHub App | https://github.com/apps/claude 에서 이 레포에 설치 |
| Claude 토큰 | 로컬에서 `claude setup-token` → 레포 Secrets에 `CLAUDE_CODE_OAUTH_TOKEN` 등록 |

## 에러 처리

| 상황 | 대응 |
|---|---|
| `미션 브랜치가 아님` | 현재 브랜치 이름을 보여주고 `git branch -m phase{P}/m{P}-{N}-{slug}`를 제안한다 |
| `(연결할 이슈 없음)` | `mission_issue.py M{P}-{N}`으로 이슈를 만든 뒤 `--update`로 본문을 다시 생성한다 |
| `Gradle workspace를 찾지 못함` | workspace에 `gradlew`가 있는지 확인한다. M0-2 이전 미션은 `--skip-tests`를 쓴다 |
| Claude 리뷰 job이 인증 오류 | Secrets의 `CLAUDE_CODE_OAUTH_TOKEN` 등록 여부와 Claude App 설치 여부를 확인하라고 안내한다 |
