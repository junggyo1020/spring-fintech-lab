# M2-6 `ExecutorService`와 가상 스레드

## 목표
스레드를 직접 `new Thread()`로 만들지 않고 **스레드 풀**로 다루는 법, 그리고 Java 21의 **가상 스레드**를 익힌다.
Spring Boot의 Tomcat, `@Async`, 커넥션 풀이 모두 이 개념 위에 있다.

## 과제

### 1단계: 스레드 풀 종류
- `newFixedThreadPool`, `newCachedThreadPool`, `newSingleThreadExecutor`, `newVirtualThreadPerTaskExecutor`
- 각각 1만 개의 "100ms 대기 작업(`Thread.sleep(100)`)"을 제출했을 때 전체 소요 시간과 생성된 플랫폼 스레드 수 측정
- `ThreadPoolExecutor`를 직접 생성(core/max/queue/RejectedExecutionHandler)해보고, 큐가 꽉 차면 무슨 일이 생기는지 실험

### 2단계: `Future`와 `CompletableFuture`
- 이체 요청 1,000건을 비동기로 제출하고 결과(`Future<TransferResult>`)를 모아 성공/실패 집계
- `CompletableFuture`로 "잔액 조회 → 한도 조회 → 이체" 를 체이닝, 하나라도 실패하면 예외 처리
- 타임아웃: `orTimeout`, `completeOnTimeout`

### 3단계: 가상 스레드 + 락
- 외부 API 호출을 흉내내는 `Thread.sleep(50)`을 **락 안에서** 수행하는 이체를 가상 스레드 1만 개로 실행
- `synchronized` 버전과 `ReentrantLock` 버전 비교
- JDK 21에서 `-Djdk.tracePinnedThreads=full` 옵션으로 pinning 관찰 (JDK 24+는 JEP 491로 synchronized pinning이 해소됨 — 사용하는 JDK 버전에 따라 결과가 다를 수 있음을 기록)

### 4단계: 올바른 종료
- `shutdown()` vs `shutdownNow()`, `awaitTermination`
- try-with-resources로 `ExecutorService` 사용 (Java 19+)
- 인터럽트를 받은 작업이 올바르게 종료되도록 `InterruptedException` 처리 (삼키지 말 것!)

## 검증 기준
- [ ] 1단계 측정표 (풀 종류별 시간, 스레드 수)
- [ ] 2단계 비동기 이체 집계 테스트
- [ ] 3단계 관찰 결과 정리
- [ ] 프로젝트 전체에서 `catch (InterruptedException e) {}` 처럼 삼킨 곳이 없음

## 생각해볼 질문
1. 가상 스레드는 CPU 바운드 작업도 빠르게 해주나? 어떤 작업에 효과가 있나?
2. 가상 스레드 1만 개가 동시에 DB에 접근하면, 커넥션 풀(예: 10개)은 어떻게 되나?
3. Tomcat 기본 스레드 풀(200개)이 모두 사용 중일 때 들어온 요청은 어떻게 되나?
