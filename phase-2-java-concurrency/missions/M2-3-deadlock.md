# M2-3 이체와 데드락

> 가이드 수준: L2 · 예상 시간: 4~6h · 선행: M2-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- A→B와 B→A 동시 이체로 데드락을 재현하고, 테스트 JVM을 멈추게 하지 않는 격리된 테스트(`./gradlew deadlockDemo`)로 감지한다.
- `jstack` 출력에서 `Found one Java-level deadlock:` 절을 찾아, 어느 스레드가 어느 모니터를 쥐고 무엇을 기다리는지 TIL에 적는다.
- `AccountNumber` 오름차순 락 순서로 데드락을 없애고, 계좌 10개·이체 1,000건에서 총액 10,000,000원이 보존됨을 테스트로 보여준다.
- 같은 계좌 이체를 `SameAccountTransferException`으로 거절하는 규칙을 테스트로 고정한다.

## 배경
M2-2에서는 계좌 하나만 잠갔다. 이체는 출금 계좌와 입금 계좌 2개를 함께 잠가야 출금과 입금 사이에 다른 스레드가 끼어들지 못한다. 그런데 A→B 이체가 A를 잠그고 B를 기다리는 동안 B→A 이체가 B를 잠그고 A를 기다리면 두 스레드 모두 영원히 멈춘다. 은행에서 이 상태는 해당 계좌의 모든 입출금 요청이 응답 없이 쌓이는 장애가 된다. 이 미션은 데드락을 일부러 만들고, 덤프로 진단하고, 락 순서 규칙으로 없앤다.

```
스레드1: A 잠금 → B 잠금 대기
스레드2: B 잠금 → A 잠금 대기   → 두 스레드 모두 영원히 대기 (데드락)
```

## 요구사항
1. **1단계 — 데드락 재현 (격리된 테스트)**
   - 테스트 전용 클래스에 아래 이체를 만든다. `Account`는 M2-2 1단계의 `synchronized` 버전이다.
     ```java
     void transfer(Account from, Account to, Money amount) {
         synchronized (from) {
             sleepOneMillisecond();       // 재현율을 높이는 지연
             synchronized (to) {
                 from.withdraw(amount);
                 to.deposit(amount);
             }
         }
     }
     ```
   - `sleepOneMillisecond()`는 `Thread.sleep(1)`을 호출하고, `InterruptedException`을 잡으면 인터럽트 플래그를 복구하는 테스트용 메서드다. 이 지연이 있으면 A를 쥔 스레드와 B를 쥔 스레드가 동시에 존재할 확률이 올라간다 (이 문서 작성 시 JDK 21.0.8·Gradle 8.14.3에서 5초 안에 데드락 감지 확인).
   - 계좌 A, B(각 1,000,000원). 작업 200개: 100개는 A→B, 100개는 B→A로 1원씩 1회. README 5절 틀로 동시에 출발시킨다.
   - 스레드는 데몬 스레드를 만드는 `ThreadFactory`로 생성한다 (`Executors.newFixedThreadPool(200, threadFactory)`, 팩토리 안에서 `setDaemon(true)`).
   - 감지: `done.await(5, TimeUnit.SECONDS)`가 `false`임을 단정한다. 5초 안에 200개가 모두 끝나면 이 테스트는 실패한다 (데드락이 재현되지 않음).
   - 이 테스트에 `@Tag("deadlock-demo")`를 붙인다. README "워크스페이스 만들기"의 `build.gradle.kts` 설정으로 `./gradlew test`에서는 제외되고 `./gradlew deadlockDemo`에서만 실행된다.
   - 격리하는 이유: `synchronized`에서 모니터를 기다리는 스레드는 `interrupt()`로 깨울 수 없다. `shutdownNow()`는 인터럽트만 보내므로 데드락 스레드는 JVM이 끝날 때까지 남는다. 데몬 스레드로 만들어야 테스트가 끝난 뒤 JVM이 종료된다. `assertTimeoutPreemptively`도 시간 초과 시 테스트 스레드를 버릴 뿐 데드락 스레드를 정리하지 못한다.
