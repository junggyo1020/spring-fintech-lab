# M5-6 트랜잭션 함정

> 가이드 수준: L2, 예상 시간: 6~8h, 선행: M5-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 롤백 규칙(unchecked/checked/`Error`/`rollbackFor`), self-invocation, 메서드 접근 제한자, 전파 속성(`REQUIRED`, `REQUIRES_NEW`, `NESTED`), `readOnly`의 동작을 각각 테스트 하나로 재현하고, 테스트가 끝난 뒤 계좌 잔액으로 커밋/롤백 여부를 판정한다.
- 내부 트랜잭션의 예외를 바깥에서 잡았는데도 `UnexpectedRollbackException`이 나는 경우와 나지 않는 경우를 구분해 테스트로 보여준다.
- `NESTED`가 `JpaTransactionManager`에서는 기본 설정으로 `NestedTransactionNotSupportedException`을 던지고, `DataSourceTransactionManager`에서는 savepoint로 동작함을 테스트로 보여준다.
- 트랜잭션 안에서 3초 걸리는 외부 호출이 커넥션 풀(최대 2개)을 고갈시키는 것을 재현하고, 외부 호출을 트랜잭션 밖으로 옮겨 해결한 결과를 테스트로 비교한다.

## 배경
`@Transactional`은 애너테이션 하나라서 "붙였으니 안전하다"고 믿기 쉽다. 실제로는 checked 예외를 던지면 커밋되고, 같은 클래스 안에서 부르면 트랜잭션이 아예 시작되지 않는다. 금융 시스템에서 이것은 "한도 초과 예외를 던졌는데 출금은 커밋됐다", "롤백된 줄 알았던 이체 실패 로그 테이블 기록까지 사라졌다" 같은 사고가 된다.
Phase 3 M3-5에서 AOP self-invocation을 재현했다. `@Transactional`도 같은 프록시 구조라서 같은 문제가 생긴다 (README 4절).
M5-4에서 만든 JPA 환경과 Testcontainers를 그대로 쓴다.

## 요구사항
1. **실험용 패키지 `lab.bank.txlab`.** 아래 빈을 만든다. 이름은 바꿔도 되지만 역할은 하나씩 분리한다 (전파 실험의 바깥/안쪽 메서드는 **서로 다른 빈**이어야 한다).
   - `RollbackRuleLab`: 롤백 규칙 실험 (시나리오 1~6)
   - `SelfInvocationLab`: self-invocation, `private`, package-private 실험 (시나리오 7~8)
   - `PropagationOuter`, `PropagationInner`: 전파 실험 (시나리오 9~13)
   - `ReadOnlyLab`: `readOnly` 실험 (시나리오 15~16)
   - `NotifyingTransferService` + 인터페이스 `NotificationClient`: 외부 호출 실험 (시나리오 17~18)
2. **"입금 1,000"의 정의.** 실험 메서드가 계좌를 바꿀 때는 `JdbcTemplate`으로 `UPDATE account SET balance = balance + 1000 WHERE number = ?` 한 문장을 실행한다 (시나리오 6, 15는 예외로 JPA를 쓴다). 결과는 테스트가 끝난 뒤 새 트랜잭션에서 잔액을 읽어 판정한다.
3. **실험용 예외.** `lab.bank.txlab.LabCheckedException extends Exception`. unchecked 예외는 `IllegalStateException`을 쓴다.
4. **트랜잭션 상태 기록.** 각 실험 메서드는 실행 중 `TransactionSynchronizationManager.isActualTransactionActive()` 값을 테스트가 읽을 수 있게 남긴다 (방법 자유: 반환값, 필드, 리스트 등).
5. **`NotificationClient`.** `void notifyTransfer(TransferResult result)`. 테스트에서는 호출될 때마다 `Thread.sleep(3000)` 하는 구현을 빈으로 등록한다.
   - `NotifyingTransferService.transferAndNotifyInside(TransferCommand)`: 하나의 `@Transactional` 안에서 M5-4 `JpaTransferEngine.transfer` 호출 후 알림 호출
   - `NotifyingTransferService.transferAndNotifyAfter(TransferCommand)`: 이체 트랜잭션이 커밋된 뒤 알림 호출 (방법은 직접 고른다)
6. **`NESTED` 실험 (시나리오 13).** Spring Boot가 자동 등록한 트랜잭션 매니저는 `JpaTransactionManager`다. `DataSourceTransactionManager`는 **빈으로 등록하지 않고** 테스트 안에서 `new DataSourceTransactionManager(dataSource)`로 만들어 `TransactionTemplate` 두 개(바깥 `REQUIRED`, 안쪽 `NESTED`)와 함께 쓴다. `PlatformTransactionManager` 빈을 하나 더 등록하면 Boot의 자동 설정 `JpaTransactionManager`가 빠진다.
7. **커넥션 풀 크기 실험.** 시나리오 11은 `spring.datasource.hikari.maximum-pool-size=1`, 시나리오 17~18은 `=2`로, 둘 다 `spring.datasource.hikari.connection-timeout=1000`을 테스트 클래스의 `@TestPropertySource`로 준다.

