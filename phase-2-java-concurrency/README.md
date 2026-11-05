# Phase 2 — Java 동시성 (3주)

## 학습 목표
- 동시성 버그를 **재현 → 원인 설명 → 해결 → 테스트로 증명**하는 4단계를 체화한다.
- 원자성(atomicity), 가시성(visibility), 순서(ordering) 세 가지 문제를 구분해서 설명할 수 있다.
- `synchronized`, `volatile`, `ReentrantLock`, Atomic/CAS, 동시성 컬렉션 중 **상황에 맞는 도구**를 고른다.
- 데드락을 일부러 만들고, 스레드 덤프로 진단하고, 락 순서로 해결한다.

## 이 Phase의 결과물
Phase 1의 `Account`/`BankService`를 **수천 개의 스레드가 동시에 이체해도 정합성이 깨지지 않는** 이체 엔진으로 발전시킨다.

---

## 핵심 개념 정리

### 1. 동시성 문제의 3요소
| 문제 | 설명 | 예 | 해결 도구 |
|---|---|---|---|
| **원자성** | 여러 단계 연산이 중간에 끼어들림 | `balance = balance - amount` (읽기→계산→쓰기) | `synchronized`, Lock, CAS |
| **가시성** | 한 스레드의 쓰기가 다른 스레드에 안 보임 | `while (!stopped)` 무한루프 | `volatile`, `synchronized`, Lock |
| **순서** | 컴파일러/CPU가 명령어 순서를 바꿈 | double-checked locking 버그 | happens-before 규칙 |

### 2. Lost Update — 금융 동시성 버그의 원형
```
잔액 10,000원, 스레드 A와 B가 동시에 각각 3,000원 출금

A: 잔액 읽기 (10,000)
B: 잔액 읽기 (10,000)
A: 10,000 - 3,000 = 7,000 쓰기
B: 10,000 - 3,000 = 7,000 쓰기   ← A의 출금이 사라짐!

결과: 6,000원 출금됐는데 잔액 7,000원 (은행이 3,000원 손해)
```
이 패턴은 **메모리(Phase 2) → DB(Phase 5) → 분산 시스템(Phase 6, 8)** 에서 모양만 바뀌어 계속 나온다.

### 3. 도구 비교
| 도구 | 원자성 | 가시성 | 특징 |
|---|---|---|---|
| `volatile` | ❌ | ✅ | 단순 플래그용. `count++`에는 무용 |
| `synchronized` | ✅ | ✅ | 간단, 자동 해제. 타임아웃/공정성 없음 |
| `ReentrantLock` | ✅ | ✅ | `tryLock(timeout)`, 공정성, `Condition`. 반드시 `finally`에서 `unlock` |
| `AtomicLong` 등 | ✅(단일 변수) | ✅ | CAS 기반 락프리. 여러 변수를 함께 바꾸긴 어려움 |
| 불변 객체 | - | ✅(final) | 공유해도 안전. 가장 좋은 동시성 전략은 "공유하지 않거나 바꾸지 않기" |

### 4. 데드락 4조건 (모두 성립해야 발생)
1. 상호 배제 2. 점유 대기 3. 비선점 4. **순환 대기** ← 락 순서를 정해서 이걸 깬다

### 5. 동시성 테스트 기본 틀
동시성 테스트는 "여러 스레드를 **동시에 출발**시키고, **모두 끝날 때까지 기다린 후**, 불변식을 검증"한다.

```java
@Test
void concurrentWithdraw() throws InterruptedException {
    int threadCount = 100;
    ExecutorService executor = Executors.newFixedThreadPool(32);
    CountDownLatch ready = new CountDownLatch(threadCount);
    CountDownLatch start = new CountDownLatch(1);
    CountDownLatch done  = new CountDownLatch(threadCount);

    for (int i = 0; i < threadCount; i++) {
        executor.submit(() -> {
            ready.countDown();
            try {
                start.await();          // 모두 준비될 때까지 대기 → 동시에 출발
                // TODO: 테스트할 동작
            } catch (Exception e) {
                // TODO: 예외 집계
            } finally {
                done.countDown();
            }
        });
    }

    ready.await();
    start.countDown();                  // 출발!
    done.await(10, TimeUnit.SECONDS);
    executor.shutdown();

    // TODO: 불변식 검증 (예: 총액 보존, 잔액 >= 0)
}
```
> 이 틀은 **직접 타이핑**하고, 각 Latch가 왜 필요한지 TIL에 적자.
> 동시성 버그는 확률적이다. 한 번 통과했다고 안전한 게 아니다 → `@RepeatedTest(50)`도 활용.

---

## 워크스페이스
`phase-2-java-concurrency/workspace/`에 새 Gradle 프로젝트를 만들고, Phase 1의 도메인 코드를 **복사해서** 시작한다.
(Phase 1 코드는 원본으로 보존 — 나중에 비교하며 무엇이 바뀌었는지 보기 위해)

## 미션

| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M2-1](missions/M2-1-race-condition.md) | Race condition 재현하기 | 3~4h |
| [M2-2](missions/M2-2-synchronized.md) | `synchronized`로 계좌 보호 | 3~4h |
| [M2-3](missions/M2-3-deadlock.md) | 이체와 데드락 | 4~6h |
| [M2-4](missions/M2-4-reentrant-lock.md) | `ReentrantLock`, `tryLock`, 타임아웃 | 4~5h |
| [M2-5](missions/M2-5-cas.md) | Atomic/CAS와 낙관적 동시성 | 4~5h |
| [M2-6](missions/M2-6-executor-virtual-threads.md) | `ExecutorService`와 가상 스레드 | 4~5h |
| [M2-7](missions/M2-7-transfer-engine.md) | [종합] 스레드 안전한 이체 엔진 | 8~12h |

## 읽을거리
- 『자바 병렬 프로그래밍』 2장(스레드 안전성), 3장(객체 공유), 10장(활동성 위험)
- JLS 17.4 Memory Model — happens-before 규칙 부분만
- JEP 444 (Virtual Threads), JEP 491 (synchronized pinning 해소, JDK 24)

## 완료 체크리스트
- [ ] lost update를 의도적으로 재현하는 테스트를 작성했다
- [ ] 데드락을 재현하고 `jstack`으로 스레드 덤프를 떠서 원인을 찾았다
- [ ] 같은 문제를 3가지 다른 방법(synchronized / Lock / CAS)으로 풀고 성능을 비교했다
- [ ] M2-7 종합 테스트가 `@RepeatedTest(100)`에서도 100% 통과한다
