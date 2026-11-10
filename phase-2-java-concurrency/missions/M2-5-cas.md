# M2-5 Atomic/CAS와 낙관적 동시성

> 가이드 수준: L2 · 예상 시간: 4~5h · 선행: M2-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `AtomicInteger`, `LongAdder`, `synchronized` 카운터의 소요 시간을 스레드 1/4/16/64개에서 README 6절 규칙으로 측정해 표로 비교한다.
- `AtomicReference<Money>`의 `compareAndSet` 재시도 루프로 출금하는 계좌를 만들고, M2-2 2단계 시나리오(성공 33건, 실패 17건, 잔액 1,000원)를 통과시킨다.
- 버전 번호를 가진 상태 객체로 낙관적 업데이트를 구현하고, 재시도 한도를 넘으면 `OptimisticLockFailureException`이 나는 것을 결정적(deterministic) 테스트로 보여준다.
- ABA 문제를 단일 스레드 테스트로 재현하고, `AtomicStampedReference`에서는 같은 순서의 CAS가 실패함을 보여준다.

## 배경
M2-2~M2-4의 락은 "충돌할지 모르니 먼저 잠근다"는 비관적 방식이다. 충돌이 드문 계좌에서는 잠그고 푸는 비용과 대기 시간이 낭비가 된다. CAS(compare-and-set)는 잠그지 않고 "읽은 값이 그대로일 때만 새 값으로 바꾸고, 바뀌었으면 다시 읽어 재시도"한다. Phase 5의 JPA `@Version`도 같은 아이디어(버전을 비교하고 맞을 때만 교체)를 쓴다. 차이는 JPA가 이것을 `UPDATE ... SET ..., version = version + 1 WHERE id = ? AND version = ?` SQL로 실행하고, 영향받은 행 수가 0이면 낙관적 락 실패 예외를 던진다는 점이다. 이 미션은 M2-2에서 락으로 지킨 출금 규칙을 락 없이 지킨다.

## 요구사항
1. **1단계 — 카운터 3종 비교** (`lab.bank.experiment`, README 6절 측정 규칙 적용)
   - 카운터 3종: `AtomicInteger.incrementAndGet()`, `LongAdder.increment()`, `synchronized` 메서드 안의 `int` 증가.
   - 1회 측정 = 전체 10,000,000회 증가를 스레드 수로 똑같이 나눠 동시에 실행. 스레드 1개 × 10,000,000회, 4개 × 2,500,000회, 16개 × 625,000회, 64개 × 156,250회.
   - 매 측정 후 최종 값이 10,000,000인지 확인한다 (`LongAdder`는 `sum()`). 다르면 측정값을 버리고 원인을 찾는다.
   - `LongAdder`가 스레드 수가 많을 때 빠른 이유를 `LongAdder` Javadoc 클래스 설명과 `Striped64` 소스 주석에서 찾아 TIL에 3~5문장으로 적는다.
2. **2단계 — CAS 계좌** (`lab.bank.concurrency.CasAccount`)
   - 잔액을 `AtomicReference<Money>`로 갖는다. `deposit(Money)`, `withdraw(Money)`, `balance()`. 락(`synchronized`, `Lock`)을 쓰지 않는다.
   - `withdraw` 흐름 (의사 코드):
     ```
     반복:
       current = balance.get()
       current < amount 이면 → InsufficientBalanceException (잔액 변경 없음)
       next = current - amount
       balance.compareAndSet(current, next) 성공 → 종료
       실패 → 재시도 횟수 +1, 처음으로
     ```
   - 금액 검증(0 이하 → `InvalidAmountException`, 통화 다름 → `CurrencyMismatchException`)은 Phase 1 `Account`와 같다.
   - 재시도 횟수를 `LongAdder`로 세고 `long retryCount()`로 노출한다.
   - `compareAndSet`은 `Money.equals`가 아니라 참조 동등성(`==`)으로 비교한다. `get()`으로 얻은 참조를 그대로 `compareAndSet`의 기대값으로 넘기면 이것이 문제가 되는지, 값이 같은 새 `Money` 객체를 기대값으로 넘기면 어떻게 되는지 테스트로 확인해 TIL에 적는다.