2. **2단계 — 스레드 덤프 분석**
   - `main` 메서드 클래스(`lab.bank.experiment.DeadlockDemo`)로 A→B 스레드 1개, B→A 스레드 1개를 만들어 데드락을 일으킨다. 스레드 이름을 `transfer-A-to-B`, `transfer-B-to-A`로 정한다. 첫 번째 `synchronized` 안에서 `Thread.sleep(200)`을 넣으면 매번 데드락이 난다.
   - 실행 중인 상태에서:
     ```bash
     jps -l                    # PID 확인 (lab.bank.experiment.DeadlockDemo 줄)
     jstack <PID>              # 스레드 덤프
     jcmd <PID> Thread.print   # 같은 정보, 다른 명령
     ```
   - 덤프의 `Found one Java-level deadlock:` 절과 그 아래 `Java stack information for the threads listed above:` 절을 TIL에 붙이고, 각 스레드에 대해 "쥐고 있는 모니터", "기다리는 모니터", "기다리는 코드 줄 번호"를 표로 정리한다.
   - IntelliJ 디버거의 "Get Thread Dump"(Debug 창 → 카메라 아이콘)로 같은 상태를 확인하고, `jstack` 출력과 다른 점 1가지를 적는다.
3. **3단계 — 락 순서로 해결**
   - `AccountNumber`가 `Comparable<AccountNumber>`를 구현한다. 순서는 계좌번호 문자열 순서다. 형식이 `XXX-XXXX-XXXX`(숫자, 자리수 고정)이므로 문자열 순서와 숫자 순서가 같다.
   - `BankService.transfer(AccountNumber from, AccountNumber to, Money amount, String memo)`는 두 계좌 중 `compareTo` 결과가 작은 계좌를 먼저 잠그고 큰 계좌를 나중에 잠근다.
   - 같은 계좌 이체(`from.equals(to)`)는 락을 잡기 전에 `SameAccountTransferException`(`BankException` 상속, `ErrorCode.SAME_ACCOUNT_TRANSFER`)을 던진다. 잔액과 `Ledger`는 바뀌지 않는다.
   - 1단계와 같은 부하(A→B 100개, B→A 100개, 1원씩)를 고친 `transfer`로 실행하면 `done.await(5, SECONDS) == true`이고 A + B = 2,000,000원이다. 이 테스트는 `@Tag` 없이 `./gradlew test`에서 실행한다.
4. **4단계 — 다수 계좌 랜덤 이체**
   - 계좌 10개(각 1,000,000원). 메인 스레드에서 `new Random(42)`로 이체 명령 1,000개를 미리 만든다: 출금·입금 계좌는 서로 다른 임의의 두 계좌, 금액은 1~100,000원 균등 분포 정수.
   - 플랫폼 스레드 1,000개가 명령 1개씩 동시에 실행한다. 잔액 부족(`InsufficientBalanceException`)은 실패로 집계하고 테스트를 실패시키지 않는다.
   - 검증: `done.await(10, SECONDS) == true`, 10개 계좌 잔액 합계 10,000,000원, 모든 잔액 ≥ 0원, 성공 건수 + 실패 건수 = 1,000, `Ledger`의 `TRANSFER_OUT` 합계 = `TRANSFER_IN` 합계 = 성공한 명령의 금액 합계.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 계좌 A, B 각 1,000,000원, 데몬 스레드 200개, `@Tag("deadlock-demo")` | 순서 없는 `transfer`로 A→B 100개, B→A 100개(1원씩) 동시 실행 | `done.await(5, SECONDS) == false` |
