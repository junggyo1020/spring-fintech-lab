# M1-2 `Account` 엔티티와 도메인 예외

> 가이드 수준: L1, 예상 시간: 5~7h, 선행: M1-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 잔액을 `deposit`/`withdraw`로만 바꿀 수 있는 `Account` 엔티티를 만들고, 예외가 난 뒤 잔액이 그대로인 것을 테스트로 보여준다.
- `AccountStatus`의 3×3 전이 조합 9개를 `@ParameterizedTest` + `@CsvSource`로 검증하고, `true`인 조합이 정확히 4개임을 보여준다.
- `ErrorCode`를 가진 `BankException` 계층을 만들고, 예외 메시지에 전체 계좌번호가 아니라 마스킹된 번호만 들어가는 것을 테스트로 보여준다.

## 배경
계좌 잔액에 `setBalance()`가 열려 있으면 어떤 코드든 검증 없이 잔액을 바꿀 수 있다. 출금 화면, 배치, 관리자 도구가 각자 잔액 검사를 구현하다 한 곳이라도 빠뜨리면 잔액이 음수가 되거나, 해지된 계좌에 입금이 들어가는 사고가 난다.
그래서 "잔액은 음수가 될 수 없다", "`ACTIVE`가 아닌 계좌는 거래할 수 없다" 같은 규칙을 `Account`가 자기 메서드 안에서 검사하게 한다.
규칙 위반은 이름만 보고 원인을 알 수 있는 도메인 예외로 알리고, 각 예외가 가진 `ErrorCode`는 Phase 4에서 HTTP 에러 응답으로 그대로 바뀐다.
M1-1의 `Money`를 잔액 타입으로 쓰고, 여기서 만든 `Account`는 M1-3에서 `BankService`와 `Ledger`가 사용한다.

## 요구사항

### 1. `ErrorCode`와 `BankException` (패키지 `lab.bank.common`)
- `enum ErrorCode`: 이 미션에서 아래 7개를 만든다. M1-3에서 4개를 더 추가한다.

  | 상수 | 대응 예외 |
  |---|---|
  | `INVALID_AMOUNT` | `InvalidAmountException` |
  | `CURRENCY_MISMATCH` | `CurrencyMismatchException` |
  | `INSUFFICIENT_BALANCE` | `InsufficientBalanceException` |
  | `ACCOUNT_NOT_ACTIVE` | `AccountNotActiveException` |
  | `ILLEGAL_STATE_TRANSITION` | `IllegalAccountStateTransitionException` |
  | `ACCOUNT_HAS_BALANCE` | `AccountHasBalanceException` |
  | `ACCOUNT_NOT_FOUND` | `AccountNotFoundException` |

- `public abstract class BankException extends RuntimeException`
  - 생성자: `protected BankException(ErrorCode errorCode, String message)`
  - `public ErrorCode errorCode()`

### 2. 예외 계층

```
BankException (lab.bank.common, abstract, extends RuntimeException)
├── CurrencyMismatchException             (lab.bank.money)   // M1-1 것을 RuntimeException → BankException 상속으로 변경
├── InvalidAmountException                (lab.bank.account) // 요청 금액 포함
├── InsufficientBalanceException          (lab.bank.account) // 마스킹 계좌번호, 요청 금액, 현재 잔액 포함
├── AccountNotActiveException             (lab.bank.account) // 마스킹 계좌번호, 현재 상태 포함
├── IllegalAccountStateTransitionException (lab.bank.account) // 마스킹 계좌번호, 현재 상태, 요청 상태 포함
├── AccountHasBalanceException            (lab.bank.account) // 마스킹 계좌번호, 현재 잔액 포함
└── AccountNotFoundException              (lab.bank.account) // 마스킹 계좌번호 포함. M1-3 BankService가 던진다
```

- 금액은 `Money.toString()` 형식(`KRW 10,001`)으로 메시지에 넣는다.
- 메시지 예: `"잔액이 부족합니다. 계좌=110-****-5678, 요청=KRW 10,001, 잔액=KRW 10,000"`

### 3. `AccountNumber` (값 객체, `record` 권장, 패키지 `lab.bank.account`)
- 생성: `new AccountNumber(String value)` 또는 `AccountNumber.of(String value)` 중 하나를 정해 쓴다.
- 형식: 숫자 3자리-4자리-4자리 (`110-1234-5678`). 정규식 `\d{3}-\d{4}-\d{4}` 전체 일치.
- 형식이 틀리거나 `null`이면 `IllegalArgumentException`.
- `String value()`: 전체 번호 `"110-1234-5678"`
- `String masked()`: 가운데 4자리를 가린 `"110-****-5678"`
- `toString()`: `masked()`와 같은 값을 반환한다. 로그나 예외 메시지에 객체를 그대로 넣어도 전체 번호가 나오지 않게 하기 위해서다.

