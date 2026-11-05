# Phase 1 — 금융 도메인을 위한 Java 기본기 (3주)

## 학습 목표
- 돈을 안전하게 다루는 **값 객체(Value Object)**를 설계할 수 있다.
- **불변식(invariant)**을 객체 스스로 지키게 만들 수 있다. (잔액은 음수가 될 수 없다 등)
- 의도를 드러내는 **도메인 예외**를 설계할 수 있다.
- JUnit5 + AssertJ로 **테스트를 먼저** 작성하는 습관을 들인다.

## 이 Phase의 결과물
Spring도 DB도 없는 **순수 Java** 코어뱅킹 도메인 모델. Phase 2(동시성)에서 이 코드를 그대로 쓰고, Phase 3에서 Spring으로 옮긴다.

```
lab.bank
├── money/      Money, Currency(enum)
├── account/    Account, AccountNumber, AccountStatus, 예외들
├── ledger/     Transaction, TransactionType, Ledger
└── interest/   InterestCalculator, InterestPolicy
```

---

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 왜 `double`로 돈을 계산하면 안 되나
```java
System.out.println(0.1 + 0.2);            // 0.30000000000000004
System.out.println(1.03 - 0.42);          // 0.6100000000000001
```
`double`은 2진 부동소수점이라 0.1을 정확히 표현할 수 없다. 1원 오차라도 수백만 건이 쌓이면 대사(reconciliation)가 깨진다.

**`BigDecimal` 사용 규칙**
- 생성은 **문자열**로: `new BigDecimal("0.1")` ✅, `new BigDecimal(0.1)` ❌ (`BigDecimal.valueOf(0.1)`은 OK)
- 비교는 `compareTo`: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))`는 **false** (scale이 다름)
- 나눗셈은 반드시 scale과 `RoundingMode` 지정: `a.divide(b, 2, RoundingMode.HALF_EVEN)`
- 불변이다: `a.add(b)`는 `a`를 바꾸지 않고 새 객체를 반환

> 원화(KRW)는 소수점이 없지만, 이자·환율·수수료 계산 중간 과정에는 소수가 생긴다.
> "언제, 어떤 규칙으로 반올림하는가"가 곧 **비즈니스 정책**이다.

### 2. 값 객체 vs 엔티티
| | 값 객체 (Value Object) | 엔티티 (Entity) |
|---|---|---|
| 동일성 | 값이 같으면 같다 | 식별자(ID)가 같으면 같다 |
| 가변성 | **불변** | 상태가 변한다 |
| 예 | `Money`, `AccountNumber` | `Account`, `Order` |
| `equals` | 모든 필드 비교 | ID만 비교 |

### 3. 불변 객체 만드는 법
1. 모든 필드 `private final`
2. setter 없음
3. 클래스를 `final`로 (또는 `record`)
4. 가변 객체를 받거나 내보낼 때 **방어적 복사** (`List.copyOf(...)`)
5. 상태 변경 메서드는 **새 객체를 반환**

불변 객체는 **스레드 안전**하다. → Phase 2에서 큰 무기가 된다.

### 4. `equals` / `hashCode` 계약
- `equals`가 true면 `hashCode`도 같아야 한다.
- 안 지키면 `HashMap`/`HashSet`에서 객체를 못 찾는다.
- `record`는 둘 다 자동 생성한다. 단 `BigDecimal` 필드가 있으면 scale 문제를 고려해야 한다. (M1-1에서 직접 겪어보자)

### 5. 예외 설계
- 비즈니스 규칙 위반 → **unchecked 도메인 예외** (`InsufficientBalanceException extends BankException extends RuntimeException`)
- 예외 이름만 봐도 무슨 규칙이 깨졌는지 알 수 있게
- 메시지에는 디버깅에 필요한 정보(계좌번호, 요청 금액, 현재 잔액)를 담되 **민감정보는 마스킹**

### 6. 테스트 작성 규칙
```java
@Test
@DisplayName("잔액보다 큰 금액을 출금하면 예외가 발생한다")
void withdrawMoreThanBalance() {
    // given
    // when
    // then
}
```
- 테스트 이름 = 스펙. 테스트 목록만 읽어도 클래스가 뭘 하는지 알 수 있어야 한다.
- 경계값을 테스트한다: 0, 음수, 정확히 잔액만큼, 잔액 + 1

---

## 워크스페이스 만들기

Phase 0과 같은 방식으로 `phase-1-java-foundation/workspace/`에 Gradle 프로젝트를 직접 만든다.
- `rootProject.name = "bank-domain"`
- 패키지 루트: `lab.bank`
- 의존성: Phase 0과 동일 (JUnit5, AssertJ)

---

## 미션

| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M1-1](missions/M1-1-money.md) | `Money` 값 객체 | 4~6h |
| [M1-2](missions/M1-2-account.md) | `Account` 엔티티와 도메인 예외 | 5~7h |
| [M1-3](missions/M1-3-ledger.md) | 거래내역과 `Ledger` | 5~7h |
| [M1-4](missions/M1-4-interest.md) | 이자 계산기와 반올림 정책 | 4~6h |
| [M1-5](missions/M1-5-console-bank.md) | [종합] 콘솔 뱅킹 애플리케이션 | 6~10h |

## 읽을거리
- 이펙티브 자바: 아이템 10, 11 (equals/hashCode), 17 (불변), 49 (매개변수 검증), 69~73 (예외)
- `BigDecimal` Javadoc의 class description 부분 전체
- JUnit 5 User Guide: Writing Tests, Parameterized Tests

## 완료 체크리스트
- [ ] 모든 미션의 테스트 통과
- [ ] 각 미션의 "생각해볼 질문" TIL 작성
- [ ] [레벨 진단](../docs/self-check.md) Phase 1 항목을 모두 설명할 수 있다
