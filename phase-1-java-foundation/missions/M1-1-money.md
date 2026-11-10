# M1-1 `Money` 값 객체

> 가이드 수준: L1 · 예상 시간: 4~6h · 선행: M0-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 통화와 금액을 함께 가진 불변 값 객체 `Money`를 만들고, 테스트 시나리오 22개를 JUnit 5 테스트로 통과시킨다.
- `Money.of("1000", USD)`와 `Money.of("1000.00", USD)`를 `HashSet`에 넣으면 크기가 1이 되는 것을 테스트로 보여준다.
- 같은 금액·이율에 `HALF_EVEN`과 `HALF_UP`을 적용했을 때 결과가 달라지는 입력을 `@ParameterizedTest`로 보여준다.

## 배경
은행 코드에서 금액은 가장 많이 쓰이는 타입이다. 금액을 `BigDecimal`로만 다루면 원화와 달러를 더하는 코드, `new BigDecimal("1000")`과 `new BigDecimal("1000.00")`을 다른 값으로 판단하는 코드, 곱셈 뒤 반올림을 빠뜨리는 코드가 호출하는 곳마다 생길 수 있다.
예를 들어 원화 계좌에 달러 금액 `100.00`이 그대로 더해지면 잔액이 100원 늘어나는 사고가 된다.
이 미션은 통화 검사, scale 정규화, 반올림 규칙을 `Money` 한 클래스에 모아, `Money`를 거치지 않고는 금액을 만들거나 계산할 수 없게 한다.
M0-2에서 만든 Gradle 설정과 given/when/then 테스트 구조를 그대로 쓰고, 여기서 만든 `Money`는 M1-2의 계좌 잔액과 M1-4의 이자 계산에 쓰인다.

## 요구사항

패키지: `lab.bank.money`

### `Currency` (enum)
| 상수 | `scale()` | 출력 패턴 |
|---|---|---|
| `KRW` | `0` | `#,##0` |
| `USD` | `2` | `#,##0.00` |

- `public int scale()`: 통화의 소수점 자리수를 반환한다.

### `Money`
`final class` 또는 `record`로 만든다. public 생성자는 두지 않는다 (`record`라면 canonical constructor를 검증용으로 쓰되, 외부 코드는 정적 팩토리만 호출한다).

1. **생성**

   | 시그니처 | 동작 |
   |---|---|
   | `static Money of(String amount, Currency currency)` | 문자열 금액을 통화 scale로 정규화해 만든다 |
   | `static Money won(long amount)` | `Money.of(String.valueOf(amount), Currency.KRW)`와 같다 |
   | `static Money zero(Currency currency)` | 금액 0, 해당 통화 scale |

   - 정규화: 내부 `BigDecimal`의 scale을 항상 통화 scale로 맞춘다. `Money.of("1000", USD)`의 내부 값은 `1000.00`(scale 2)이다.
   - 값을 잃지 않는 소수점 0은 허용한다: `Money.of("1000.0", KRW)` → `KRW 1,000`, `Money.of("10.1", USD)` → `USD 10.10`.
   - 반올림이 있어야만 통화 scale에 맞출 수 있으면 `IllegalArgumentException`: `Money.of("10.123", USD)`, `Money.of("100.5", KRW)`.
   - 숫자가 아닌 문자열(`"abc"`, `""`)은 `IllegalArgumentException` (`NumberFormatException`은 `IllegalArgumentException`의 하위 클래스이므로 그대로 전파해도 된다).
   - `amount` 또는 `currency`가 `null`이면 `IllegalArgumentException`.
   - 음수 금액은 허용한다 (차액 계산에 필요). 양수 여부 검사는 `Money`를 쓰는 쪽(M1-2 `Account.deposit` 등)이 한다.

2. **조회**
   - `BigDecimal amount()`, `Currency currency()`
   - `boolean isNegative()`, `boolean isPositive()`, `boolean isZero()`

3. **연산** (모두 새 `Money`를 반환하고 원본은 바뀌지 않는다)

   | 시그니처 | 동작 |
   |---|---|
   | `Money plus(Money other)` | 합 |
   | `Money minus(Money other)` | 차 (음수 결과 허용) |
   | `Money times(BigDecimal rate, RoundingMode mode)` | 금액 × `rate`를 `mode`로 통화 scale에 맞춰 반올림 |

   - `plus`, `minus`에서 통화가 다르면 `CurrencyMismatchException`.
   - 인자가 `null`이면 `IllegalArgumentException`.