## 테스트 시나리오
모든 시나리오의 준비: 계좌 A = `110-0000-0001` 잔액 100,000, B = `110-0000-0002` 잔액 0. "A 최종"은 테스트 끝에 새 트랜잭션에서 읽은 값이다. "활성"은 실험 메서드 안에서 기록한 `isActualTransactionActive()` 값이다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `@Transactional` 메서드 | 입금 1,000 → `IllegalStateException` | 예외 전파, A 최종 100000.00 (롤백) |
| 2 | `@Transactional` 메서드 | 입금 1,000 → `LabCheckedException` | 예외 전파, **A 최종 101000.00 (커밋)** |
| 3 | `@Transactional(rollbackFor = Exception.class)` | 입금 1,000 → `LabCheckedException` | 예외 전파, A 최종 100000.00 |
| 4 | `@Transactional` 메서드 | 입금 1,000 → `new Error("lab")` | 예외 전파, A 최종 100000.00 |
| 5 | `@Transactional` 메서드 | 입금 1,000 → `JdbcTemplate`으로 memo 101자 거래내역 INSERT를 try/catch로 잡고 정상 반환 | 예외 없음, A 최종 101000.00, 거래 행 0 (`JdbcTemplate`은 트랜잭션에 rollback-only 표시를 하지 않음) |
| 6 | `@Transactional` 메서드 | 입금 1,000 → `SpringDataAccountTransactionRepository.save(memo 101자 엔티티)`를 try/catch로 잡고 정상 반환 | 메서드 종료 시 `UnexpectedRollbackException`, A 최종 100000.00 (리포지토리의 `@Transactional`이 같은 트랜잭션에 참여했다가 rollback-only로 표시) |
| 7 | `SelfInvocationLab`의 트랜잭션 없는 public 메서드가 `this.inner()`(`@Transactional`) 호출 / 같은 구조로 `private` `@Transactional` 메서드 호출 | `inner`에서 입금 1,000 → `IllegalStateException` | 두 경우 모두 활성 `false`, 예외 전파, **A 최종 101000.00** (트랜잭션이 없어 autocommit으로 반영됨) |
| 8 | package-private `@Transactional` 메서드, 같은 패키지의 테스트가 주입받은 빈으로 직접 호출 | 입금 1,000 → `IllegalStateException` | 활성 `true`, A 최종 100000.00 (Spring Framework 6.0 이상, 클래스 기반 프록시) |
| 9 | 바깥 `REQUIRED` → 안쪽 `REQUIRED` (다른 빈) | 바깥 입금 1,000 → 안쪽 입금 1,000 후 `IllegalStateException` → 바깥이 잡고 정상 반환 | 바깥 메서드 호출이 `UnexpectedRollbackException`으로 끝남, A 최종 100000.00 |
| 10 | 바깥 `REQUIRED` → 안쪽 `REQUIRES_NEW` | (가) 9번과 같은 흐름 / (나) 안쪽 입금 1,000 성공 → 바깥이 `IllegalStateException` | (가) 예외 없음, A 최종 101000.00 (바깥만 커밋) / (나) 예외 전파, A 최종 101000.00 (안쪽만 커밋) |
| 11 | 커넥션 풀 최대 1개, 10번 (가)의 구조 | 바깥 메서드 호출 | 약 1,000ms 후 `CannotCreateTransactionException`(원인 사슬: Hibernate `JDBCConnectionException` → `SQLTransientConnectionException`), A 최종 100000.00. 소요 시간을 기록 |
| 12 | 바깥 `REQUIRED` → 안쪽 `NESTED` (Boot 기본 `JpaTransactionManager`) | 바깥 입금 1,000 → 안쪽 호출 | 안쪽 호출 시점에 `NestedTransactionNotSupportedException`, 바깥이 잡지 않으면 A 최종 100000.00 |
| 13 | 요구사항 6의 `DataSourceTransactionManager` + `TransactionTemplate` | (가) 바깥 입금 1,000 → 안쪽(`NESTED`) 입금 1,000 후 예외 → 바깥이 잡고 정상 종료 / (나) 안쪽도 정상 종료 | (가) A 최종 101000.00 (안쪽만 savepoint로 롤백) / (나) A 최종 102000.00 |
| 14 | 9번, 10번(가), 13번(가) 결과 | 세 결과를 한 표로 정리 | `docs/m5-6-propagation.md`에 "안쪽 예외를 바깥이 잡았을 때 A 최종": `REQUIRED` 100000.00 / `REQUIRES_NEW` 101000.00 / `NESTED` 101000.00 |
| 15 | `@Transactional(readOnly = true)`, JPA로 A 조회 | 10,000원 출금(도메인 메서드) 후 정상 반환 | `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` = `true`, `getEntityUpdateCount()` 0, A 최종 100000.00 |
| 16 | `@Transactional(readOnly = true)` | `JdbcTemplate`으로 입금 1,000 실행 | `TransientDataAccessResourceException`, 가장 깊은 원인은 `SQLException`(에러 코드 0, SQLState `S1009`, `Connection is read-only. Queries leading to data modification are not allowed.`). MySQL Connector/J가 읽기 전용 커넥션에서 UPDATE를 서버로 보내기 전에 막는다 (서버 에러 1792 `Cannot execute statement in a READ ONLY transaction`는 mysql CLI에서 `START TRANSACTION READ ONLY;` 후 UPDATE하면 볼 수 있다). Boot 4.1.2 + Connector/J에서 확인한 값이며, 실제 클래스와 에러 코드를 기록, A 최종 100000.00 |
| 17 | 커넥션 풀 최대 2개, 알림 3,000ms | `transferAndNotifyInside(A → B, 1,000)`을 스레드 3개에서 동시에 호출 | 2건 성공, 1건 `CannotCreateTransactionException` (약 1,000ms 만에 실패). A 최종 98000.00, B 최종 2000.00 |
| 18 | 17번과 같은 설정 | `transferAndNotifyAfter(A → B, 1,000)`을 스레드 3개에서 동시에 호출 | 3건 모두 성공, A 최종 97000.00, B 최종 3000.00. 알림 호출 시점에 `isActualTransactionActive()` = `false` |

