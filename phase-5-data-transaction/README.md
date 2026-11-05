# Phase 5 — 데이터 접근 & 트랜잭션 & DB 락 (3주)

## 학습 목표
- JDBC → JdbcTemplate → JPA 순으로 올라가며 **각 추상화가 무엇을 숨기는지** 안다.
- `@Transactional`의 동작 원리(프록시 + `PlatformTransactionManager` + 스레드 로컬 커넥션)를 설명한다.
- Phase 2에서 메모리로 겪은 lost update를 **DB에서 다시 재현**하고, DB 수준 해법들을 비교한다.

## 주제
| 주 | 주제 |
|---|---|
| 1주 | Docker로 MySQL 띄우기, Flyway 마이그레이션, 순수 JDBC로 계좌 저장 → JdbcTemplate → Spring Data JPA. 영속성 컨텍스트, 1차 캐시, 더티 체킹, 연관관계, N+1, Testcontainers |
| 2주 | `@Transactional` 전파(REQUIRED/REQUIRES_NEW/NESTED), 롤백 규칙(checked 예외는 기본 커밋!), readOnly, self-invocation, 격리 수준별 이상현상(dirty read, non-repeatable read, phantom) 직접 재현 |
| 3주 | Lost update 재현 → ① `SELECT ... FOR UPDATE`(비관) ② `@Version`(낙관) + 재시도 ③ `UPDATE account SET balance = balance - ? WHERE id = ? AND balance >= ?`(원자적 조건부 업데이트) 비교. MySQL 데드락 재현 및 `SHOW ENGINE INNODB STATUS` 분석, 인덱스와 락 범위, `EXPLAIN` |

## 미션 (상세 문서는 Phase 4 완료 후 작성)
- **M5-1 JDBC 맨손 구현**: `Connection`, `PreparedStatement`, 트랜잭션 직접 관리(`setAutoCommit(false)`) → 반복 코드 체감
- **M5-2 JPA 전환**: 계좌/거래내역 엔티티 매핑, Flyway 스키마, Testcontainers 통합 테스트
- **M5-3 N+1 사냥**: 계좌 목록 + 최근 거래 조회에서 N+1 재현 → fetch join / `@EntityGraph` / batch size 비교
- **M5-4 트랜잭션 함정 모음**: 전파, checked 예외 롤백, self-invocation, `private` 메서드, 트랜잭션 안 외부 API 호출 — 각각 테스트로 재현
- **M5-5 격리 수준 실험실**: 두 커넥션을 수동으로 번갈아 실행해 각 이상현상 재현 (MySQL REPEATABLE READ의 갭 락까지)
- **M5-6 DB 동시성 3종 비교**: 100 동시 출금 테스트를 세 가지 방식으로 통과시키고 처리량·실패율·재시도 횟수 비교표 작성
- **M5-7 DB 데드락**: A→B, B→A 이체로 MySQL 데드락 재현, 원인 분석, 락 순서/재시도로 해결

## 완료 기준
- [ ] "`@Transactional`만 붙이면 동시성이 해결된다"가 **틀린 이유**를 테스트로 보여줄 수 있다
- [ ] 비관/낙관/원자적 UPDATE 중 상황별로 무엇을 고를지 근거를 댈 수 있다
- [ ] InnoDB 데드락 로그를 읽고 어떤 쿼리가 어떤 락을 기다렸는지 설명할 수 있다