3. **3단계 — 버전 기반 낙관적 업데이트** (`lab.bank.concurrency.VersionedAccount`)
   - `record AccountState(Money balance, long version)`을 `AtomicReference<AccountState>`로 관리한다. 성공한 변경마다 `version`이 정확히 1 오른다.
   - 생성자에서 `int maxRetries`(0 이상)를 받는다. 시도 횟수 = 첫 시도 1회 + 재시도 최대 `maxRetries`회. 모두 실패하면 `OptimisticLockFailureException`(`BankException` 상속, `ErrorCode.OPTIMISTIC_LOCK_FAILURE`)을 던지고 이 호출의 변경은 반영되지 않는다.
   - 테스트용 훅: 패키지 전용 생성자로 `AtomicReference<AccountState>`와 `compareAndSet` 직전에 호출되는 `Runnable`을 함께 받는다 (공개 생성자는 아무것도 하지 않는 `Runnable`을 넘긴다). 테스트는 같은 `AtomicReference`를 훅 안에서 `set`해 CAS 실패를 결정적으로 만든다. 훅 안에서 `VersionedAccount`의 메서드를 호출하면 훅이 다시 호출되어 끝나지 않으므로 호출하지 않는다.
   - 이체: `VersionedAccount` 2개 사이 이체를 CAS만으로 원자적으로 만들 수 있는지 시도한다. 출금 CAS 성공 후 입금 CAS 전에 다른 스레드가 두 계좌 잔액 합을 읽으면 무엇이 보이는지 테스트나 그림으로 보이고, 한계를 TIL에 적는다.
4. **4단계 — ABA 문제** (단일 스레드 테스트로 순서를 고정)
   - `AtomicLong` 잔액 10,000: 값 읽기(10,000) → 다른 작업이 5,000 출금 → 다른 작업이 5,000 입금 → 처음 읽은 10,000을 기대값으로 `compareAndSet(10_000, 9_000)` → `true`(중간 변경 2번을 감지하지 못함).
   - `AtomicStampedReference<Money>`로 같은 순서를 실행 → 처음 읽은 참조와 스탬프로 `compareAndSet` → `false`.
   - 3단계의 `version`이 ABA를 막는 원리를 TIL에 적는다. 잔액만 보는 출금에서 ABA가 실제 손실을 만드는지, 손실을 만드는 예(상태의 "이력"에 의존하는 결정)는 무엇인지 함께 적는다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `CasAccount` 잔액 100,000원, 스레드 50개 | 동시에 `withdraw(3,000원)` 1회씩, `@RepeatedTest(50)` | 성공 33건, `InsufficientBalanceException` 17건, 잔액 1,000원 |
| 2 | `CasAccount` 잔액 0원, 스레드 100개 | 동시에 `deposit(1,000원)` 1회씩, `@RepeatedTest(50)` | 잔액 100,000원, `retryCount() >= 0` (값은 출력해 TIL에 기록) |
| 3 | `VersionedAccount` 잔액 10,000원·version 0, `maxRetries = 3`, 훅이 매번 상태를 (잔액 + 1원, version + 1)로 교체 | `withdraw(1,000원)` | `OptimisticLockFailureException`, 훅 호출 4회, 최종 상태 잔액 10,004원·version 4 |
| 4 | `VersionedAccount` 잔액 0원·version 0, `maxRetries = 99`, 아무것도 안 하는 훅, 스레드 100개 | 동시에 `deposit(1,000원)` 1회씩, `@RepeatedTest(50)` | 예외 0건, 잔액 100,000원, version 100 |
| 5 | `VersionedAccount` 잔액 5,000원, `maxRetries = 3` | `withdraw(5,001원)` | `InsufficientBalanceException`, 잔액 5,000원, version 0 (재시도하지 않음) |
| 6 | `AtomicLong` 10,000 | 요구사항 4단계 순서 | `compareAndSet(10_000, 9_000) == true` |
| 7 | `AtomicStampedReference<Money>` 10,000원·스탬프 0 | 요구사항 4단계 순서 (변경마다 스탬프 +1) | 처음 읽은 참조·스탬프 0으로 `compareAndSet` → `false`, 현재 스탬프 2 |