계산식 (17번): 커넥션 2개를 두 요청이 3,000ms씩 점유 → 세 번째 요청은 1,000ms(`connection-timeout`) 안에 커넥션을 얻지 못함 → 성공 2건 × 1,000원 → A = 100,000 − 2,000 = 98,000.

## 제약
- 테스트 메서드, 클래스에 `@Transactional`을 붙이지 않는다: 테스트가 연 트랜잭션에 실험 메서드가 참여해 버려 커밋/롤백 결과를 관찰할 수 없다.
- 시나리오의 결과를 로그로 판단하지 않는다. 잔액, 예외 클래스, 활성 여부를 assert한다.
- 시나리오 17~18은 동시 출발을 위해 Phase 2 README 5절의 `CountDownLatch` 틀을 쓴다. 결과는 스레드별로 성공/예외 클래스를 모아 개수를 assert한다.
- `NotificationClient` 구현에서 `Thread.sleep` 시간을 줄여 테스트를 빠르게 만들지 않는다. 3,000ms(알림) > 1,000ms(커넥션 대기)라는 관계가 실험의 조건이다.

## 힌트
<details>
<summary>힌트 1: 6번과 9번이 같은 이유</summary>

`SimpleJpaRepository`의 메서드에도 `@Transactional`이 붙어 있다. 리포지토리 호출은 9번의 "안쪽 `REQUIRED` 빈 호출"과 구조가 같다.
`AbstractPlatformTransactionManager`의 `globalRollbackOnParticipationFailure` 속성 Javadoc을 읽고, 참여한 트랜잭션에서 예외가 프록시 밖으로 나갈 때 무엇이 표시되는지 확인한다.
</details>

<details>
<summary>힌트 2: 커밋 뒤에 실행하는 방법</summary>

Spring Framework Reference "Transaction Management" 장의 "Transaction-bound Events" 절(`@TransactionalEventListener`)과 `TransactionSynchronization.afterCommit()`을 읽는다.
트랜잭션 경계를 바깥 메서드에서 끊고, 이체 트랜잭션 메서드를 다른 빈에서 호출한 뒤 알림을 부르는 구조도 가능하다. 세 방법 중 알림이 실패했을 때 이체 결과가 어떻게 되는지 각각 적어 본다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "lab.bank.txlab.*"`에서 시나리오 1~18 테스트가 통과한다 (14번은 문서 확인)
- [ ] `docs/m5-6-propagation.md`에 시나리오 14 표, 시나리오 11, 16, 17의 실제 예외 클래스, 에러 메시지 첫 줄, 소요 시간이 있다
- [ ] `docs/m5-6-propagation.md`에 "외부 API 호출을 트랜잭션 밖으로 옮기면 생기는 새 문제"(알림 실패 시 이체는 이미 커밋됨)를 3줄 이내로 적었다

## 생각해볼 질문
1. Spring이 checked 예외를 기본으로 커밋하는 이유는 무엇인가? Spring Framework 6.2의 `rollbackOn = ALL_EXCEPTIONS` 설정을 이 프로젝트에 켠다면 어떤 시나리오의 결과가 바뀌나?
2. 이체 실패 이력을 감사 로그 테이블에 남기려고 `REQUIRES_NEW`를 쓴다고 하자. 시나리오 11의 결과를 근거로, 동시 요청이 풀 크기와 같아지면 어떤 일이 생기는지 설명한다.
3. Phase 6의 타행이체(M6-7)는 "DB 커밋은 됐는데 대외기관 응답이 타임아웃"인 경우를 다룬다. 시나리오 18처럼 외부 호출을 커밋 뒤로 옮겼을 때, 외부 호출이 실패하면 이미 커밋된 출금을 어떻게 처리해야 할까?
