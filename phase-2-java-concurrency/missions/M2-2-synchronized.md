# M2-2 `synchronized`로 계좌 보호

> 가이드 수준: L2 · 예상 시간: 3~4h · 선행: M2-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `synchronized`로 `Account`를 보호해, M2-1 2단계 시나리오가 "성공 100건, 잔액 0원"으로 50회 반복 모두 통과함을 테스트로 보여준다.
- 잔액보다 많은 출금이 동시에 들어와도 성공 33건, 실패 17건, 잔액 1,000원이 정확히 나오는 테스트를 작성한다.
- 전역 락·계좌별 락·락 없음 3버전의 소요 시간과 정합성을 README 6절 규칙으로 측정해 표로 비교한다.
- `Ledger` 동시 `append`가 깨지는 것을 재현하고, 선택한 보호 방식과 그 비용(예: 복사 횟수)을 수치로 설명한다.

## 배경
M2-1에서 잔액 읽기와 쓰기 사이에 다른 스레드가 끼어들어 출금이 사라지는 것을 봤다. 실제 은행에서 이 버그는 고객 잔액보다 많은 금액이 출금되는 사고로 이어진다. `synchronized`는 한 객체의 모니터를 한 번에 한 스레드만 갖게 해서 3단계(읽기·계산·쓰기)를 하나로 묶는다. 락을 어느 객체에 거느냐(락 범위)에 따라 처리량이 크게 달라지므로, 이 미션은 정합성과 함께 락 범위별 소요 시간을 측정한다.

## 요구사항
1. **1단계 — 계좌 단위 동기화**
   - `Account.deposit(Money)`, `Account.withdraw(Money)`, `Account.balance()`를 `synchronized` 메서드로 바꾼다. 검증 규칙(금액 0 이하 → `InvalidAmountException`, 잔액 부족 → `InsufficientBalanceException` 등)은 Phase 1과 같다.
   - M2-1 2단계 테스트를 "성공 100건, 실패 0건, 최종 잔액 0원"을 단정하는 테스트로 바꾸고 `@RepeatedTest(50)`을 붙인다.
2. **2단계 — 잔액보다 많은 동시 출금**
   - 잔액 100,000원, 스레드 50개가 동시에 `withdraw(Money.won(3_000))`을 1회씩 호출한다.
   - 성공 33건, `InsufficientBalanceException` 17건, 최종 잔액 1,000원. 실행 중 어느 시점에도 잔액이 음수가 되지 않는다.
   - 계산: 100,000 ÷ 3,000 = 33 나머지 1,000 → 성공 33건, 실패 50 − 33 = 17건, 잔액 100,000 − 33 × 3,000 = 1,000원.
3. **3단계 — 락 범위 실험** (`lab.bank.experiment` 패키지, README 6절 측정 규칙 적용)
   - 실험용 인터페이스 하나를 만들고 3가지로 구현한다.
     ```java
     public interface DepositService {
         void deposit(AccountNumber number, Money amount);
         Money balanceOf(AccountNumber number);
     }
     ```
   - 3구현 모두 1단계 이전의 동기화 없는 계좌 복사본(`PlainAccount`: `deposit`, `balance`만 있음)을 `Map<AccountNumber, PlainAccount>`에 담아 쓴다. 맵은 스레드 시작 전에 모두 채우고 이후 수정하지 않는다.

     | 버전 | 락 |
     |---|---|
     | A | `DepositService` 구현의 두 메서드 모두 `synchronized` (서비스 객체 하나에 전역 락) |
     | B | 메서드 안에서 `synchronized (account)` (계좌별 락) |
     | C | 락 없음 (비교 기준) |

   - 작업 W1: 계좌 1,000개, 플랫폼 스레드 1,000개. 스레드 i는 계좌 i에만 1원 입금을 100회. 기대 총액 100,000원, 계좌별 100원.
   - 작업 W2: 계좌 1개, 플랫폼 스레드 1,000개. 모든 스레드가 그 계좌에 1원 입금을 100회. 기대 총액 100,000원.
   - 각 (버전, 작업) 조합을 워밍업 3회 + 측정 5회 실행하고 중앙값을 기록한다. 매 회차 새 계좌로 시작한다.
