# M2-7 [종합] 스레드 안전한 이체 엔진

> 가이드 수준: L2 · 예상 시간: 8~12h · 선행: M2-4, M2-5, M2-6

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 가상 스레드 10,000개가 계좌 100개 사이에서 동시에 이체해도 총액 100,000,000원이 보존되고 데드락이 없는 `TransferEngine`을 테스트로 보여준다.
- 1일 이체 한도 5,000,000원이 동시 요청과 자정(Asia/Seoul) 경계에서 정확히 지켜짐을 테스트로 보여준다.
- 같은 `requestId`로 동시에 100건이 와도 실제 이체가 1건만 일어나고, 내용이 다른 요청은 `IdempotencyKeyConflictException`으로 거절됨을 테스트로 보여준다.
- 한 계좌쌍이 락을 2초 쥐고 있어도 다른 계좌쌍 이체가 100ms 안에 끝나고, 락 대기 3초 초과 시 `LockAcquisitionTimeoutException`이 남을 측정으로 보여준다.
- 공유 가변 상태와 보호 방식, 이 엔진의 한계를 `DESIGN.md`에 근거와 함께 기록한다.

## 배경
M2-1~M2-6에서 lost update, 데드락, 무한 대기, 스레드 풀 고갈을 하나씩 재현하고 고쳤다. 실제 이체 서버에서는 이 문제들이 한꺼번에 나온다. 고객 앱이 응답을 못 받고 같은 이체를 재시도하면 이중 출금이 되고, 한도 확인과 출금 사이에 다른 이체가 끼어들면 하루 한도를 넘는 금액이 빠져나간다. 이 미션은 Phase 2의 도구를 조합해 이 요구사항을 한 엔진에서 지키고, 그 설계 결정을 문서로 남긴다. 여기서 만든 `TransferEngine`, `TransferCommand`, `TransferResult`는 Phase 3에서 Spring 빈이 되고, Phase 4에서 이체 API 뒤에 놓인다.

## 요구사항
1. **인터페이스** (`lab.bank.transfer` 패키지, 시그니처는 그대로 쓴다)
   ```java
   public interface TransferEngine {
       TransferResult transfer(TransferCommand command);
       Money balanceOf(AccountNumber accountNumber);
       List<Transaction> historyOf(AccountNumber accountNumber);
   }

   public record TransferCommand(String requestId, AccountNumber from, AccountNumber to,
                                 Money amount, String memo) { }

   public record TransferResult(String requestId, String outTransactionId, String inTransactionId,
                                Money fromBalanceAfter, Money toBalanceAfter) { }
   ```
   - 계좌 등록·개설·입금·출금은 Phase 1 `BankService`의 메서드(`addAccount(Account)`, `openAccount(String, Currency)`, `deposit`, `withdraw`) 이름과 시그니처를 그대로 쓰고, 이체와 같은 계좌 락을 쓴다. 테스트 시나리오처럼 계좌번호를 정해서 만들 때는 `addAccount(Account.open(...))`를 쓴다. 계좌 저장소와 `Ledger`는 엔진 생성 시 넘겨받는다.
   - 엔진은 생성자로 `Clock`을 받는다. 거래 시각과 1일 한도의 날짜 계산은 이 `Clock`으로만 한다 (`LocalDateTime.now()` 직접 호출 금지).
   - 테스트용 훅: 생성자로 `TransferHook`을 받는다. 공개 생성자는 아무것도 하지 않는 훅을 넘긴다.
     ```java
     @FunctionalInterface
     public interface TransferHook {
         void afterLocksAcquired(TransferCommand command);   // 두 계좌 락을 모두 얻은 직후, 검증 전에 호출
     }
     ```