시나리오 3 계산: 시도 4회(1 + 3) 각각 직전에 훅이 1원 입금 + version 1 증가 → 잔액 10,000 + 4 = 10,004원, version 0 + 4 = 4. 출금 1,000원은 반영되지 않는다.
시나리오 4 근거: 스레드마다 변경이 1회뿐이면, 한 스레드의 CAS가 실패하는 경우는 다른 스레드의 CAS가 성공했을 때뿐이다. 다른 스레드는 99개이므로 재시도는 최대 99회다.

## 제약
- `CasAccount`, `VersionedAccount`에 `synchronized`, `Lock`을 쓰지 않는다.
- `compareAndSet`을 쓴다. `weakCompareAndSet*` 계열은 값이 같아도 실패할 수 있어(spurious failure) 시나리오 4의 근거가 성립하지 않는다.
- CAS 실패 후 같은 `current` 값으로 다시 `compareAndSet`하지 않는다. 매 재시도마다 `get()`으로 새로 읽는다.
- 1단계 측정은 `main` 메서드로 실행한다 (README 6절).

## 힌트
<details>
<summary>힌트 1: `AtomicReference.updateAndGet`을 쓰지 않는 이유</summary>

`updateAndGet(UnaryOperator)`도 내부에서 CAS 재시도를 하지만, 함수가 재시도마다 여러 번 호출될 수 있어 부수효과가 없어야 한다 (`AtomicReference` Javadoc). 잔액 부족 시 예외를 던지는 것과 재시도 횟수를 세는 것을 함께 하려면 루프를 직접 쓰는 편이 동작을 확인하기 쉽다. 직접 루프와 `updateAndGet` 중 무엇을 썼는지, 이유와 함께 TIL에 적는다.
</details>

<details>
<summary>힌트 2: `AtomicStampedReference`의 비교 방식</summary>

`AtomicStampedReference.compareAndSet`도 참조는 `==`로 비교한다. 4단계에서 "처음 읽은 참조"를 변수에 저장해 두고, 5,000원 입금 후 만들어진 10,000원 `Money`는 다른 객체라는 점을 확인한다. 같은 실험을 `AtomicReference<Money>`로 하면 ABA가 재현되는지도 확인해 본다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~7이 통과한다
- [ ] TIL에 1단계 측정표가 있다. 표 위에 JDK 버전·CPU 코어 수·OS, 열은 `카운터`, `스레드 수`, `스레드당 증가 횟수`, `소요 시간 중앙값(ms)`, `최소(ms)`, `최대(ms)`, `최종 값`이고 3종 × 4 스레드 수 = 12행이다
- [ ] TIL에 2단계 참조 동등성 확인 결과, 3단계 CAS 이체의 한계, 4단계 ABA 설명이 있다

## 생각해볼 질문
1. 충돌이 드문 경우와 잦은 경우 각각 비관적(락) 방식과 낙관적(CAS) 방식 중 무엇이 유리한가? 시나리오 2에서 기록한 `retryCount()`를 근거로 들어 보자.
2. 이벤트 상금 지급 계좌 1개에 스레드 1,000개가 동시에 출금하면 `maxRetries = 3`인 `VersionedAccount`에서 몇 건이 `OptimisticLockFailureException`이 될지 예측하고, 실제로 실행해 비교해 보자.
3. Phase 5의 JPA `@Version`과 3단계 구현에서 같은 점(버전 비교 후 교체)과 다른 점(비교·교체가 일어나는 곳, 실패 감지 방법, 재시도 책임)을 예측해 적어 두자.
