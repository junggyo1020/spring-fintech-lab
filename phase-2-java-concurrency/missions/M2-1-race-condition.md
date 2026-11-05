# M2-1 Race condition 재현하기

## 목표
"동시성 버그는 있다"를 말로 아는 것과 **눈으로 보는 것**은 다르다. 버그를 일부러 만들고, 그 버그를 **확정적으로 잡아내는 테스트**를 작성한다.

## 과제

### 1단계: 카운터
- `UnsafeCounter` — `int count; void increment() { count++; }`
- 스레드 100개가 각각 1,000번 `increment()` → 기대값 100,000
- 테스트: 실제 값이 100,000보다 **작음**을 확인 (= 버그 재현 테스트)
- `javap -c`로 `increment()`의 바이트코드를 보고, `count++`가 몇 개의 명령어인지 TIL에 적기

### 2단계: 계좌 출금 lost update
- Phase 1의 `Account`를 그대로 사용
- 잔액 1,000,000원, 스레드 100개가 동시에 10,000원씩 출금
- 기대: 잔액 0원, 성공 100건
- 실제로 어떤 결과가 나오는지 **10번 돌려서** 기록
- 재현이 잘 안 되면 `withdraw` 내부의 "읽기"와 "쓰기" 사이에 `Thread.sleep(1)` 또는 `Thread.yield()`를 넣어 **경쟁 구간을 넓혀보기** (테스트용 훅을 어떻게 넣을지 고민)

### 3단계: 가시성 문제
```java
class Worker implements Runnable {
    private boolean stopped = false;      // volatile 없음
    public void stop() { stopped = true; }
    public void run() { long n = 0; while (!stopped) { n++; } }
}
```
- 메인 스레드에서 1초 후 `stop()` 호출 → 워커가 멈추는지 확인 (JIT 최적화 때문에 안 멈출 수 있다)
- `volatile`을 붙이면 어떻게 되는가
- ⚠️ 루프 안에 `System.out.println`을 넣으면 재현이 안 될 수 있다. 왜일까?

## 검증 기준
- [ ] 1단계: 버그를 재현하는 테스트 (`isLessThan(100_000)`) 작성
- [ ] 2단계: 10회 실행 결과표 (잔액, 성공 건수) TIL에 기록
- [ ] 3단계: volatile 유무에 따른 동작 차이 기록

## 생각해볼 질문
1. 재현 테스트가 "가끔 통과"한다면 그 테스트는 쓸모 있는가? 동시성 버그 재현율을 높이는 방법은?
2. 2단계에서 잔액이 **기대보다 큰** 경우와 **음수**인 경우가 각각 가능한가? 어떤 인터리빙에서?
3. Phase 1에서 `Money`를 불변으로 만든 게 여기서 도움이 됐는가, 아니면 상관없었는가? (힌트: 불변인 건 `Money`지 `Account.balance` 참조가 아니다)
