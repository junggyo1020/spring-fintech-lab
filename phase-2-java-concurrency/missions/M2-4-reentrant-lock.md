# M2-4 `ReentrantLock`, `tryLock`, 타임아웃

> 가이드 수준: L2, 예상 시간: 4~5h, 선행: M2-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `Account`의 `synchronized`를 `ReentrantLock`으로 바꾸고, M2-2, M2-3 테스트가 수정 없이 통과함을 보여준다.
- 두 락을 제한 시간 안에 얻지 못하면 이미 얻은 락을 풀고 `LockAcquisitionTimeoutException`을 던지는 이체를 만들고, 예외 발생 시각과 락 누수 없음을 테스트로 보여준다.
- 락 순서 없이 `tryLock`만 쓸 때 생기는 라이브락을, 백오프 없음과 1~10ms 랜덤 백오프 두 버전의 측정표로 비교한다.
- 공정 락과 비공정 락의 처리량과 스레드별 획득 횟수 분포를 측정표로 비교한다.

## 배경
M2-3의 `synchronized` 이체는 락을 기다리기 시작하면 포기할 방법이 없다. 운영 중인 이체 서버에서 락을 오래 쥔 요청 하나가 생기면, 같은 계좌로 들어온 요청이 모두 응답 없이 쌓이고 스레드 풀이 바닥나 다른 계좌 요청까지 멈춘다. `ReentrantLock.tryLock(timeout)`은 정해진 시간만 기다리고 실패를 반환하므로, 서버가 "지금은 처리할 수 없다"는 응답을 정해진 시간 안에 돌려줄 수 있다. 이 미션은 M2-3의 락 순서 이체를 출발점으로, 기다림에 상한을 둔다.

## 요구사항
1. **1단계: `synchronized` → `ReentrantLock` 전환**
   - `Account`가 자기 `ReentrantLock`(비공정, `new ReentrantLock()`)을 하나 갖는다. 모든 잔액 접근은 `lock(); try { ... } finally { unlock(); }` 형태로 감싼다.
   - `BankService.transfer`는 M2-3과 같은 `AccountNumber` 오름차순으로 두 계좌의 락을 잡는다.
   - M2-2 시나리오 1~4, M2-3 시나리오 2~6 테스트를 한 줄도 고치지 않고 통과시킨다 (리팩터링 안전망).
2. **2단계: 타임아웃 이체**
   - `BankService.transfer(AccountNumber from, AccountNumber to, Money amount, String memo, Duration timeout)`을 추가한다.
   - 락 순서는 1단계와 같다. 첫 번째 락을 `tryLock(남은 시간)`으로 얻고, 두 번째 락은 `timeout`에서 이미 쓴 시간을 뺀 남은 시간으로 `tryLock`한다. 두 락을 모두 얻는 데 걸린 시간의 합이 `timeout`을 넘지 않는다.
   - 두 번째 락을 얻지 못하면 첫 번째 락을 풀고 `LockAcquisitionTimeoutException`(`BankException` 상속, `ErrorCode.LOCK_ACQUISITION_TIMEOUT`)을 던진다. 메시지에 마스킹한 두 계좌번호와 `timeout` 값을 넣는다. 잔액과 `Ledger`는 바뀌지 않는다.
   - `timeout`이 `null`, 0, 음수이면 `IllegalArgumentException`.
   - `tryLock` 대기 중 인터럽트되면 인터럽트 플래그를 복구하고 `LockAcquisitionTimeoutException`을 던진다 (원인 예외로 `InterruptedException`을 담는다).
3. **3단계: 락 순서 없는 `tryLock`과 라이브락** (`lab.bank.experiment`, README 6절 측정 규칙 적용)
   - 실험용 이체를 따로 만든다: 락 순서 없이 항상 `from` → `to` 순서로 잡는다. `from`은 `tryLock(남은 시간)`, `to`는 `tryLock()`(기다리지 않음)으로 시도하고, `to`를 얻지 못하면 `from`을 풀고 처음부터 다시 시도한다. 전체 제한 시간은 1초, 넘으면 `LockAcquisitionTimeoutException`.
   - 버전 X: 재시도 전 대기 없음. 버전 Y: 재시도 전 1~10ms 사이 균등 분포 랜덤 시간(`ThreadLocalRandom`, 밀리초 정수) 대기.
   - 부하: 계좌 A, B 각 1,000,000원, 플랫폼 스레드 200개(A→B 100개, B→A 100개, 1원씩 1회), 동시 출발.
   - 기록: 성공 건수, `LockAcquisitionTimeoutException` 건수, 전체 재시도 횟수(`LongAdder`로 집계), 전체 소요 시간. 매 회차 A + B = 2,000,000원인지 확인한다.
4. **4단계: 공정성** (`lab.bank.experiment`, README 6절 측정 규칙 적용)
   - `new ReentrantLock(true)`(공정)와 `new ReentrantLock(false)`(비공정) 각각에 대해: 플랫폼 스레드 100개가 동시에 출발해 2초 동안 "`lock()` → 1원 입금 → `unlock()`"을 반복한다.
   - 스레드별 획득 횟수를 배열에 기록하고, 전체 획득 횟수, 초당 획득 횟수(전체 ÷ 2), 스레드별 최소, 최대, 최대÷최소를 계산한다.
   - 이 실험에는 `lock()`을 쓴다. 인자 없는 `tryLock()`은 공정 락이어도 락이 비어 있으면 대기 중인 스레드를 무시하고 바로 획득한다 (`ReentrantLock.tryLock()` Javadoc).