4. **비교**
   - `boolean isGreaterThan(Money other)`, `boolean isLessThan(Money other)`, `boolean isGreaterThanOrEqual(Money other)`
   - 통화가 다르면 `CurrencyMismatchException`.

5. **동등성**
   - 통화와 정규화된 금액이 같으면 `equals`가 `true`, `hashCode`가 같다.
   - 통화가 다르면 금액이 같아도 `equals`가 `false`다 (`Money.zero(KRW)`와 `Money.zero(USD)`는 다르다).

6. **출력** — `toString()`
   - 형식: `"{통화 코드} {천 단위 구분 금액}"`. 예: `"KRW 1,000"`, `"USD 1,000.00"`, `"KRW -500"`.
   - 구분자는 OS·JVM 기본 Locale과 무관하게 항상 쉼표(`,`)와 점(`.`)이다.

### `CurrencyMismatchException`
- 이 미션에서는 `RuntimeException`을 상속한다. M1-2에서 `BankException` 계층이 생기면 `BankException`을 상속하도록 바꾼다.
- 메시지에 두 통화 코드를 모두 넣는다. 예: `"통화가 다릅니다: KRW, USD"`.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `Money.won(1000)` | `plus(Money.won(500))` | `Money.won(1500)` |
| 2 | `Money.won(1000)` | `minus(Money.won(1500))` | `Money.won(-500)`, `isNegative() == true` |
| 3 | `Money.won(1000)` | `plus(Money.of("1", USD))` | `CurrencyMismatchException`, 메시지에 `KRW`와 `USD` 포함 |
| 4 | `Money a = Money.won(1000)` | `a.plus(Money.won(500))` 후 `a` 확인 | `a.equals(Money.won(1000)) == true` |
| 5 | - | `Money.of("1000", USD).equals(Money.of("1000.00", USD))` | `true`, 두 객체의 `hashCode` 같음 |
| 6 | 5의 두 객체 | 빈 `HashSet`에 둘 다 `add` | `size() == 1` |
| 7 | - | `Money.zero(KRW).equals(Money.zero(USD))` | `false` |
| 8 | - | `Money.of("10.123", USD)` | `IllegalArgumentException` |
| 9 | - | `Money.of("100.5", KRW)` | `IllegalArgumentException` |
| 10 | - | `Money.of("1000.0", KRW)` | `Money.won(1000)`과 `equals == true` |
| 11 | - | `Money.of(null, KRW)`, `Money.of("100", null)`, `Money.of("abc", KRW)` | 각각 `IllegalArgumentException` |
| 12 | `Money.won(10000)` | `times(new BigDecimal("0.035"), HALF_EVEN)` | `Money.won(350)` |
| 13 | `Money.won(1)` | `times(new BigDecimal("0.5"), HALF_EVEN)` | `Money.won(0)` (0.5 → 가장 가까운 짝수 0) |
| 14 | `Money.won(3)` | `times(new BigDecimal("0.5"), HALF_EVEN)` | `Money.won(2)` (1.5 → 가장 가까운 짝수 2) |
| 15 | `Money.won(1)` | `times(new BigDecimal("0.5"), HALF_UP)` | `Money.won(1)` (0.5 → 1) |
| 16 | `Money.won(1000)` | `isGreaterThan(Money.won(999))` | `true` |
| 17 | `Money.won(1000)` | `isGreaterThanOrEqual(Money.won(1000))` | `true` |
| 18 | `Money.won(1000)` | `isLessThan(Money.of("1000", USD))` | `CurrencyMismatchException` |
| 19 | `Money.won(1234567)` | `toString()` | `"KRW 1,234,567"` |
| 20 | `Money.of("1234.5", USD)` | `toString()` | `"USD 1,234.50"` |
| 21 | `Money.won(-500)` | `toString()` | `"KRW -500"` |
| 22 | `Locale.setDefault(Locale.GERMANY)` 후 (테스트 끝에 원래 Locale로 복구) | `Money.of("1234.5", USD).toString()` | `"USD 1,234.50"` (독일 Locale 기본 기호로 만들면 `1.234,50`이 된다) |

12~15는 `@ParameterizedTest` + `@CsvSource`로 한 메서드에 묶는다. 22는 `@AfterEach`나 `try`/`finally`로 기본 Locale을 되돌려 다른 테스트에 영향을 주지 않게 한다.

