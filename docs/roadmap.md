# 주차별 로드맵 (27.5주)

주 10~15시간 기준이다. 아래 "예상 시간"은 각 미션 문서 메타 줄의 예상 시간을 합한 범위이고, Phase README의 "주차별 계획"과 같은 배치다.
미션 목록·선행 관계·workspace 시작 방법은 [curriculum-map.md](curriculum-map.md)가 기준이다. 이 문서와 Phase README가 다르면 Phase README를 따르고, 이 문서를 고친다.

## 진행 규칙

- 한 주에 15시간을 쓰고도 미션이 남으면 남은 부분을 다음 주로 넘긴다. 미션을 건너뛰지 않는다.
- 각 주의 마지막 학습일(주말 3시간)은 PR 리뷰 반영, 그 주 TIL 다시 읽기, [레벨 진단](self-check.md) 해당 항목 답하기에 쓴다.
- Phase를 시작하는 날 `python3 .claude/skills/study-workflow/scripts/mission_issue.py --phase N`으로 그 Phase의 미션 이슈를 만든다. 마일스톤 진행률이 Phase 진척률이 된다. 진행 흐름 전체는 [study-method.md](study-method.md)의 "미션 진행 흐름"에 있다.
- 다음 Phase로 넘어가기 전에 Phase README의 "완료 기준"을 모두 체크한다.

## Phase 요약

| Phase | 기간 | 가이드 수준 | 미션 수 | 미션 예상 시간 합계 |
|---|---|---|---|---|
| [0 개발 환경](../phase-0-setup/README.md) | 0.5주 | L1 | 3 | 4~7h |
| [1 Java 기본기 + TDD](../phase-1-java-foundation/README.md) | 3주 | L1 | 5 | 24~36h |
| [2 Java 동시성](../phase-2-java-concurrency/README.md) | 3주 | L2 | 7 | 30~41h |
| [3 Spring Core](../phase-3-spring-core/README.md) | 2주 | L2 | 6 | 22~29h |
| [4 Web·API·보안](../phase-4-spring-web/README.md) | 3주 | L2 | 8 | 33~42h |
| [5 SQL·JPA·트랜잭션](../phase-5-data-transaction/README.md) | 4주 | L2 | 9 | 40~56h |
| [6 코어뱅킹](../phase-6-core-banking/README.md) | 4주 | L3 | 8 | 41~57h |
| [7 증권 매매](../phase-7-securities-trading/README.md) | 4주 | L3 | 8 | 46~54h |
| [8 분산·운영](../phase-8-advanced/README.md) | 4주 | L3 | 7 | 44~58h |

## 주차별 배치

| 누적 주 | Phase | 가이드 수준 | Phase 내 주차 | 미션 | 예상 시간 |
|---|---|---|---|---|---|
| 0~0.5 | [0 개발 환경](../phase-0-setup/README.md) | L1 | - | M0-1, M0-2, M0-3 | 4~7h |
| 0.5~1.5 | [1 Java 기본기 + TDD](../phase-1-java-foundation/README.md) | L1 | 1주 | M1-1, M1-4 | 8~12h |
| 1.5~2.5 | [1 Java 기본기 + TDD](../phase-1-java-foundation/README.md) | L1 | 2주 | M1-2, M1-3 | 10~14h |
| 2.5~3.5 | [1 Java 기본기 + TDD](../phase-1-java-foundation/README.md) | L1 | 3주 | M1-5 | 6~10h |
| 3.5~4.5 | [2 Java 동시성](../phase-2-java-concurrency/README.md) | L2 | 1주 | M2-1, M2-2, M2-3 | 10~14h |
| 4.5~5.5 | [2 Java 동시성](../phase-2-java-concurrency/README.md) | L2 | 2주 | M2-4, M2-5, M2-6 | 12~15h |
| 5.5~6.5 | [2 Java 동시성](../phase-2-java-concurrency/README.md) | L2 | 3주 | M2-7 | 8~12h |
| 6.5~7.5 | [3 Spring Core](../phase-3-spring-core/README.md) | L2 | 1주 | M3-1, M3-2, M3-3 | 11~14h |
| 7.5~8.5 | [3 Spring Core](../phase-3-spring-core/README.md) | L2 | 2주 | M3-4, M3-5, M3-6 | 11~15h |
| 8.5~9.5 | [4 Web·API·보안](../phase-4-spring-web/README.md) | L2 | 1주 | M4-1, M4-2, M4-3 | 12~15h |
| 9.5~10.5 | [4 Web·API·보안](../phase-4-spring-web/README.md) | L2 | 2주 | M4-4, M4-5 | 9~12h |
| 10.5~11.5 | [4 Web·API·보안](../phase-4-spring-web/README.md) | L2 | 3주 | M4-6, M4-7, M4-8 | 12~15h |
| 11.5~12.5 | [5 SQL·JPA·트랜잭션](../phase-5-data-transaction/README.md) | L2 | 1주 | M5-1, M5-2, M5-3 | 11~16h |
| 12.5~13.5 | [5 SQL·JPA·트랜잭션](../phase-5-data-transaction/README.md) | L2 | 2주 | M5-4, M5-5 | 10~13h |
| 13.5~14.5 | [5 SQL·JPA·트랜잭션](../phase-5-data-transaction/README.md) | L2 | 3주 | M5-6, M5-7 | 9~13h |
| 14.5~15.5 | [5 SQL·JPA·트랜잭션](../phase-5-data-transaction/README.md) | L2 | 4주 | M5-8, M5-9 | 10~14h |
| 15.5~16.5 | [6 코어뱅킹](../phase-6-core-banking/README.md) | L3 | 1주 | M6-1, M6-2 | 9~13h |
| 16.5~17.5 | [6 코어뱅킹](../phase-6-core-banking/README.md) | L3 | 2주 | M6-3, M6-4 | 11~15h |
| 17.5~18.5 | [6 코어뱅킹](../phase-6-core-banking/README.md) | L3 | 3주 | M6-5, M6-6 | 9~13h |
| 18.5~19.5 | [6 코어뱅킹](../phase-6-core-banking/README.md) | L3 | 4주 | M6-7, M6-8 | 12~16h |
| 19.5~20.5 | [7 증권 매매](../phase-7-securities-trading/README.md) | L3 | 1주 | M7-1, M7-2 | 11~13h |
| 20.5~21.5 | [7 증권 매매](../phase-7-securities-trading/README.md) | L3 | 2주 | M7-3, M7-4 | 13~15h |
| 21.5~22.5 | [7 증권 매매](../phase-7-securities-trading/README.md) | L3 | 3주 | M7-5, M7-6 | 12~14h |
| 22.5~23.5 | [7 증권 매매](../phase-7-securities-trading/README.md) | L3 | 4주 | M7-7, M7-8 | 10~12h |
| 23.5~24.5 | [8 분산·운영](../phase-8-advanced/README.md) | L3 | 1주 | M8-1, M8-2 | 11~15h |
| 24.5~25.5 | [8 분산·운영](../phase-8-advanced/README.md) | L3 | 2주 | M8-3, M8-5 요구사항 1~6 | 11~14h |
| 25.5~26.5 | [8 분산·운영](../phase-8-advanced/README.md) | L3 | 3주 | M8-4, M8-5 요구사항 7~9 | 12~15h |
| 26.5~27.5 | [8 분산·운영](../phase-8-advanced/README.md) | L3 | 4주 | M8-6, M8-7 | 10~14h |

