# Phase 1 — 금융 도메인을 위한 Java 기본기 + TDD (3주)

> 가이드 수준: L1 · 선행: Phase 0 완료 · 이 Phase의 workspace 시작 방법: 빈 디렉터리에서 직접 생성

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- `BigDecimal`과 `RoundingMode`로 금액·이자·세금을 계산하고, 기대값을 Python `decimal`이나 손 계산으로 구해 테스트에 넣는다.
- 생성 시점에 규칙을 검사하는 불변 값 객체(`Money`, `AccountNumber`)를 만들고, `equals`/`hashCode` 계약을 `HashSet` 테스트로 보여준다.
- 잔액이 음수가 되는 출금, 해지 계좌 입금 같은 규칙 위반을 도메인 예외로 막고, 예외가 난 뒤에도 잔액이 바뀌지 않았음을 테스트로 보여준다.
- 테스트를 먼저 커밋하고 구현을 나중에 커밋하는 순서를 미션 5개 모두에서 git 이력으로 남긴다.
- JaCoCo 리포트로 도메인 패키지 라인 커버리지 90% 이상을 보여준다.

## 이 Phase의 결과물
Spring도 DB도 없는 순수 Java 코어뱅킹 도메인 모델과 콘솔 앱. Phase 2(동시성)에서 이 `src/`를 복사해 쓰고, Phase 3에서 Spring Boot 프로젝트로 옮긴다. 아래 클래스 이름은 Phase 5까지 그대로 쓴다.

```
phase-1-java-foundation/workspace/src/main/java/lab/bank/
├── common/       BankException, ErrorCode                                        (M1-2)
├── money/        Money, Currency, CurrencyMismatchException                      (M1-1)
├── account/      Account, AccountNumber, AccountStatus, 계좌 예외 6개             (M1-2)
├── ledger/       Transaction, TransactionType, Ledger                            (M1-3)
├── interest/     InterestPolicy, SimpleDailyInterestPolicy,
│                 ActualDaysInterestPolicy, MonthlyCompoundInterestPolicy,
│                 TaxCalculator, AfterTaxInterest                                 (M1-4)
├── application/  BankService, 거래 예외 4개, AccountNumberGenerator               (M1-3, M1-5)
└── console/      BankConsoleApp, InputView, OutputView, MenuController           (M1-5)
```

패키지 의존 방향: `console → application → account·ledger·interest → money → common`. 화살표 반대 방향 import는 하지 않는다.

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 왜 `double`로 돈을 계산하면 안 되나
```java
System.out.println(0.1 + 0.2);                 // 0.30000000000000004
System.out.println(1.03 - 0.42);               // 0.6100000000000001
System.out.println(10_000_000 * 0.0003);       // 2999.9999999999995
System.out.println((long) (10_000_000 * 0.0003)); // 2999
```
`double`은 2진 부동소수점이라 0.1, 0.0003 같은 10진 소수를 정확히 표현하지 못한다. 위 마지막 줄은 원금 10,000,000원에 이율 0.03%를 곱해 원 미만을 버린 결과다. 정답은 3,000원인데 2,999원이 나온다.
이런 계산을 계좌 1,000,000개에 매일 돌리면 하루에 최대 1,000,000원이 원장 합계와 맞지 않고, 일 마감 대사(reconciliation, 원장 합계와 계좌 잔액 합계 비교)에서 불일치로 잡힌다.