| 2 | `AccountNumber` `"110-0000-0002"`, `"110-0000-0010"` | `compareTo` | 첫 번째가 음수 반환 (`"110-0000-0002"`가 앞) |
| 3 | 같은 값의 `AccountNumber` 2개 | `compareTo` | 0 |
| 4 | 계좌 A, B 각 1,000,000원 | 락 순서 `BankService.transfer`로 A→B 100개, B→A 100개(1원씩) 동시 실행, `@RepeatedTest(50)` | `done.await(5, SECONDS) == true`, A + B = 2,000,000원 |
| 5 | 계좌 A 1,000,000원 | `transfer(A, A, 1,000원, "메모")` | `SameAccountTransferException`, A 잔액 1,000,000원, `Ledger`에 A의 거래 0건 |
| 6 | 계좌 10개 각 1,000,000원, `Random(42)` 명령 1,000개 | 스레드 1,000개 동시 실행, `@RepeatedTest(50)` | `done.await(10, SECONDS) == true`, 총액 10,000,000원, 모든 잔액 ≥ 0, `TRANSFER_OUT` 합계 = `TRANSFER_IN` 합계 = 성공 금액 합계 |

## 제약
- 데드락 재현 테스트(시나리오 1)는 반드시 데몬 스레드 + `@Tag("deadlock-demo")`로 만든다. 기본 `./gradlew test`에 섞이면 데드락 스레드가 테스트 JVM에 남는다.
- 락 순서는 `AccountNumber.compareTo`로만 정한다. `System.identityHashCode()`, `hashCode()`로 정하지 않는다.
- 이체 시 모든 검증(계좌 존재, 상태, 통화, 잔액)을 끝낸 뒤 잔액을 바꾼다. 출금 후 입금이 실패해서 한쪽만 바뀐 상태가 남으면 안 된다 (Phase 1 M1-3 시나리오 6과 같은 규칙).

## 힌트
<details>
<summary>힌트 1: 두 락의 순서 정하기</summary>

`from.compareTo(to) < 0`이면 (from, to), 아니면 (to, from) 순서로 잠근다. 잠그는 순서와 출금·입금 방향은 별개다. 잠근 뒤에도 출금은 항상 `from`, 입금은 항상 `to`에서 일어나는지 확인한다.
</details>

<details>
<summary>힌트 2: 시나리오 6의 기대값</summary>

이체는 돈을 계좌 사이에서 옮기기만 하므로, 어떤 명령이 성공하든 실패하든 총액은 10,000,000원이어야 한다. 성공 금액 합계는 구현 코드가 아니라 테스트에서 성공한 명령의 금액을 `AtomicLong`이나 `LongAdder`로 따로 더해 구한다.
</details>

## 완료 기준
- [ ] `./gradlew deadlockDemo`가 `BUILD SUCCESSFUL`로 끝난다 (시나리오 1 통과, 실행 시간 약 5초)
- [ ] `./gradlew test`에서 시나리오 2~6이 통과하고, 시나리오 1은 실행되지 않는다 (테스트 리포트에 없음)
- [ ] TIL에 `jstack` 출력의 `Found one Java-level deadlock:` 절과 표(열: `스레드 이름`, `쥐고 있는 모니터`, `기다리는 모니터`, `코드 줄 번호`)가 있다

## 생각해볼 질문
1. 데드락 4조건 중 락 순서 방식은 어떤 조건을 깨는가? 다른 조건 하나를 깨는 방법을 설명해 보자 (M2-4의 `tryLock`이 깨는 조건).
2. 계좌번호 대신 `System.identityHashCode()`로 순서를 정하면 어떤 문제가 생기는가? 두 객체의 값이 같을 때 순서를 정하는 추가 규칙(tie-breaker)이 없으면 무슨 일이 생기는가?
3. Phase 5에서 두 트랜잭션이 `SELECT ... FOR UPDATE`로 계좌 행을 A→B, B→A 순서로 잠그면 MySQL은 어떻게 반응할까? JVM과 다른 점을 예측해 적어 두자.