상한이 15시간을 넘는 주는 2개다. 처리 방법은 각 Phase README의 "주차별 계획"에 적힌 그대로다.

| 주 | 상한 | 처리 |
|---|---|---|
| Phase 5 1주 | 16h | 15시간을 쓰고도 M5-3이 남으면 남은 부분을 Phase 5 2주로 넘긴다 (2주 상한 13h) |
| Phase 6 4주 | 16h | 15시간을 쓰고도 M6-8이 남으면 Phase 7 시작 전에 1~2일을 더 쓴다 |

Phase 8의 M8-5(6~8h)는 요구사항 1~6(메트릭·대시보드)과 7~9(트레이스·로그)로 나눠 각각 3~4h로 잡았다. 트레이스 요구사항은 M8-4 Saga 흐름을 대상으로 하므로 M8-4와 같은 주에 한다.

## Phase 대표 완료 기준

각 Phase README "완료 기준"의 한 항목을 원문 그대로 옮겼다. 나머지 항목은 README에서 확인한다.

| Phase | 대표 완료 기준 |
|---|---|
| 0 | PR을 열었을 때 GitHub Actions `ci` 워크플로가 초록 체크로 끝나고, 그 PR을 main에 머지했다 |
| 1 | `phase-1-java-foundation/workspace`에서 `./gradlew test jacocoTestReport jacocoTestCoverageVerification`이 `BUILD SUCCESSFUL`로 끝난다 |
| 2 | `./gradlew test`가 통과하고, M2-7의 반복 지정 시나리오가 `@RepeatedTest(100)`에서 100회 모두 통과한다 |
| 3 | M3-5의 self-invocation 재현 테스트가 "감사 로그 0건"을 단언하고, 고친 2가지 버전 테스트가 "감사 로그 3건"을 단언하며 모두 통과한다 |
| 4 | 모든 오류 응답이 `Content-Type: application/problem+json`이고 `type`, `title`, `status`, `detail`, `instance`, `code` 6개 필드를 가진다 (M4-8 테스트로 확인) |
| 5 | "`@Transactional`만 붙이면 동시성이 해결된다"가 틀렸음을 M5-8의 lost update 테스트(최종 잔액 > 0, 거래 행 100개)로 보여줄 수 있다 |
| 6 | M6-4의 동시성 테스트(핫 계좌 입금 1,000건, 랜덤 이체 10,000건)가 끝난 뒤 INV-1, INV-2가 성립한다 |
| 7 | 명령 10만 건 실행 후 전체 재생·스냅샷+꼬리 재생 두 방법으로 복구한 호가창 해시가 원본과 같다 (M7-8) |
| 8 | `docs/load-test-report.md`에 변경 1가지씩 최소 3회의 전후 측정 행이 있고, 마지막 행이 "500 req/s, p99 < 300ms, 에러율 < 0.1%"를 만족하거나 만족하지 못한 이유를 지표 값으로 적었다 |