5. **5단계 (선택, 완료 기준에 포함하지 않음): `Condition`으로 입금 대기 출금**
   - `withdrawWhenAvailable(Money amount, Duration timeout)`: 잔액이 부족하면 `Condition.await(남은 시간)`으로 기다리고, 입금 시 `signalAll()`로 깨운다. `timeout` 안에 잔액이 생기지 않으면 `InsufficientBalanceException`.
   - 실제 은행 기능이 아니라 생산자-소비자 패턴과 `wait/notify`의 대체 API를 연습하는 단계다.

## 테스트 시나리오

모든 시나리오에서 A의 계좌번호는 `110-0000-0001`, B는 `110-0000-0002`다 (A가 락 순서상 먼저).

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 1단계 전환 후 | M2-2 시나리오 1~4, M2-3 시나리오 2~6 실행 | 테스트 코드 수정 없이 전부 통과 |
| 2 | 계좌 A, B 각 1,000,000원, 별도 스레드가 A의 락을 쥐고 2초 유지 (락 획득 후 래치로 알림) | `transfer(A, B, 1,000원, "메모", 500ms)` | `LockAcquisitionTimeoutException`, 호출부터 예외까지 500ms 이상 1,000ms 미만, A, B 잔액 1,000,000원, `Ledger` 거래 0건 |
| 3 | 2와 같되 별도 스레드가 B의 락을 쥠 | `transfer(A, B, 1,000원, "메모", 500ms)` | `LockAcquisitionTimeoutException`, 예외 직후 A의 락이 잠겨 있지 않음 (`isLocked() == false`) |
| 4 | 3 직후, 별도 스레드가 B의 락을 해제 | `transfer(B, A, 1,000원, "메모", 500ms)` | 성공, A 1,001,000원, B 999,000원 (이전 실패에서 락 누수 없음) |
| 5 | 락을 쥔 스레드 없음 | `transfer(A, B, 1,000원, "메모", Duration.ZERO)` | `IllegalArgumentException` |
| 6 | 별도 스레드가 A의 락을 쥐고 2초 유지 | 이체 스레드가 `transfer(A, B, 1,000원, "메모", 5s)` 대기 중일 때 그 스레드에 `interrupt()` | `LockAcquisitionTimeoutException`(원인 `InterruptedException`), 이체 스레드의 인터럽트 플래그 `true` |

## 제약
- `unlock()`은 반드시 `finally` 안에서 호출한다. `lock()`/`tryLock()` 호출은 `try` 블록 밖(직전)에 둔다. `tryLock`이 `false`를 반환했다면 `unlock()`을 호출하지 않는다 (호출하면 `IllegalMonitorStateException`).
- 2단계 이체는 1단계 락 순서를 유지한다. 순서 없는 버전은 3단계 실험 클래스에만 둔다.
- 3단계, 4단계 측정은 `main` 메서드로 실행한다 (README 6절).

## 힌트
<details>
<summary>힌트 1: 남은 시간 계산</summary>

시작 시각을 `System.nanoTime()`으로 잡고, 두 번째 `tryLock` 직전에 `timeout.toNanos() - (현재 - 시작)`을 남은 시간으로 쓴다. 남은 시간이 0 이하이면 `tryLock(0, NANOSECONDS)`는 기다리지 않고 바로 결과를 반환한다. `System.currentTimeMillis()`는 시스템 시계 조정의 영향을 받으므로 경과 시간 측정에 쓰지 않는다.
</details>

<details>
<summary>힌트 2: 3단계에서 버전 X가 느린 이유</summary>

A→B 스레드가 A를 잡고 B를 시도하는 순간 B→A 스레드가 B를 잡고 A를 시도하면, 둘 다 실패하고 둘 다 즉시 다시 같은 순서로 시도한다. 스레드는 계속 실행 중인데 진행이 없는 상태가 라이브락이다. 랜덤 대기는 두 스레드의 재시도 시점을 어긋나게 만든다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~6이 통과한다
- [ ] TIL에 3단계 측정표가 있다. 표 위에 JDK 버전, CPU 코어 수, OS, 열은 `버전(X/Y)`, `성공 건수`, `타임아웃 건수`, `전체 재시도 횟수`, `소요 시간 중앙값(ms)`, `A + B(원)`이다
- [ ] TIL에 4단계 측정표가 있다. 열은 `락 종류(공정/비공정)`, `전체 획득 횟수`, `초당 획득 횟수`, `스레드별 최소`, `스레드별 최대`, `최대÷최소`이고, 각 값은 측정 5회의 중앙값이다

## 생각해볼 질문
1. `unlock()`을 `finally`에 넣지 않으면 예외가 났을 때 무슨 일이 생기는가? `synchronized`는 왜 같은 문제가 없는가?
2. 재진입(reentrant)이 안 되는 락이라면 `transfer` 안에서 `Account.withdraw`(같은 락을 다시 잡음)를 호출할 때 무슨 일이 생기는가?
3. 타임아웃 값은 무엇을 기준으로 정해야 하는가? 너무 짧을 때와 너무 길 때 각각 사용자와 서버에 생기는 문제를 적어 보자. Phase 4에서 `LockAcquisitionTimeoutException`을 HTTP 응답으로 바꾼다면 어떤 상태 코드가 맞을까?