## 제약
- `double`, `float` 사용 금지 — 2진 부동소수점 오차 (README 핵심 개념 1절).
- public 생성자 금지 — 정규화와 검증을 건너뛴 `Money`가 만들어지지 않게 정적 팩토리만 연다.
- `Money`의 금액 필드를 바꾸는 메서드 금지 — 모든 연산은 새 객체를 반환한다.
- `Currency` enum이 `DecimalFormat` 인스턴스를 필드로 갖지 않는다. `DecimalFormat`은 Javadoc에 "Decimal formats are generally not synchronized"라고 적혀 있어, enum 상수처럼 모든 스레드가 공유하는 곳에 두면 Phase 2에서 동시 호출 시 출력이 섞일 수 있다. 패턴 문자열만 갖고, `toString()` 호출마다 `DecimalFormat`을 새로 만든다.

## 힌트
<details>
<summary>힌트 1: scale 정규화와 예외</summary>

`BigDecimal.setScale(int newScale)`(RoundingMode 없는 버전)은 값을 잃는 반올림이 필요하면 `ArithmeticException("Rounding necessary")`을 던진다. `setScale(newScale, RoundingMode.UNNECESSARY)`와 같은 동작이다.
`new BigDecimal("1000.0").setScale(0)`은 `1000`이 되고, `new BigDecimal("100.5").setScale(0)`은 예외가 난다. 이 예외를 잡아 `IllegalArgumentException`으로 바꿔 던지면 시나리오 8~10을 한 번에 처리할 수 있다.
</details>

<details>
<summary>힌트 2: equals와 scale</summary>

생성 시점에 항상 통화 scale로 정규화하면 내부 `BigDecimal`의 scale이 같아서 `BigDecimal.equals`를 그대로 써도 시나리오 5가 통과한다.
정규화를 빼고 `record Money(BigDecimal amount, Currency currency)`를 만들면 시나리오 5와 6이 실패한다. 정규화 코드를 잠깐 주석 처리해 두 테스트가 실패하는 것을 확인한 뒤 되돌린다.
</details>

<details>
<summary>힌트 3: Locale과 무관한 천 단위 구분자</summary>

`new DecimalFormat(pattern)`은 JVM 기본 Locale의 기호를 쓴다. `java.text.DecimalFormat(String pattern, DecimalFormatSymbols symbols)` 생성자에 `DecimalFormatSymbols.getInstance(Locale.ROOT)`(또는 `Locale.US`)를 넘기면 구분자가 항상 `,`와 `.`이다.
패턴 문자열(`#,##0`, `#,##0.00`)은 `Currency` enum이 갖게 한다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "lab.bank.money.*"`에서 시나리오 1~22에 해당하는 테스트가 모두 PASSED로 출력된다
- [ ] `src/main/java/lab/bank/money/`에 `Money`, `Currency`, `CurrencyMismatchException` 3개 파일이 있고, `double`·`float`가 한 번도 나오지 않는다
- [ ] `git log --oneline`에서 `MoneyTest`를 추가한 `[test]` 커밋이 `Money` 구현 커밋보다 먼저 있다
- [ ] TIL에 `final class`와 `record`로 각각 만들어 본 결과(코드 줄 수, 정규화를 넣은 위치)를 비교한 표가 있다

## 생각해볼 질문
1. `Money`가 가변이라 `plus`가 자기 자신의 금액을 바꾼다면, `Money fee = price; fee.plus(tax);` 같은 코드에서 `price`는 어떻게 되는가? 불변 설계가 막아주는 버그를 코드 예로 하나 적는다. 이어서, Phase 2에서 스레드 100개가 같은 `Money` 인스턴스로 `plus`를 동시에 호출해도 락이 필요 없는 이유를 README 핵심 개념 3절의 final 필드 보장으로 설명한다.
2. 0.5, 1.5, 2.5, 3.5 네 값을 각각 정수로 반올림해 더한다. `HALF_UP`으로 반올림한 합, `HALF_EVEN`으로 반올림한 합, 반올림하지 않은 합(8)을 비교하고, 정확히 .5로 끝나는 값을 많이 반올림할 때 `HALF_EVEN`의 누적 편차가 `HALF_UP`보다 작은 이유를 설명한다.
3. 음수 금액을 허용하면 "출금 금액은 양수여야 한다" 규칙은 어디서 검사해야 하는가? `PositiveMoney` 같은 별도 타입을 만드는 방법과 비교해 장단점을 적는다.
4. JDK의 `java.util.Currency`는 ISO 4217 통화 코드와 기본 소수점 자리수(`getDefaultFractionDigits()`)를 제공한다. 이 미션에서 직접 만든 enum과 비교해, 지원 통화 목록을 제한할 수 있는지와 `switch`에서 빠진 통화를 컴파일러가 잡아주는지 두 기준으로 비교한다.