**`BigDecimal` 사용 규칙**
- 생성은 문자열로 한다: `new BigDecimal("0.1")`은 정확히 0.1이다. `new BigDecimal(0.1)`은 `0.1000000000000000055511151231257827021181583404541015625`가 된다. `BigDecimal.valueOf(0.1)`은 `Double.toString(0.1)`을 거쳐 `0.1`이 된다.
- 값 비교는 `compareTo`로 한다: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))`는 `false`(scale 1과 2가 다름), `compareTo`는 `0`이다.
- 나눗셈은 scale과 `RoundingMode`를 지정한다: `BigDecimal.ONE.divide(new BigDecimal("3"))`는 무한소수라 `ArithmeticException`이 난다. `a.divide(b, 10, RoundingMode.HALF_EVEN)`처럼 쓴다.
- 불변이다: `a.add(b)`는 `a`를 바꾸지 않고 새 객체를 반환한다. 반환값을 버리면 계산이 사라진다.

원화(KRW)는 소수점이 없지만 이자·환율·수수료 계산 중간에는 소수가 생긴다. "어느 단계에서 어떤 `RoundingMode`로 몇 자리를 남기는가"는 약관이나 업무 규칙으로 정하는 값이고, M1-4에서 미션 규칙으로 정해서 쓴다.

### 2. 값 객체 vs 엔티티
| | 값 객체 (Value Object) | 엔티티 (Entity) |
|---|---|---|
| 동일성 | 모든 필드 값이 같으면 같다 | 식별자(ID)가 같으면 같다 |
| 가변성 | 불변 | 상태가 변한다 |
| 예 | `Money`, `AccountNumber` | `Account` |
| `equals`/`hashCode` | 모든 필드로 계산 | 식별자 필드로만 계산 |

### 3. 불변 객체 만드는 법
1. 모든 필드를 `private final`로 선언한다.
2. setter를 두지 않는다.
3. 클래스를 `final`로 선언하거나 `record`를 쓴다 (하위 클래스가 상태를 바꾸는 메서드를 추가하지 못하게).
4. 가변 객체(`List`, `Map`)를 받거나 내보낼 때 복사본을 쓴다 (`List.copyOf(...)`).
5. 상태를 바꾸는 연산은 새 객체를 반환한다 (`money.plus(other)`).
6. 생성자 안에서 `this`를 다른 객체에 넘기거나 static 필드에 저장하지 않는다.

**스레드 간 공유에서 얻는 효과 (JLS 17.5 final 필드 의미론)**: 생성자가 끝난 뒤에 참조를 얻은 스레드는 그 객체의 `final` 필드가 생성자에서 대입한 값으로 보이는 것이 보장된다. 6번 규칙을 어겨 생성 도중 `this`가 다른 스레드에 노출되면 이 보장이 사라진다. `final` 필드만 있는 객체는 생성 후 값이 바뀌지 않으므로, 여러 스레드가 락 없이 같은 `Money` 인스턴스를 읽어도 다른 값을 보는 일이 없다. Phase 2에서 여러 스레드가 `Account`를 공유할 때, 락이 필요한 곳은 가변 필드인 `balance`·`status`를 바꾸는 코드뿐이고 `Money` 자체에는 락이 필요 없다.

### 4. `equals` / `hashCode` 계약
- `a.equals(b)`가 `true`면 `a.hashCode() == b.hashCode()`여야 한다.
- 어기면 `HashSet.contains`, `HashMap.get`이 같은 값의 객체를 찾지 못한다. `HashMap`은 `hashCode`로 버킷을 먼저 고르고, 같은 버킷 안에서만 `equals`로 비교하기 때문이다.
- `record`는 모든 컴포넌트로 `equals`/`hashCode`를 자동 생성한다. 컴포넌트가 `BigDecimal`이면 `BigDecimal.equals`(scale까지 비교)를 쓰므로 `1000`과 `1000.00`이 다른 값이 된다. M1-1 힌트 2에서 직접 재현한다.

### 5. 예외 설계
- 비즈니스 규칙 위반은 unchecked 도메인 예외로 표현한다: `InsufficientBalanceException extends BankException extends RuntimeException`.
- checked 예외(`Exception` 직접 상속)를 쓰면 `deposit`을 호출하는 모든 메서드에 `throws`가 붙고, Phase 5의 `@Transactional`은 기본 설정에서 checked 예외에 롤백하지 않는다.
- 예외 이름만 보고 어떤 규칙이 깨졌는지 알 수 있게 이름을 짓는다.
- 메시지에는 디버깅에 필요한 정보(계좌번호, 요청 금액, 현재 잔액)를 넣고, 계좌번호는 가운데 4자리를 `****`로 가린다(`110-****-5678`).
- 모든 도메인 예외는 `ErrorCode`를 가진다. Phase 4에서 `ErrorCode`를 HTTP 상태 코드와 에러 응답 본문으로 바꾼다.

### 6. 테스트 작성 규칙
```java
@Test
@DisplayName("잔액보다 큰 금액을 출금하면 예외가 발생하고 잔액은 그대로다")
void withdrawMoreThanBalance() {
    // given
    // when
    // then
}
```
- `@DisplayName`은 규칙을 문장으로 쓴다. 테스트 목록만 읽어도 클래스의 규칙 목록이 되게 한다.
- 경계값을 테스트한다: 0, 음수, 정확히 잔액만큼, 잔액 + 1원, `null`.
- 기대값은 구현 코드로 계산하지 않는다. 손 계산이나 Python `decimal`로 구한 숫자를 그대로 적는다.

## 워크스페이스 만들기
Phase 0 M0-2와 같은 방식으로 `phase-1-java-foundation/workspace/`에 Gradle 프로젝트를 직접 만든다.

```bash
cd phase-1-java-foundation/workspace
gradle wrapper --gradle-version 8.14.3
```

- `settings.gradle.kts`: `rootProject.name = "bank-domain"`
- `build.gradle.kts`: Phase 0 M0-2의 파일을 그대로 복사한다 (Java 21 toolchain, `org.junit:junit-bom:5.11.4`, `org.junit.jupiter:junit-jupiter`, `org.assertj:assertj-core:3.27.3`, `org.junit.platform:junit-platform-launcher`).
- M1-5에서 `jacoco`, `application` 플러그인과 설정 블록을 추가한다. 추가할 내용은 M1-5 요구사항에 있다.
- 루트 패키지: `lab.bank`
- `build.gradle.kts`가 생기면 M0-3의 CI가 이 workspace의 `./gradlew test`도 실행한다.

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 (8~12h) | M1-1, M1-4 | 핵심 개념 1·3·4·6절, `BigDecimal` Javadoc class description, `RoundingMode`, `ChronoUnit`, 이펙티브 자바 아이템 10·11·17 |
| 2주 (10~14h) | M1-2, M1-3 | 핵심 개념 2·5절, `enum`·`record`·`switch` 식, `java.time`(`Clock`, `LocalDate`, `LocalDateTime`), 컬렉션·스트림(`Collectors.groupingBy`), 이펙티브 자바 아이템 49·69~73 |
| 3주 (6~10h) | M1-5 | 이 README "이 Phase의 결과물"의 패키지 의존 방향, JaCoCo Gradle 플러그인 |

M1-4의 선행은 M1-1뿐이라 1주차에 둔다. M1-4와 M1-5를 같은 주에 두면 3주차가 10~16h로 주 15h를 넘는다.

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M1-1](missions/M1-1-money.md) | `Money` 값 객체 | 4~6h |
| [M1-2](missions/M1-2-account.md) | `Account` 엔티티와 도메인 예외 | 5~7h |
| [M1-3](missions/M1-3-ledger.md) | 거래내역과 `Ledger` | 5~7h |
| [M1-4](missions/M1-4-interest.md) | 이자 계산기와 반올림 정책 | 4~6h |
| [M1-5](missions/M1-5-console-bank.md) | [종합] 콘솔 뱅킹 | 6~10h |

## 읽을거리
- 이펙티브 자바 3판: 아이템 10·11 (`equals`/`hashCode`), 17 (불변), 49 (매개변수 검증), 69~73 (예외)
- `java.math.BigDecimal` Javadoc의 class description 전체, `RoundingMode` Javadoc의 표
- Java Language Specification (Java SE 21) 17.5 "final Field Semantics"
- JUnit 5 User Guide: "Writing Tests" 장의 "Display Names", "Parameterized Tests" 절
- JaCoCo 문서: "Coverage Counters", Gradle User Manual "The JaCoCo Plugin"

## 완료 기준
- [ ] `phase-1-java-foundation/workspace`에서 `./gradlew test jacocoTestReport jacocoTestCoverageVerification`이 `BUILD SUCCESSFUL`로 끝난다
- [ ] 미션 5개 각각에서 `test:` 커밋이 구현 커밋보다 먼저 있다 (`git log --oneline`)
- [ ] 각 미션의 "생각해볼 질문"에 대한 TIL이 `til/`에 있다
- [ ] [레벨 진단](../docs/self-check.md) Phase 1 항목을 말로 설명할 수 있다
