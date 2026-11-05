# M1-1 `Money` 값 객체

## 배경
은행 시스템에서 금액은 가장 많이 쓰이는 타입이다. `BigDecimal`을 그대로 쓰면
통화 혼동(원화 + 달러), 음수 금액, 반올림 실수 같은 버그가 코드 곳곳에 퍼진다.
**금액 규칙을 `Money` 한 곳에 모아** 이런 버그가 원천적으로 불가능하게 만든다.

## 요구사항

### `Currency` (enum)
- `KRW`(소수점 0자리), `USD`(소수점 2자리) 두 가지
- 각 통화는 자신의 소수점 자리수(`scale`)를 안다

### `Money`
1. **생성**
   - `Money.of(String amount, Currency currency)`, `Money.won(long amount)` 정적 팩토리
   - `Money.zero(Currency currency)`
   - 금액은 통화의 scale로 정규화된다. `Money.of("1000", USD)` → 내부 값 `1000.00`
   - 통화 scale보다 소수점이 많으면 예외: `Money.of("10.123", USD)` ❌, `Money.of("100.5", KRW)` ❌
   - 금액 또는 통화가 `null`이면 예외
   - **음수 금액은 허용한다** (차액 계산 등에 필요). 대신 `isNegative()`, `isPositive()`, `isZero()` 제공
2. **연산** (모두 새 `Money` 반환, 원본 불변)
   - `plus(Money)`, `minus(Money)`
   - `times(BigDecimal rate, RoundingMode mode)` — 결과는 통화 scale로 반올림
   - 통화가 다르면 `CurrencyMismatchException`
3. **비교**
   - `isGreaterThan(Money)`, `isLessThan(Money)`, `isGreaterThanOrEqual(Money)`
   - 통화가 다르면 `CurrencyMismatchException`
4. **동등성**
   - `Money.of("1000", USD)`와 `Money.of("1000.00", USD)`는 **같다** (`equals`, `hashCode` 모두)
   - 통화가 다르면 다르다
5. **출력**
   - `toString()`: `"KRW 1,000"`, `"USD 1,000.00"` 형식

### `CurrencyMismatchException`
- `RuntimeException` 상속, 메시지에 두 통화 정보를 포함

## 테스트 시나리오 (전부 테스트 코드로 옮길 것)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| 1 | `Money.won(1000).plus(Money.won(500))` | `Money.won(1500)` |
| 2 | `Money.won(1000).minus(Money.won(1500))` | `Money.won(-500)`, `isNegative() == true` |
| 3 | `Money.won(1000).plus(Money.of("1", USD))` | `CurrencyMismatchException` |
| 4 | `plus` 후 원본 객체 | 값이 바뀌지 않음 |
| 5 | `Money.of("1000", USD).equals(Money.of("1000.00", USD))` | `true`, `hashCode`도 같음 |
| 6 | 위 두 객체를 `HashSet`에 넣으면 | 크기 1 |
| 7 | `Money.of("10.123", USD)` | 예외 |
| 8 | `Money.of("100.5", KRW)` | 예외 |
| 9 | `Money.of(null, KRW)`, `Money.of("100", null)` | 예외 |
| 10 | `Money.won(10000).times(new BigDecimal("0.035"), HALF_EVEN)` | `Money.won(350)` |
| 11 | `Money.won(1).times(new BigDecimal("0.5"), HALF_EVEN)` | `Money.won(0)` (banker's rounding) |
| 12 | `Money.won(3).times(new BigDecimal("0.5"), HALF_EVEN)` | `Money.won(2)` |
| 13 | `Money.won(1).times(new BigDecimal("0.5"), HALF_UP)` | `Money.won(1)` |
| 14 | `Money.won(1000).isGreaterThan(Money.won(999))` | `true` |
| 15 | `Money.won(1000).isGreaterThanOrEqual(Money.won(1000))` | `true` |
| 16 | `Money.won(1234567).toString()` | `"KRW 1,234,567"` |
| 17 | `Money.of("1234.5", USD).toString()` | `"USD 1,234.50"` |

> 10~13은 `@ParameterizedTest` + `@CsvSource`로 묶어보자.

## 제약
- `Money`는 `final class` 또는 `record` (둘 다 해보고 차이를 TIL에 적으면 더 좋다)
- `double`, `float` 사용 금지
- public 생성자 금지 (정적 팩토리만)

## 힌트 (30분 고민 후 열기)

<details>
<summary>힌트 1: scale 정규화</summary>

`BigDecimal.setScale(scale)`을 RoundingMode 없이 호출하면, 반올림이 필요할 때 `ArithmeticException`이 발생한다.
이걸 "소수점이 너무 많으면 예외"에 활용할 수 있다. (`RoundingMode.UNNECESSARY`와 같은 동작)
</details>

<details>
<summary>힌트 2: equals와 scale</summary>

생성 시점에 항상 통화 scale로 정규화해두면, 내부 `BigDecimal`의 scale이 항상 같아서 `equals`가 안전해진다.
정규화 안 하고 `record`를 쓰면 시나리오 5번이 깨진다. 직접 깨뜨려 보자.
</details>

<details>
<summary>힌트 3: 천 단위 구분자</summary>

`java.text.DecimalFormat("#,##0")`, `DecimalFormat("#,##0.00")`. 통화별 패턴을 `Currency` enum이 갖게 하면 어떨까?
</details>

## 생각해볼 질문 (TIL에 답하기)
1. `Money`를 불변으로 만들면 어떤 버그가 예방되는가? 가변이었다면 어떤 코드가 위험해지는가?
2. `HALF_EVEN`(banker's rounding)은 왜 금융권에서 많이 쓰이나? `HALF_UP`과 대량 처리 시 누적 오차 차이는?
3. 음수 금액을 허용한 선택은 옳은가? "출금 금액"처럼 반드시 양수여야 하는 곳은 어떻게 보장할까?
4. `java.util.Currency`(JDK 기본)를 쓰지 않고 enum을 만든 이유를 생각해보자. 장단점은?
