# 레벨 진단

각 질문에 **말로(또는 글로) 설명**할 수 있으면 체크. 해당 Phase에서 80% 이상 체크되면
개념 학습은 가볍게 훑고 **미션만** 풀어도 된다. 단, 종합 미션(M*-5, M*-7 등)은 반드시 푼다.

## Phase 1 — Java
- [ ] `0.1 + 0.2 != 0.3`인 이유와 금융 계산에서 `BigDecimal`을 쓰는 이유
- [ ] `new BigDecimal("1.0").equals(new BigDecimal("1.00"))`의 결과와 이유
- [ ] `equals`만 재정의하고 `hashCode`를 안 하면 `HashSet`에서 무슨 일이 생기는가
- [ ] 불변 객체를 만드는 규칙 4가지 이상
- [ ] checked / unchecked 예외의 차이, 도메인 예외를 어떻게 설계하는가
- [ ] `record`가 자동으로 만들어주는 것들
- [ ] JUnit5 `@ParameterizedTest`를 써본 적이 있다

## Phase 2 — 동시성
- [ ] `count++`가 스레드 안전하지 않은 이유 (바이트코드 수준)
- [ ] `volatile`이 보장하는 것과 보장하지 않는 것
- [ ] 데드락 발생 4가지 조건, 그중 무엇을 깨는 게 가장 현실적인가
- [ ] `synchronized`와 `ReentrantLock`의 차이
- [ ] CAS가 무엇이고 ABA 문제란 무엇인가
- [ ] 가상 스레드에서 `synchronized`를 쓸 때 주의할 점(pinning)

## Phase 3~4 — Spring
- [ ] Spring 없이 DI를 구현하면 어떤 코드가 되는가
- [ ] `@Configuration` 클래스의 `@Bean` 메서드를 두 번 호출해도 같은 객체가 나오는 이유
- [ ] AOP 프록시에서 같은 클래스 내부 메서드 호출 시 어드바이스가 적용되지 않는 이유
- [ ] 요청이 들어와서 컨트롤러 메서드가 호출되기까지의 흐름

## Phase 5 — 데이터 & 트랜잭션
- [ ] 영속성 컨텍스트와 1차 캐시, 더티 체킹
- [ ] N+1 문제와 해결 방법 3가지
- [ ] `REQUIRED`와 `REQUIRES_NEW`의 차이, 내부 트랜잭션 예외 시 외부 트랜잭션 상태
- [ ] READ COMMITTED vs REPEATABLE READ, MySQL InnoDB의 갭 락
- [ ] 비관적 락과 낙관적 락 중 무엇을 고를지 판단 기준
