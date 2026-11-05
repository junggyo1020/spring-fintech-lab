# M2-3 이체와 데드락

## 배경
이체는 **두 계좌를 동시에** 잠가야 한다. A→B 이체와 B→A 이체가 동시에 일어나면?

```
스레드1: A 잠금 → (B 잠금 대기...)
스레드2: B 잠금 → (A 잠금 대기...)   → 영원히 대기 (데드락)
```

## 과제

### 1단계: 데드락 재현
```java
void transfer(Account from, Account to, Money amount) {
    synchronized (from) {
        synchronized (to) {
            from.withdraw(amount);
            to.deposit(amount);
        }
    }
}
```
- 계좌 A, B. 스레드 100개는 A→B, 100개는 B→A로 1원씩 이체
- 테스트가 **멈추는 것**을 확인 (`assertTimeoutPreemptively` 또는 `done.await(5, SECONDS)`의 반환값으로 감지)

### 2단계: 스레드 덤프 분석
- `main` 메서드로 데드락 상황을 만들고 실행해둔 상태에서:
  ```bash
  jps                  # PID 확인
  jstack <PID>         # 스레드 덤프
  ```
- 덤프에서 `Found one Java-level deadlock:` 부분을 찾아 TIL에 붙여넣고 해석하기
- IntelliJ의 디버거 "Get Thread Dump" 기능으로도 확인

### 3단계: 락 순서로 해결
- **항상 계좌번호가 작은 쪽을 먼저 잠근다**
- 같은 계좌로 이체(`from == to`)는 어떻게 처리할지 결정 (예외? 무시?)
- 1단계 테스트가 5초 안에 끝나고, **A + B 총액이 보존**되는지 검증

### 4단계: 다수 계좌 랜덤 이체
- 계좌 10개 (각 1,000,000원), 스레드 1,000개가 임의의 두 계좌 간 임의 금액 이체
- 검증:
  - 데드락 없음 (제한 시간 안에 종료)
  - **10개 계좌 총액 = 10,000,000원** (돈이 생기거나 사라지지 않음)
  - 모든 계좌 잔액 ≥ 0
  - `Ledger`의 TRANSFER_OUT 합계 == TRANSFER_IN 합계

## 생각해볼 질문
1. 데드락 4조건 중 락 순서 방식은 어떤 조건을 깨는가? 다른 조건을 깨는 방법도 하나 설명해보자.
2. 계좌번호 대신 `System.identityHashCode()`로 순서를 정하는 방법의 문제점은? (해시 충돌 시 tie-breaker)
3. DB에서도 같은 데드락이 생길까? (Phase 5에서 MySQL로 재현할 예정 — 예측만 적어두기)
