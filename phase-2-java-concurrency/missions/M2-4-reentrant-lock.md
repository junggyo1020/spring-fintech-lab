# M2-4 `ReentrantLock`, `tryLock`, 타임아웃

## 목표
`synchronized`로는 할 수 없는 것들 — **기다리다 포기하기, 공정성, 조건 대기** — 을 익힌다.
실서비스에서 "무한정 기다리는 요청"은 장애다. 타임아웃은 선택이 아니라 필수다.

## 과제

### 1단계: `synchronized` → `ReentrantLock` 전환
- `Account`가 자신의 `ReentrantLock`을 갖도록 변경
- 반드시 `lock(); try { ... } finally { unlock(); }` 패턴
- M2-2, M2-3의 테스트가 그대로 통과해야 함 (리팩터링 안전망)

### 2단계: `tryLock` 타임아웃 이체
- `transfer(from, to, amount, Duration timeout)`
- 두 락을 모두 `timeout` 안에 얻지 못하면, 이미 얻은 락은 **해제**하고 `LockAcquisitionTimeoutException`
- 이 방식은 락 순서 없이도 데드락이 영구화되지 않는다 → 1단계의 락 순서를 **일부러 제거하고** 테스트해보자
- 이 경우 발생하는 **라이브락(livelock)** 가능성과 해결책(랜덤 백오프)을 실험

### 3단계: 공정성(fairness)
- `new ReentrantLock(true)` vs `false`
- 한 계좌에 스레드 100개가 경쟁할 때, 각 스레드의 락 획득 횟수 분포를 측정 (기아 상태가 생기는가?)
- 처리량(throughput) 차이 측정

### 4단계: `Condition` — 입금 대기 출금 (선택)
- `withdrawWhenAvailable(Money amount, Duration timeout)`: 잔액이 부족하면 입금될 때까지 기다렸다가 출금
- `Condition.await(timeout)` / `signalAll()` 사용
- 실제 은행에 이런 기능은 없지만, **생산자-소비자** 패턴과 `wait/notify`의 현대판을 익히는 연습

## 검증 기준
- [ ] 리팩터링 후 기존 테스트 전부 통과
- [ ] 타임아웃 이체: 락을 오래 잡고 있는 스레드가 있을 때 예외가 정해진 시간 안에 발생
- [ ] 타임아웃 실패 시 락이 누수되지 않음 (이후 다른 스레드가 정상적으로 락 획득)
- [ ] 공정성 실험 결과표

## 생각해볼 질문
1. `unlock()`을 `finally`에 안 넣으면 무슨 일이 생기나? `synchronized`는 왜 그런 걱정이 없나?
2. "재진입(reentrant)"이란? 재진입이 안 되는 락이라면 어떤 코드에서 문제가 생기나?
3. 타임아웃 값은 어떻게 정해야 하나? 너무 짧으면/길면 각각 어떤 문제가 생기나?
