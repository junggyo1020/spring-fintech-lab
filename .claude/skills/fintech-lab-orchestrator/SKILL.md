---
name: fintech-lab-orchestrator
description: spring-fintech-lab 커리큘럼 문서 작업 전체(구조 변경 → 미션 작성 → 기술·도메인 검증 → 수정 → 자동 검사)를 에이전트들로 조율한다. "커리큘럼 고도화", "Phase N 미션 전부 만들어줘", "전체 문서 검증하고 고쳐줘", "커리큘럼 업데이트", "버전 올려서 문서 갱신" 같은 여러 문서에 걸친 작업에 반드시 이 스킬을 사용할 것. 미션 1개 수정은 mission-authoring, 학습자 코드 리뷰는 mission-review를 직접 쓴다.
---

# Fintech Lab Orchestrator

## 실행 모드: 서브 에이전트 (파이프라인 + 팬아웃)

이 환경에는 팀 생성 도구가 없으므로 `Agent` 도구로 서브 에이전트를 호출한다. 에이전트끼리 직접 대화하지 않고, 결과는 `_workspace/` 파일로 주고받는다.
모든 Agent 호출에 `model: "opus"`를 지정한다. 에이전트 역할은 `.claude/agents/{name}.md` 파일을 프롬프트에 읽게 해서 전달한다.

## 에이전트 구성

| 에이전트 | 정의 파일 | subagent_type | 스킬 | 출력 |
|---|---|---|---|---|
| curriculum-architect | `.claude/agents/curriculum-architect.md` | general-purpose | mission-authoring, curriculum-verification | `docs/curriculum-map.md`, `_workspace/00_architect_change-plan.md` |
| mission-author (Phase별 1명) | `.claude/agents/mission-author.md` | general-purpose | mission-authoring, fintech-domain-facts | `phase-{P}-*/**`, `_workspace/{P}_author_report.md` |
| tech-verifier | `.claude/agents/tech-verifier.md` | general-purpose | curriculum-verification | `_workspace/{P}_tech_findings.md` |
| domain-verifier | `.claude/agents/domain-verifier.md` | general-purpose | curriculum-verification, fintech-domain-facts | `_workspace/{P}_domain_findings.md` |
| learning-reviewer | `.claude/agents/learning-reviewer.md` | general-purpose | mission-review | 대화 (이 오케스트레이터 밖에서 단독 사용) |

## 워크플로우

### Phase A: 준비 (리더가 직접)
1. 요청 범위를 정한다: 어떤 Phase, 신규 작성인지 수정인지.
2. `_workspace/`가 없으면 만든다 (`.gitignore`에 포함됨).
3. 현재 상태를 기록한다: `python3 .claude/skills/curriculum-verification/scripts/check_docs.py > _workspace/00_baseline_check.txt`

### Phase B: 구조 (구조 변경이 있을 때만)
curriculum-architect 1명을 실행한다. `docs/curriculum-map.md`가 바뀌면 Phase C의 입력이 된다.

### Phase C: 작성 (팬아웃)
Phase마다 mission-author를 1명씩 **동시에** 실행한다 (`run_in_background: true`).
각 프롬프트에 포함할 것: 담당 Phase 번호, 정의 파일 경로, 읽을 파일 목록, 이미 알려진 문제 목록(있으면), 출력 경로.
Phase끼리는 `docs/curriculum-map.md`의 클래스·미션 이름으로만 연결되므로 동시에 작성해도 충돌하지 않는다.

### Phase D: 검증 (팬아웃)
작성이 모두 끝나면 tech-verifier, domain-verifier를 동시에 실행한다. 대상은 Phase C에서 바뀐 파일 전체.
domain-verifier는 금융 규칙이 있는 Phase(1, 6, 7, 8)만 맡는다. 수정 권한을 주고, 문장 단위로 고치게 한다.

### Phase E: 통합 (리더가 직접)
1. 검사 스크립트를 다시 실행해 ERROR 0을 확인한다.
2. 각 `_workspace/*_findings.md`의 "확인 필요" 항목을 모아 사용자에게 보고한다.
3. README.md 진행 현황 체크박스와 Phase README 미션 표가 curriculum-map과 일치하는지 확인한다.
4. 커밋은 성격별로 나눈다 (하네스 / 구조 문서 / Phase별 미션). 커밋 명의는 레포 `git config`를 따른다.

## 데이터 흐름

```
[리더] → curriculum-architect → docs/curriculum-map.md
             │
             ├─→ mission-author(P0) ─┐
             ├─→ mission-author(P1) ─┤   phase-*/README.md, missions/*.md
             ├─→ ...                 ├─→ _workspace/{P}_author_report.md
             └─→ mission-author(P8) ─┘
                                     │
               ┌─────────────────────┴─────────────────────┐
               ↓                                           ↓
         tech-verifier                              domain-verifier
   _workspace/{P}_tech_findings.md          _workspace/{P}_domain_findings.md
               └─────────────────────┬─────────────────────┘
                                     ↓
                         [리더] check_docs.py → 커밋 → 보고
```

## 에러 핸들링

| 상황 | 처리 |
|---|---|
| 에이전트 1명 실패 | 같은 프롬프트로 1회 재실행. 재실패면 해당 Phase 없이 진행하고 최종 보고에 "Phase N 미작성" 명시 |
| 작성자와 검증자의 의견 충돌 | 삭제하지 않고 보고서에 양쪽 근거를 병기, 리더가 공식 문서로 판정 |
| check_docs.py ERROR가 남음 | 해당 파일만 mission-author에게 재작업 지시 (1회) |
| curriculum-map과 다른 클래스 이름 사용 | curriculum-map 기준으로 문서를 고친다 |

## 테스트 시나리오

### 정상 흐름
1. 사용자: "Phase 5 미션 전부 다시 써줘"
2. Phase A: baseline 검사 결과 저장
3. Phase C: mission-author(P5) 1명 실행 → README + M5-1~M5-9 작성, 자가 검사 ERROR 0
4. Phase D: tech-verifier가 Phase 5 검증 (domain-verifier는 금융 규칙 없음으로 생략)
5. Phase E: ERROR 0 확인, "확인 필요" 항목 보고, `[docs] Phase 5 미션 문서 재작성` 커밋

### 에러 흐름
1. Phase C에서 mission-author(P7)가 중간에 실패
2. 같은 프롬프트로 재실행 → 다시 실패
3. Phase 7 없이 Phase D 진행 (나머지 Phase만 검증)
4. 최종 보고에 "Phase 7 미션 미작성, 원인: {에러}" 명시, 사용자에게 재시도 여부 확인
