# M2-5 Atomic/CAS와 낙관적 동시성

## 목표
락을 걸지 않고 **"바꾸기 직전에 아무도 안 바꿨는지 확인하고, 바뀌었으면 재시도"** 하는 방식을 익힌다.
이 아이디어는 Phase 5의 JPA `@Version`(낙관적 락)과 정확히 같은 원리다.

## 과제

### 1단계: 카운터 3종 비교
- `AtomicInteger`, `LongAdder`, `synchronized` 카운터
- 스레드 수 1 / 4 / 16 / 64에서 각 1,000만 회 증가 → 처리 시간 측정표
- 왜 `LongAdder`가 고경합에서 빠른지 조사해서 TIL에 적기

### 2단계: CAS 기반 계좌
- `AtomicReference<Money> balance`로 잔액 관리
- `withdraw`를 `compareAndSet` 루프로 구현:
  ```
  loop:
    current = balance.get()
    if current < amount → InsufficientBalanceException
    next = current - amount
    if balance.compareAndSet(current, next) → 성공, 종료
    else → 재시도
  ```
- ⚠️ `compareAndSet`은 **참조 동등성(==)** 으로 비교한다. `Money`의 `equals`가 아니다. 이게 문제가 되는가?
- 재시도 횟수를 측정하는 카운터를 달고, 경합 정도에 따라 재시도가 얼마나 늘어나는지 관찰
- M2-2의 2단계 테스트(잔액 부족 동시 출금)를 통과시키기

### 3단계: 버전 기반 낙관적 업데이트
- `record AccountState(Money balance, long version)`를 `AtomicReference`로 관리
- 업데이트 시 version + 1
- 최대 재시도 N회 후 실패하면 `OptimisticLockFailureException`
- **이체는 이 방식으로 할 수 있을까?** 두 계좌를 원자적으로 바꿔야 하는데 CAS는 변수 하나만 다룬다. 시도해보고 한계를 정리

### 4단계: ABA 문제
- ABA 문제가 무엇인지 조사하고, 계좌 잔액 시나리오로 예를 만들어보기
- `AtomicStampedReference`로 해결하는 예제 작성
- 3단계의 version 필드가 ABA를 막는 원리 설명

## 검증 기준
- [ ] 1단계 성능표
- [ ] 2단계 CAS 계좌가 동시 출금 테스트 통과
- [ ] 3단계 재시도 초과 시 예외 발생 테스트
- [ ] 이체에 CAS를 쓰기 어려운 이유 정리

## 생각해볼 질문
1. 비관적(락) vs 낙관적(CAS) — 충돌이 드문 경우/잦은 경우 각각 무엇이 유리한가?
2. 인기 계좌(예: 이벤트 상금 지급 계좌)에 수천 건이 몰리면 낙관적 방식은 어떻게 되나?
3. JPA의 `@Version`과 이 미션의 3단계는 어떤 점이 같고 어떤 점이 다를까? (예측)