### 4. `AccountStatus` (enum, 패키지 `lab.bank.account`)
- 상수: `ACTIVE`(정상), `FROZEN`(정지), `CLOSED`(해지)
- `boolean canTransitTo(AccountStatus next)`: 아래 표대로 반환한다. 자기 자신으로의 전이(`ACTIVE → ACTIVE` 등)는 `false`다. `next`가 `null`이면 `IllegalArgumentException`.

  | 현재 \ 다음 | `ACTIVE` | `FROZEN` | `CLOSED` |
  |---|---|---|---|
  | `ACTIVE` | false | **true** | **true** |
  | `FROZEN` | **true** | false | **true** |
  | `CLOSED` | false | false | false |

  `true`는 정확히 4개다.

### 5. `Account` (엔티티, 패키지 `lab.bank.account`)
| 필드 | 설명 |
|---|---|
| `AccountNumber number` | 식별자, `final` |
| `String ownerName` | 예금주, `final` |
| `Currency currency` | 계좌 통화, `final` |
| `Money balance` | 잔액, `deposit`/`withdraw`로만 바뀐다 |
| `AccountStatus status` | 상태, `freeze`/`unfreeze`/`close`로만 바뀐다 |

| 시그니처 | 동작 |
|---|---|
| `static Account open(AccountNumber number, String ownerName, Currency currency)` | 잔액 `Money.zero(currency)`, 상태 `ACTIVE`. 인자가 `null`이거나 `ownerName`이 공백이면 `IllegalArgumentException` |
| `void deposit(Money amount)` | 잔액 += `amount` |
| `void withdraw(Money amount)` | 잔액 -= `amount` |
| `void freeze()` | `ACTIVE → FROZEN` |
| `void unfreeze()` | `FROZEN → ACTIVE` |
| `void close()` | `ACTIVE → CLOSED` 또는 `FROZEN → CLOSED` |
| `AccountNumber number()`, `String ownerName()`, `Currency currency()`, `Money balance()`, `AccountStatus status()` | 조회 |

**`deposit` 검사 순서** (앞의 검사에서 실패하면 뒤 검사는 하지 않는다)
1. `amount`가 `null` → `IllegalArgumentException`
2. 상태가 `ACTIVE`가 아님 → `AccountNotActiveException`
3. `amount`가 0 이하 → `InvalidAmountException`
4. `amount` 통화가 계좌 통화와 다르면 → `CurrencyMismatchException`

**`withdraw` 검사 순서**: `deposit`의 1~4 다음에
5. `amount`가 잔액보다 크면 → `InsufficientBalanceException` (잔액과 같으면 성공해서 잔액 0)

**상태 변경 검사 순서**
1. `status.canTransitTo(요청 상태)`가 `false` → `IllegalAccountStateTransitionException`
2. (`close()`만) 잔액이 0이 아님 → `AccountHasBalanceException`

**공통 규칙**
- 예외가 나면 잔액과 상태는 호출 전과 같다. 모든 검사를 끝낸 뒤에 필드를 바꾼다.
- `equals`/`hashCode`는 `AccountNumber`만으로 계산한다.
- setter를 만들지 않는다. `balance()`는 `Money`를 그대로 반환한다(`Money`는 불변이므로 호출자가 받은 객체로 잔액을 바꿀 수 없다).

## 테스트 시나리오

`A`는 `Account.open(new AccountNumber("110-1234-5678"), "홍길동", KRW)`로 만든 계좌다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | - | `A` 개설 | `balance() == Money.won(0)`, `status() == ACTIVE` |
| 2 | `A` | `deposit(Money.won(10000))` | 잔액 `Money.won(10000)` |
| 3 | `A` | `deposit(Money.won(0))`, `deposit(Money.won(-1))` | 각각 `InvalidAmountException`, `errorCode() == INVALID_AMOUNT`, 잔액 0 |
| 4 | `A` 잔액 10,000 | `withdraw(Money.won(10000))` | 잔액 `Money.won(0)` |
| 5 | `A` 잔액 10,000 | `withdraw(Money.won(10001))` | `InsufficientBalanceException`, 잔액 `Money.won(10000)` 그대로 |
| 6 | `A` | `deposit(Money.of("1", USD))` | `CurrencyMismatchException`, `errorCode() == CURRENCY_MISMATCH` |
| 7 | `A`를 `freeze()` | `deposit(Money.won(1000))`, `withdraw(Money.won(1000))` | 각각 `AccountNotActiveException` |
| 8 | `A`를 `freeze()` 후 `unfreeze()` | `deposit(Money.won(1000))` | 잔액 `Money.won(1000)` |
| 9 | `A`를 `freeze()` | `deposit(Money.won(0))` | `AccountNotActiveException` (상태 검사가 금액 검사보다 먼저) |
| 10 | `A` 잔액 1,000 | `close()` | `AccountHasBalanceException`, 상태 `ACTIVE` 그대로 |
| 11 | `A` 잔액 0을 `freeze()` | `close()` | 상태 `CLOSED` |
| 12 | `A`를 `close()` | `freeze()` | `IllegalAccountStateTransitionException`, 상태 `CLOSED` 그대로 |
| 13 | `A` (`ACTIVE`) | `freeze()`를 두 번 | 두 번째 호출에서 `IllegalAccountStateTransitionException` |
| 14 | - | `canTransitTo` 3×3 = 9개 조합 | 요구사항 4의 표와 일치 (`true` 4개, `false` 5개) |
| 15 | `A` 잔액 10,000 | `withdraw(Money.won(10001))`의 예외 메시지 | `"110-****-5678"`을 포함하고 `"110-1234-5678"`을 포함하지 않음 |
| 16 | - | `new AccountNumber("1101234")`, `"abc-defg-hijk"`, `"110-1234-56789"`, `"110 1234 5678"`, `null` | 각각 `IllegalArgumentException` |
| 17 | - | `new AccountNumber("110-1234-5678")`의 `masked()`, `toString()` | 둘 다 `"110-****-5678"` |
| 18 | 같은 계좌번호로 개설한 두 `Account`, 하나만 10,000 입금 | `equals`, `hashCode` | `equals == true`, `hashCode` 같음 |
| 19 | - | `Account.open(번호, " ", KRW)` | `IllegalArgumentException` |

