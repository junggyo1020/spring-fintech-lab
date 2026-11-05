# M2-2 `synchronized`로 계좌 보호

## 목표
가장 기본적인 모니터 락으로 M2-1의 버그를 고치고, **락의 범위(granularity)** 를 고민한다.

## 과제

### 1단계: 계좌 단위 동기화
- `Account.deposit`, `withdraw`, `balance()`를 `synchronized`로 보호
- M2-1의 2단계 테스트를 **"잔액 0, 성공 100건"을 검증하는 테스트**로 바꾸고 통과시키기
- `@RepeatedTest(50)`으로 반복

### 2단계: 잔액보다 많은 동시 출금
- 잔액 100,000원, 스레드 50개가 각각 3,000원 출금 시도
- 검증: 성공 33건, 실패(`InsufficientBalanceException`) 17건, 최종 잔액 1,000원
- **잔액이 절대 음수가 되지 않음**을 검증

### 3단계: 락 범위 실험 (`BankService`)
세 가지 버전을 만들어 비교한다.
| 버전 | 락 | 
|---|---|
| A | `BankService`의 모든 메서드 `synchronized` (전역 락) |
| B | 계좌별 `synchronized(account)` |
| C | 락 없음 (버그 버전, 비교 기준) |

- 계좌 1,000개, 스레드 1,000개가 **서로 다른 계좌**에 입금 100회씩 → 각 버전 소요 시간 측정
- 계좌 1개에 스레드 1,000개 → 소요 시간 측정
- 결과를 표로 TIL에 정리

### 4단계: `Ledger`도 안전한가?
- 여러 스레드가 동시에 `Ledger.append`를 호출하면? 내부 `ArrayList`/`HashMap`이 깨지는 걸 재현해보자
- `Collections.synchronizedList`, `ConcurrentHashMap` + `CopyOnWriteArrayList`, 또는 `synchronized` 중 무엇을 쓸지 결정하고 이유를 적기

## 검증 기준
- [ ] 1, 2단계 테스트가 `@RepeatedTest(50)` 통과
- [ ] 3단계 성능 비교표
- [ ] 4단계 `Ledger` 동시성 테스트 통과

## 생각해볼 질문
1. `balance()` 조회 메서드에도 `synchronized`가 필요한 이유는? (원자성? 가시성?)
2. `synchronized` 메서드 안에서 외부 메서드(콜백, 로깅, 네트워크 호출)를 호출하면 어떤 위험이 있나?
3. 전역 락(A)이 항상 나쁜가? 어떤 상황에서는 A가 오히려 맞는 선택일 수 있을까? (힌트: Phase 7 매칭 엔진)