2. **처리 순서와 예외** (`transfer` 한 번의 흐름)
   1. `command` 또는 필드 중 `memo`를 제외한 값이 `null`이거나 `requestId`가 빈 문자열이면 `IllegalArgumentException`.
   2. 멱등성 확인 (아래 4번 규칙).
   3. `from.equals(to)`이면 `SameAccountTransferException`. 금액이 0 이하이면 `InvalidAmountException`.
   4. 두 계좌가 존재하지 않으면 `AccountNotFoundException`.
   5. `AccountNumber` 오름차순으로 두 계좌 락을 `tryLock`. 두 락을 얻는 데 쓰는 시간 합계 최대 3초. 넘으면 이미 얻은 락을 풀고 `LockAcquisitionTimeoutException` (M2-4 2단계 규칙).
   6. `TransferHook.afterLocksAcquired(command)` 호출.
   7. 검증: 계좌 상태(`AccountNotActiveException`) → 통화(`CurrencyMismatchException`) → 잔액(`InsufficientBalanceException`) → 1일 한도(`DailyTransferLimitExceededException`).
   8. 출금 계좌 `TRANSFER_OUT`, 입금 계좌 `TRANSFER_IN` 거래 2건을 `Ledger`에 추가하고 잔액을 바꾼다. 결과를 `TransferResult`로 반환하고 락을 푼다.
   - 새 예외 2개(`DailyTransferLimitExceededException`, `IdempotencyKeyConflictException`)는 `BankException`을 상속하고 `ErrorCode`에 `DAILY_TRANSFER_LIMIT_EXCEEDED`, `IDEMPOTENCY_KEY_CONFLICT`를 더한다. `LockAcquisitionTimeoutException`과 `LOCK_ACQUISITION_TIMEOUT`은 M2-4에서 만든 것을 재사용한다. 이 미션이 끝나면 `ErrorCode` 상수는 15개다 (M1-2 7개 + M1-3 4개 + M2-4 1개 + M2-5 1개 + 이 미션 2개).
3. **1일 이체 한도** (이 미션의 규칙으로 정한다. 실제 은행 한도는 상품·고객 등급마다 다르다)
   - 계좌별로 하루(Asia/Seoul 기준 00:00:00 ~ 23:59:59.999999999) 동안 성공한 `TRANSFER_OUT` 금액 합계가 5,000,000원을 넘을 수 없다. 합계가 정확히 5,000,000원이 되는 이체는 허용한다.
   - 입금·출금(`deposit`/`withdraw`)과 실패한 이체는 한도에 포함하지 않는다.
   - 날짜는 `LocalDate.now(clock)`(Clock의 zone은 `Asia/Seoul`)으로 정한다. 날짜가 바뀌면 누적 합계는 0부터 다시 센다.
   - 한도 확인과 출금은 출금 계좌 락을 쥔 상태에서 함께 일어나야 한다. 확인과 출금 사이에 같은 계좌의 다른 이체가 끼어들면 안 된다.
4. **멱등성**
   - 같은 `requestId`의 첫 요청 결과를 저장한다. 이후 같은 `requestId` 요청은 이체를 다시 실행하지 않는다.
   - 저장 대상: 성공(`TransferResult`)과 업무 실패(`InsufficientBalanceException`, `DailyTransferLimitExceededException`, `AccountNotActiveException`, `AccountNotFoundException`, `CurrencyMismatchException`, `SameAccountTransferException`, `InvalidAmountException`). 같은 `requestId`가 다시 오면 저장된 `TransferResult`를 반환하거나(첫 결과와 `equals`), 같은 예외 클래스를 다시 던진다.
   - 저장하지 않는 것: `LockAcquisitionTimeoutException`. 일시적 실패이므로 같은 `requestId`로 재시도하면 이체를 처음부터 실행한다.
   - 내용이 다른 요청: 같은 `requestId`인데 저장된 첫 요청의 `TransferCommand`와 `equals`가 아니면(계좌, 금액, 메모 중 하나라도 다름) `IdempotencyKeyConflictException`을 던지고 아무것도 바꾸지 않는다.
   - 처리 중인 요청: 첫 요청이 아직 끝나지 않았을 때 같은 `requestId`(내용 같음)가 오면, 두 번째 요청은 첫 요청이 끝날 때까지 최대 3초 기다렸다가 첫 요청과 같은 결과를 돌려준다. 3초 안에 끝나지 않으면 `LockAcquisitionTimeoutException`.
5. **비기능**
   - 서로 다른 계좌 간 이체는 서로 기다리지 않는다. 엔진 전체에 락 하나(전역 락)를 쓰지 않는다.
   - 데드락 없음: 시나리오 1, 9가 제한 시간 안에 끝난다.
   - `InterruptedException`을 삼키지 않는다 (M2-6 규칙).

## 테스트 시나리오