14는 `@CsvSource({"ACTIVE,ACTIVE,false", "ACTIVE,FROZEN,true", ...})` 9줄로 작성한다.

## 제약
- `Account`의 잔액, 상태를 바꾸는 public 메서드는 `deposit`, `withdraw`, `freeze`, `unfreeze`, `close` 5개뿐이다 (리플렉션 제외).
- 예외를 던진 뒤 상태가 바뀐 채로 남으면 안 된다 (시나리오 5, 10, 12). 검사 → 변경 순서로 작성한다.
- 도메인 예외는 모두 `BankException`을 상속한다. `IllegalArgumentException`은 `null`, 형식 오류처럼 호출 코드의 버그에만 쓴다.
- 예외 메시지와 `toString()`에 전체 계좌번호를 넣지 않는다.

## 힌트
<details>
<summary>힌트 1: 검사 순서가 왜 요구사항인가</summary>

`FROZEN` 계좌에 0원을 입금하면 `AccountNotActiveException`과 `InvalidAmountException` 중 어느 쪽이 나가야 하는가? 순서를 정하지 않으면 구현마다 다른 예외가 나가고, Phase 4에서는 같은 요청에 다른 HTTP 에러 코드가 응답된다.
시나리오 9가 이 순서를 고정한다.
</details>

<details>
<summary>힌트 2: enum 안에 전이 규칙 넣기</summary>

각 상수가 생성자 인자로 `Set<AccountStatus>`를 받게 하면 `ACTIVE(Set.of(FROZEN, CLOSED))`처럼 뒤에 선언된 상수를 참조하게 된다. JDK 21의 `javac`는 이것을 `illegal forward reference` 컴파일 오류로 거부한다. `ACTIVE(Set.of(AccountStatus.FROZEN, AccountStatus.CLOSED))`처럼 클래스 이름을 붙여도 JDK 21(21.0.8에서 확인)에서는 같은 오류가 난다.
다른 방법 세 가지를 찾아보고 하나를 고른다: (1) `canTransitTo` 안에서 `switch` 식으로 `this`별 허용 상태를 반환, (2) 상수 선언 뒤의 `static { }` 블록에서 `EnumMap`을 채우기, (3) 상수별 클래스 본문(constant-specific class body)에서 메서드 재정의.
</details>

<details>
<summary>힌트 3: 마스킹 테스트</summary>

AssertJ의 `assertThatThrownBy(...).hasMessageContaining("110-****-5678")`와 `.hasMessageNotContaining("110-1234-5678")`를 함께 쓴다. `extracting(e -> ((BankException) e).errorCode())`로 `ErrorCode`도 검증할 수 있다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "lab.bank.account.*"`에서 시나리오 1~19에 해당하는 테스트가 모두 PASSED로 출력되고, 시나리오 14는 9개 케이스로 출력된다
- [ ] M1-1 테스트(`lab.bank.money.*`)가 `CurrencyMismatchException` 상속 변경 후에도 모두 통과한다
- [ ] `Account.java`에 `set`으로 시작하는 메서드가 없다
- [ ] `git log --oneline`에서 테스트 커밋이 구현 커밋보다 먼저 있다

## 생각해볼 질문
1. `Account`에 `setBalance()`가 있으면 잔액 검사를 어디서 해야 하는가? 이런 구조를 "빈약한 도메인 모델(Anemic Domain Model)"이라 부르는 이유를 Martin Fowler의 글 "AnemicDomainModel"을 읽고 한 문단으로 정리한다.
2. 잔액 부족을 예외로 알리는 방법과 `boolean` 또는 결과 타입(`sealed interface WithdrawResult`)을 반환하는 방법을 호출 코드 길이, 처리를 빠뜨렸을 때 컴파일러가 잡아주는지 두 기준으로 비교한다.
3. 엔티티의 `equals`를 식별자로만 비교하는 이유는? `hashCode`에 `balance`를 넣은 `Account`를 `HashSet`에 넣고 입금하면 `contains`가 무엇을 반환하는지 테스트로 확인한다.
4. 잔액 10,000원인 `Account`에 두 스레드가 동시에 `withdraw(Money.won(10000))`을 호출하면 어떤 결과가 나올 수 있는가? 지금 예측을 적어두고 Phase 2 M2-1에서 확인한다.