4. **4단계 — `Ledger` 동시성**
   - 스레드 100개가 동시에 같은 계좌번호의 서로 다른 `Transaction`(ID가 모두 다름)을 1,000건씩 `Ledger.append` → 기대 `history(계좌번호)` 크기 100,000건.
   - 보호 전 `Ledger`로 실행해 결과(크기가 100,000보다 작음, 또는 `ArrayIndexOutOfBoundsException` 같은 예외)를 5회 기록한다.
   - `Collections.synchronizedList`, `ConcurrentHashMap` + `CopyOnWriteArrayList`, `synchronized` 메서드 중 하나를 골라 고친다. 고른 이유를 아래 비용과 함께 TIL에 적는다.
     - `CopyOnWriteArrayList`는 `add`마다 내부 배열 전체를 새 배열로 복사한다 (원소 n개일 때 O(n)). 한 계좌에 100,000건을 넣으면 복사되는 원소 참조 수는 1 + 2 + … + 100,000 = 5,000,050,000개다. 거래내역처럼 쓰기가 계속 쌓이는 목록에 이 비용을 감수할지 결정한다.
     - `Collections.synchronizedList`는 개별 메서드만 동기화한다. 반복(iteration)이나 복사 중에는 리스트 객체에 직접 `synchronized`를 걸어야 한다 (`Collections.synchronizedList` Javadoc).
   - 고친 뒤 같은 테스트가 `@RepeatedTest(50)`에서 50회 모두 크기 100,000이다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 잔액 1,000,000원, 스레드 100개 | 동시에 `withdraw(10,000원)` 1회씩, `@RepeatedTest(50)` | 성공 100건, 실패 0건, 잔액 0원 |
| 2 | 잔액 100,000원, 스레드 50개 | 동시에 `withdraw(3,000원)` 1회씩, `@RepeatedTest(50)` | 성공 33건, `InsufficientBalanceException` 17건, 잔액 1,000원 |
| 3 | 2와 같음 | 각 스레드가 출금 직후 `balance()` 조회 | 조회한 50개 값 모두 0원 이상 |
| 4 | 잔액 0원, 스레드 100개 | 동시에 `deposit(1,000원)` 1회씩, `@RepeatedTest(50)` | 잔액 100,000원 |
| 5 | 보호한 `Ledger`, 스레드 100개, 계좌번호 1개 | 각 스레드가 같은 계좌의 `Transaction`을 `append` 1,000건, `@RepeatedTest(50)` | `history(계좌번호).size() == 100,000`, 같은 거래 ID 중복 0건 |

## 제약
- 3단계 측정은 테스트가 아니라 `main` 메서드로 실행한다 (README 6절 1번).
- `synchronized` 블록 안에서 로깅·`Thread.sleep`·외부 호출을 하지 않는다. 락을 쥔 시간만큼 다른 스레드가 기다린다.
- 동시성 테스트는 README 5절 틀을 따르고 `done.await(10, SECONDS)`의 반환값을 단정한다.

## 힌트
<details>
<summary>힌트 1: W1에서 버전 C가 정합성 "일치"로 나오는 이유</summary>

W1에서는 스레드 하나가 계좌 하나만 건드린다. 두 스레드가 같은 계좌를 동시에 바꾸는 경우가 없으면 lost update도 없다. 그렇다면 메인 스레드가 결과를 읽을 때 최신 값이 보인다는 보장은 무엇이 해 주는가? (`Thread.join()`, `ExecutorService.close()`가 만드는 happens-before 관계를 확인한다)
</details>

<details>
<summary>힌트 2: `synchronized` 메서드와 `synchronized (this)`</summary>

`synchronized` 인스턴스 메서드는 `this`의 모니터를 쓴다. 버전 B에서 `synchronized (account)`를 쓰면 1단계의 `Account`와 같은 모니터를 쓰게 되는가? JLS 8.4.3.6 "synchronized Methods"를 확인한다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~5가 `@RepeatedTest(50)`으로 50회 모두 통과한다
- [ ] TIL에 3단계 측정표가 있다. 표 위에 JDK 버전·CPU 코어 수·OS를 적고, 열은 `버전`, `작업(W1/W2)`, `소요 시간 중앙값(ms)`, `최소(ms)`, `최대(ms)`, `최종 총액(원)`, `기대 총액(원)`, `정합성(일치/불일치)`이다. 행은 3버전 × 2작업 = 6행이다
- [ ] TIL에 4단계 보호 전 5회 결과와, 선택한 보호 방식·이유(`CopyOnWriteArrayList` 복사 비용 포함)가 있다

## 생각해볼 질문
1. `balance()` 조회에도 `synchronized`가 필요한 이유는 원자성인가, 가시성인가? `Money`가 불변이라는 사실이 답을 바꾸는가?
2. `synchronized` 메서드 안에서 콜백·로깅·네트워크 호출을 하면 생기는 위험 2가지를 적어 보자 (락 보유 시간, 다른 락과의 순서).
3. 전역 락(버전 A)이 맞는 선택인 상황이 있는가? Phase 7 매칭 엔진이 종목별 전용 스레드 1개로 명령을 처리하는 이유와 연결해 보자.