모든 시나리오의 `Clock`은 별도 언급이 없으면 `2026-03-02T10:00:00+09:00`(Asia/Seoul)에 고정한다. 동시성 시나리오는 README 5절 틀을 쓰고, 스레드는 `newVirtualThreadPerTaskExecutor()`로 만든다. 계좌번호는 A `110-0000-0001` < B `110-0000-0002` < C `110-0000-0003` < D `110-0000-0004` 순서다. 금액을 적지 않은 이체는 1원이다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 계좌 100개 각 1,000,000원, `new Random(7)`로 만든 명령 10,000개(서로 다른 두 계좌, 금액 1~10,000원 정수) | 가상 스레드 10,000개가 명령 1개씩 동시 실행 | `done.await(30, SECONDS) == true`, 총액 100,000,000원, 모든 잔액 ≥ 0원, 성공 + 실패 = 10,000 |
| 2 | 1 실행 직후 | 계좌 100개 각각 `Ledger.replayBalance` | 100개 모두 `balanceOf`와 같음 |
| 3 | 출금 계좌 S 10,000,000원, 입금 계좌 10개 각 0원 | S → 서로 다른 입금 계좌 10개로 1,000,000원씩 동시에 10건 | 성공 5건, `DailyTransferLimitExceededException` 5건, S 5,000,000원, 입금 계좌 잔액 합계 5,000,000원 |
| 4 | S 10,000,000원 | S→T 4,000,000원, S→T 1,000,000원, S→T 1원을 차례로 | 1·2번째 성공(누적 정확히 5,000,000원), 3번째 `DailyTransferLimitExceededException`, S 5,000,000원 |
| 5 | S 10,000,000원, Clock `2026-03-01T23:59:59+09:00`, 테스트에서 시각을 바꿀 수 있는 Clock | S→T 5,000,000원 → S→T 1원 → Clock을 `2026-03-02T00:00:00+09:00`으로 변경 → S→T 1,000,000원 | 1번째 성공, 2번째 `DailyTransferLimitExceededException`, 3번째 성공, S 4,000,000원 |
| 6 | A 1,000,000원, B 0원 | 같은 `requestId`·같은 내용으로 100건 동시 요청 (A→B 10,000원) | A 990,000원, B 10,000원, A의 `TRANSFER_OUT` 1건, 100개 `TransferResult`가 모두 `equals` |
| 7 | 6 직후 | 같은 `requestId`, 금액 20,000원으로 요청 | `IdempotencyKeyConflictException`, A 990,000원, B 10,000원 |
| 8 | A 1,000,000원, 훅이 `requestId = "r-8"`일 때 1초 대기 | 요청 1 시작, 훅 진입을 래치로 확인한 뒤 같은 `"r-8"` 요청 2 실행 | 요청 2가 요청 1 종료 후 반환, 두 결과 `equals`, A의 `TRANSFER_OUT` 1건 |
| 9 | A, B 각 1,000,000원 | A→B 5,000건, B→A 5,000건(1원씩, `requestId` 모두 다름) 동시 실행 | `done.await(10, SECONDS) == true`, A + B = 2,000,000원 |
| 10 | A, B, C, D 각 1,000,000원, 훅이 A→B 이체에서 2초 대기 | A→B 시작, 훅 진입을 래치로 확인한 직후 C→D 1원 이체 시작 | C→D가 시작부터 100ms 안에 성공 반환 |
| 11 | A, B, C 각 1,000,000원, 훅이 A→B 이체에서 4초 대기 | A→B 시작, 훅 진입 확인 직후 A→C 1원 이체 | A→C가 `LockAcquisitionTimeoutException`, 시작부터 예외까지 3,000ms 이상 3,500ms 미만, 예외 직후 C 잔액 1,000,000원 |
| 12 | 11 직후 A→B 종료 | 11과 같은 `requestId`로 A→C 1원 재요청 | 성공 (타임아웃은 멱등성 저장 대상이 아님), C 1,000,001원 |
| 13 | A 1,000,000원 | `transfer(A→A, 1,000원)` | `SameAccountTransferException`, A 1,000,000원, `Ledger`에 A 거래 0건 |
| 14 | A 1,000원 | `requestId = "r-14"`로 A→B 2,000원 → A에 10,000원 입금 → 같은 `"r-14"`로 A→B 2,000원 | 1·2회차 모두 `InsufficientBalanceException` (2회차는 이체를 다시 실행하지 않음), A 11,000원, `Ledger`에 A의 `TRANSFER_OUT` 0건 |

시나리오 3 계산: 1,000,000 × 5 = 5,000,000원(한도와 같으므로 5번째까지 허용) → 6번째부터 누적 6,000,000원 > 5,000,000원이므로 5건 실패. 출금 계좌 잔액이 10,000,000원이라 잔액 부족은 일어나지 않는다. S = 10,000,000 − 5,000,000 = 5,000,000원.
시나리오 5 계산: 3월 1일 누적 5,000,000원 → 1원 추가 시 5,000,001원 > 한도 → 실패. 3월 2일 누적 0원에서 1,000,000원 → 성공. S = 10,000,000 − 5,000,000 − 1,000,000 = 4,000,000원.
시나리오 1의 한도: 계좌당 평균 출금 이체 100건 × 평균 5,000.5원 ≈ 500,050원으로 한도 5,000,000원에 닿지 않는다. 한도 초과가 나와도 실패로 집계하고 총액 검증은 그대로 한다.

`@RepeatedTest(100)`: 시나리오 1, 3, 6, 9를 100회 반복해 100회 모두 통과한다. 시나리오 8, 10, 11, 12는 훅 대기(1~4초) 때문에 100회 반복하면 각각 100~400초가 걸리므로 `@RepeatedTest(5)`로 5회 반복한다.

## 제약
- 엔진 전체를 감싸는 락 하나(`synchronized` 메서드, 전역 `ReentrantLock`)를 쓰지 않는다. 시나리오 10이 이 제약을 검증한다.
- 1일 한도 확인과 잔액 변경 사이에 출금 계좌 락을 풀지 않는다.
- 멱등성 저장소는 항목을 지우지 않는다 (이 미션 범위에서 만료 정책은 없다. 메모리 증가는 `DESIGN.md` 5번 질문에서 다룬다).
- 시간은 주입받은 `Clock`으로만 읽는다. 경과 시간 측정(`System.nanoTime()`)은 예외다.

## 힌트
<details>
<summary>힌트 1: 처리 중인 요청을 기다리게 하는 구조</summary>

`ConcurrentHashMap.putIfAbsent(requestId, 처리 중 표시)`의 반환값이 `null`인 스레드만 이체를 실행하게 하면, 나머지 스레드는 무엇을 기다려야 하는가? 처리 중 표시로 `CompletableFuture<TransferResult>`를 넣으면 기다리는 쪽은 `get(남은 시간, MILLISECONDS)`을 쓸 수 있다. `computeIfAbsent`의 매핑 함수 안에서 이체 전체를 실행하면 같은 해시 버킷의 다른 키 갱신이 막힐 수 있다 (`ConcurrentHashMap.computeIfAbsent` Javadoc: 계산은 짧고 단순해야 한다).
</details>

<details>
<summary>힌트 2: 계좌별 하루 누적 합계 저장 위치</summary>

누적 합계를 계좌와 같은 락으로 보호하면 한도 확인과 출금이 같은 임계 구역에 들어간다. 날짜와 합계를 한 값 객체로 묶으면 "날짜가 바뀌었으면 0부터"를 한 곳에서 처리할 수 있다. `Ledger`를 매번 다시 합산하는 방식과 비교해 시나리오 1의 소요 시간이 어떻게 달라질지 예측해 본다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~14가 통과하고, 반복 지정(1, 3, 6, 9는 100회, 8, 10, 11, 12는 5회)이 모두 통과한다
- [ ] `workspace/DESIGN.md`가 아래 5개 질문에 각각 답한다 (A4 1~2쪽)
  1. 공유 가변 상태는 무엇이고, 각각 어떻게 보호했나?
  2. 락 순서는 어떻게 정했나? 같은 계좌 이체는?
  3. 한도 체크와 출금이 원자적으로 일어나도록 어떻게 했나? (체크 후 출금 사이에 다른 이체가 끼어들면?)
  4. 멱등성 키 저장소는 무엇을 썼나? (`ConcurrentHashMap.computeIfAbsent`? `putIfAbsent`? 처리 중인 요청은?)
  5. 이 엔진의 한계는? 서버를 2대로 늘리면 무엇이 깨지나? → 이게 Phase 5~8을 배우는 이유다
- [ ] 리뷰 요청 시 `./gradlew test` 출력, `DESIGN.md`, 가장 자신 없는 부분 1~2개를 함께 보낸다

## 생각해볼 질문
1. 멱등성 저장소에 업무 실패(잔액 부족)를 저장하기로 한 규칙은 맞는가? 고객이 입금한 뒤 같은 `requestId`로 재시도하면 실패가 그대로 반환되는데, 이것을 막으려면 클라이언트와 서버가 각각 무엇을 해야 하는가?
2. 시나리오 10에서 전역 락을 썼다면 C→D 이체는 몇 ms 뒤에 끝났을까? 계산해 보고, 실제로 전역 락 버전을 만들어 측정해 비교해 보자.
3. 서버를 2대로 늘리면 `ConcurrentHashMap` 멱등성 저장소와 계좌별 `ReentrantLock`은 각각 무엇을 보장하지 못하게 되는가? Phase 5(DB 락, 유니크 제약)와 Phase 6(Redis 분산락) 중 어느 쪽이 각각의 대안이 되는지 예측해 적어 두자.
