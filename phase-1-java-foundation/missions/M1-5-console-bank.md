# M1-5 [종합] 콘솔 뱅킹

> 가이드 수준: L1 · 예상 시간: 6~10h · 선행: M1-3, M1-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- M1-1~M1-4의 도메인을 조합해 메뉴 9개(0~8)를 가진 콘솔 은행 프로그램을 `./gradlew run`으로 실행한다.
- `System.in`/`System.out`을 쓰지 않는 가짜 `InputView`로 "개설 → 입금 → 출금 → 조회" 흐름을 자동 테스트한다.
- JaCoCo로 `console`을 뺀 `lab.bank` 하위 패키지마다 라인 커버리지 90% 이상을 `jacocoTestCoverageVerification` 통과로 보여준다.
- `main` 메서드 한 곳에서 `Clock`, `AccountNumberGenerator`, `InterestPolicy`를 생성자로 주입해 객체를 조립한다.

## 배경
은행 시스템의 같은 이체 로직이 인터넷뱅킹, 모바일 앱, 창구 단말, 배치에서 모두 호출된다. 이체 규칙이 화면 코드 안에 섞여 있으면 화면마다 규칙을 복사하게 되고, 한 곳만 고쳐 채널마다 다른 결과가 나오는 사고가 난다.
그래서 입출력(UI)과 유스케이스(`BankService`)를 나누고, `BankService`는 콘솔·웹 어느 쪽에서 호출되는지 모르게 만든다.
이 미션은 M1-3의 `BankService`와 M1-4의 `InterestPolicy`·`TaxCalculator`를 콘솔 UI에 연결하는 Phase 1 종합 미션이다. `main`에서 직접 `new`로 조립한 객체 그래프는 Phase 3에서 Spring 컨테이너가 대신 조립하게 된다.

## 요구사항

### 1. 패키지 구조
```
lab.bank
├── common/ money/ account/ ledger/ interest/   # M1-1~M1-4 그대로
├── application/
│   ├── BankService                       # 유스케이스. System.in/out을 참조하지 않는다
│   ├── AccountNumberGenerator            # 인터페이스
│   └── SequentialAccountNumberGenerator  # 구현체
└── console/
    ├── BankConsoleApp      # main: 객체 조립만 한다
    ├── InputView           # 인터페이스
    ├── ConsoleInputView    # Scanner(System.in) 구현
    ├── OutputView          # PrintStream으로 출력
    └── MenuController      # 입력 → BankService 호출 → 출력
```

### 2. `AccountNumberGenerator`
- `interface AccountNumberGenerator { AccountNumber next(); }`
- `SequentialAccountNumberGenerator`: `110-` 뒤에 1부터 1씩 늘어나는 8자리 순번을 4자리-4자리로 붙인다.
  - 1번째 `110-0000-0001`, 2번째 `110-0000-0002`, 10,000번째 `110-0001-0000`
  - 99,999,999번째 다음 호출은 `IllegalStateException`
  - 테스트를 위해 시작 순번을 받는 생성자 `SequentialAccountNumberGenerator(long nextSequence)`를 둔다 (기본 생성자는 1부터).

### 3. `BankService` 확장
생성자를 `BankService(Ledger ledger, Clock clock, AccountNumberGenerator generator, InterestPolicy interestPolicy, TaxCalculator taxCalculator)`로 바꾼다. M1-3 테스트도 이 생성자로 고친다.

| 시그니처 | 동작 |
|---|---|
| `Account openAccount(String ownerName, Currency currency)` | `generator.next()`로 번호를 받아 `Account.open` 후 등록하고 반환 |
| `List<Transaction> history(AccountNumber number, LocalDate from, LocalDate to)` | 계좌가 없으면 `AccountNotFoundException`, 있으면 `Ledger.history(number, from, to)` |
| `AfterTaxInterest estimateInterest(AccountNumber number, BigDecimal annualRate, LocalDate from, LocalDate to)` | 현재 잔액을 원금으로 `interestPolicy.calculate` → `taxCalculator.calculate` 결과를 반환. 잔액·거래내역은 바꾸지 않는다 |
| `void freeze(AccountNumber)`, `void unfreeze(AccountNumber)`, `void close(AccountNumber)` | 계좌를 찾아 `Account`의 같은 이름 메서드 호출 |

### 4. 콘솔 화면과 입력 규칙

```
===== Fintech Lab Bank =====
1. 계좌 개설
2. 입금
3. 출금
4. 이체
5. 거래내역 조회 (기간)
6. 거래 취소
7. 예상 이자 계산 (세전·세후)
8. 계좌 정지/해제/해지
0. 종료
선택>
```

| 메뉴 | 입력 순서 | 성공 시 출력 |
|---|---|---|
| 1 | 예금주 이름 | `계좌가 개설되었습니다: 110-0000-0001` (전체 번호. 본인에게 보여주는 화면이므로 마스킹하지 않는다) |
| 2 | 계좌번호, 금액 | `입금 완료. 잔액: KRW 10,000` |
| 3 | 계좌번호, 금액 | `출금 완료. 잔액: KRW 7,000` |
| 4 | 출금 계좌번호, 입금 계좌번호, 금액 | `이체 완료. 출금 계좌 잔액: KRW 40,000` |
| 5 | 계좌번호, 시작일, 종료일 (`yyyy-MM-dd`) | 거래 1건당 한 줄: `2026-01-15 19:00 \| DEPOSIT \| KRW 10,000 \| 잔액 KRW 10,000 \| {거래 ID}`. 0건이면 `거래내역이 없습니다.` |
| 6 | 거래 ID | `취소 완료. 잔액: KRW 0` |
| 7 | 계좌번호, 연이율(%) (`3.5` 입력 = 0.035), 시작일, 종료일 | `세전 KRW 28,767 / 소득세 KRW 4,020 / 지방소득세 KRW 400 / 세후 KRW 24,347` |
| 8 | 계좌번호, 동작(`1` 정지, `2` 해제, `3` 해지) | `계좌 상태: FROZEN` (변경 후 상태) |
| 0 | 없음 | `종료합니다.` 출력 후 `run()`이 반환된다 |

- 콘솔에서 개설하는 계좌는 KRW만이다. 금액은 1 이상의 정수만 입력받는다.
- 입금·출금·이체 적요(`memo`)는 각각 `"콘솔 입금"`, `"콘솔 출금"`, `"콘솔 이체"`로 고정한다.
- 각 메뉴 처리가 끝나면 메뉴 화면을 다시 출력한다.

**잘못된 입력** (프로그램이 종료되지 않고 메뉴로 돌아간다)
| 입력 | 출력 |
|---|---|
| 메뉴에 숫자가 아닌 값(`abc`) 또는 없는 번호(`9`, `-1`) | `잘못된 입력입니다. 메뉴 번호를 입력하세요.` |
| 금액에 숫자가 아닌 값, 소수(`1000.5`) | `잘못된 입력입니다. 금액은 정수로 입력하세요.` |
| 계좌번호 형식 오류 | `잘못된 입력입니다. 계좌번호 형식은 000-0000-0000입니다.` |
| 날짜 형식 오류 (`2026/01/01`) | `잘못된 입력입니다. 날짜 형식은 yyyy-MM-dd입니다.` |
| 입력 스트림 끝(`Ctrl+D`, 가짜 입력 소진) | `종료합니다.` 출력 후 `run()`이 반환된다 |

**도메인 예외 → 출력 메시지** (`ErrorCode`로 고른다)
| `ErrorCode` | 출력 |
|---|---|
| `INVALID_AMOUNT` | `금액은 0원보다 커야 합니다.` |
| `INSUFFICIENT_BALANCE` | `잔액이 부족합니다. (현재 잔액: KRW 5,000)` |
| `ACCOUNT_NOT_ACTIVE` | `거래할 수 없는 계좌 상태입니다. (현재 상태: FROZEN)` |
| `ILLEGAL_STATE_TRANSITION` | `요청한 상태로 바꿀 수 없습니다.` |
| `ACCOUNT_HAS_BALANCE` | `잔액이 남아 있어 해지할 수 없습니다.` |
| `ACCOUNT_NOT_FOUND` | `계좌를 찾을 수 없습니다.` |
| `SAME_ACCOUNT_TRANSFER` | `같은 계좌로는 이체할 수 없습니다.` |
| `TRANSACTION_NOT_FOUND` | `거래를 찾을 수 없습니다.` |
| `TRANSACTION_ALREADY_REVERSED` | `이미 취소된 거래입니다.` |
| `INVALID_REVERSAL` | `입금·출금 거래만 취소할 수 있습니다.` |
| `CURRENCY_MISMATCH` | `통화가 다릅니다.` |

`INSUFFICIENT_BALANCE`의 현재 잔액, `ACCOUNT_NOT_ACTIVE`의 현재 상태는 `MenuController`가 `bankService.findAccount(...)`로 조회해 넣는다.

### 5. 클래스 시그니처
| 클래스 | 시그니처 |
|---|---|
| `InputView` | `interface InputView { String readLine(String prompt); }` — 입력이 끝났으면 `null` 반환 |
| `ConsoleInputView` | `Scanner(System.in)` 사용. `hasNextLine()`이 `false`면 `null` 반환 |
| `OutputView` | `OutputView(PrintStream out)`. 메뉴·결과·오류 메시지 출력 메서드 |
| `MenuController` | `MenuController(InputView input, OutputView output, BankService bankService)`, `void run()` |
| `BankConsoleApp` | `public static void main(String[] args)`: `Clock.system(ZoneId.of("Asia/Seoul"))`, `SequentialAccountNumberGenerator`, `SimpleDailyInterestPolicy`, `TaxCalculator`, `Ledger`를 만들어 조립하고 `run()` 호출 |

### 6. `build.gradle.kts` 추가 내용
M1-4까지의 `build.gradle.kts`에 아래를 더한다. `plugins` 블록은 기존 블록을 교체하고, 나머지는 파일 끝에 붙인다.

```kotlin
plugins {
    java
    application
    jacoco
}

application {
    mainClass = "lab.bank.console.BankConsoleApp"
}

// ./gradlew run에서 키보드 입력을 프로그램으로 전달
tasks.named<JavaExec>("run") {
    standardInput = System.`in`
}

jacoco {
    toolVersion = "0.8.13"
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        html.required = true
        xml.required = false
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.test)
    violationRules {
        rule {
            element = "PACKAGE"
            includes = listOf("lab.bank.*")
            excludes = listOf("lab.bank.console")
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.90".toBigDecimal()
            }
        }
    }
}
```

- 실행: `./gradlew run -q --console=plain` (`-q --console=plain`은 Gradle 진행 표시가 메뉴 화면과 섞이지 않게 한다)
- 커버리지: `./gradlew test jacocoTestReport jacocoTestCoverageVerification`
- 리포트: `build/reports/jacoco/test/html/index.html`을 브라우저로 연다. Codespaces에서는 VS Code 탐색기에서 파일을 우클릭 → "Download..."로 받아 연다.
- 패키지 하나라도 라인 커버리지가 0.90 미만이면 `Rule violated for package lab.bank.xxx: lines covered ratio is 0.xx, but expected minimum is 0.90`과 함께 빌드가 실패한다.
- 위 설정은 Gradle 8.14.3 + JDK 21에서 2026-11-10에 실행해 확인했다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 기본 `SequentialAccountNumberGenerator` | `next()` 2회 | `110-0000-0001`, `110-0000-0002` |
| 2 | `new SequentialAccountNumberGenerator(10000)` | `next()` | `110-0001-0000` |
| 3 | `new SequentialAccountNumberGenerator(99999999)` | `next()` 2회 | 첫 번째 `110-9999-9999`, 두 번째 `IllegalStateException` |
| 4 | `BankService`(`SimpleDailyInterestPolicy`), 계좌 잔액 10,000,000 | `estimateInterest(번호, new BigDecimal("0.035"), 2026-01-01, 2026-01-31)` | `gross` 28,767, `incomeTax` 4,020, `localIncomeTax` 400, `net` 24,347, 잔액 10,000,000 그대로, 거래내역 건수 그대로 |
| 5 | 존재하지 않는 계좌 | `history(없는 번호, 2026-01-01, 2026-01-31)` | `AccountNotFoundException` |
| 6 | 고정 Clock `2026-01-15T10:00:00Z`/`Asia/Seoul`, 가짜 입력 `1`, `홍길동`, `2`, `110-0000-0001`, `10000`, `3`, `110-0000-0001`, `3000`, `5`, `110-0000-0001`, `2026-01-01`, `2026-01-31`, `0` | `run()` | 출력에 `계좌가 개설되었습니다: 110-0000-0001`, `입금 완료. 잔액: KRW 10,000`, `출금 완료. 잔액: KRW 7,000`, `2026-01-15 19:00 \| DEPOSIT \| KRW 10,000`, `2026-01-15 19:00 \| WITHDRAWAL \| KRW 3,000`, `종료합니다.`가 이 순서로 포함 |
| 7 | 가짜 입력 `abc`, `9`, `0` | `run()` | `잘못된 입력입니다. 메뉴 번호를 입력하세요.` 2회 출력 후 `종료합니다.` |
| 8 | 계좌 개설 후 가짜 입력 `2`, `110-0000-0001`, `1000.5`, `0` | `run()` | `잘못된 입력입니다. 금액은 정수로 입력하세요.`, 잔액 0 그대로 |
| 9 | 계좌 개설·5,000 입금 후 가짜 입력 `3`, `110-0000-0001`, `10000`, `0` | `run()` | `잔액이 부족합니다. (현재 잔액: KRW 5,000)` |
| 10 | 가짜 입력 `2`, `110-0000-0099`, `1000`, `0` | `run()` | `계좌를 찾을 수 없습니다.` |
| 11 | 가짜 입력 `1`, `홍길동` (그 뒤 입력 없음) | `run()` | 예외 없이 반환, 마지막 출력 `종료합니다.` |
| 12 | 계좌 개설 후 가짜 입력 `8`, `110-0000-0001`, `1`, `2`, `110-0000-0001`, `1000`, `0` | `run()` | `계좌 상태: FROZEN`, `거래할 수 없는 계좌 상태입니다. (현재 상태: FROZEN)` |

6~12의 출력은 `OutputView`에 `new PrintStream(ByteArrayOutputStream, true, StandardCharsets.UTF_8)`를 넘겨 문자열로 검사한다.

## 제약
- `application`, `account`, `ledger`, `interest`, `money`, `common` 패키지의 코드는 `System.in`, `System.out`, `Scanner`를 참조하지 않는다.
- `console` 패키지 밖의 클래스는 `console` 패키지를 import하지 않는다.
- `MenuController`는 `BankService`의 public 메서드만 호출한다. `Account`의 상태 변경 메서드(`deposit` 등)를 직접 호출하지 않는다.
- 사용자에게 Java 예외 스택 트레이스를 출력하지 않는다. `BankException`과 입력 형식 오류는 위 표의 메시지로 바꾼다.

## 힌트
<details>
<summary>힌트 1: 가짜 InputView</summary>

`src/test`에 `InputView`를 구현한 클래스를 만들고, 생성자로 받은 `List<String>`을 `ArrayDeque`에 넣어 `readLine`마다 하나씩 꺼낸다. 큐가 비면 `null`을 반환하면 시나리오 11을 재현할 수 있다.
`readLine(prompt)`가 받은 프롬프트를 리스트에 모아 두면 "금액을 묻기 전에 계좌번호를 물었는가"도 검증할 수 있다.
</details>

<details>
<summary>힌트 2: 입력 파싱 오류를 한 곳에서 처리</summary>

`Long.parseLong`은 `"1000.5"`, `"abc"`에서 `NumberFormatException`, `LocalDate.parse`는 `"2026/01/01"`에서 `DateTimeParseException`을 던진다. 메뉴 하나를 처리하는 메서드를 `try`로 감싸 이 예외들과 `BankException`을 잡고, 메시지를 고른 뒤 메뉴로 돌아간다.
`catch (Exception e)`로 모든 예외를 삼키면 내 코드의 `NullPointerException` 같은 버그도 "잘못된 입력"으로 숨겨진다. 잡을 예외 타입을 나열한다.
</details>

<details>
<summary>힌트 3: 커버리지가 90%에 못 미칠 때</summary>

`build/reports/jacoco/test/html/index.html`에서 패키지 → 클래스 → 소스 순서로 들어가면 실행되지 않은 줄이 빨간색으로 표시된다. 빨간 줄이 예외 분기라면 그 예외를 일으키는 테스트 시나리오를 추가한다.
커버리지 숫자를 올리려고 검증(`assertThat`) 없는 테스트를 추가하지 않는다. JaCoCo는 줄이 실행되었는지만 세고 결과가 맞는지는 확인하지 않는다.
</details>

## 완료 기준
- [ ] `./gradlew test jacocoTestReport jacocoTestCoverageVerification`이 `BUILD SUCCESSFUL`로 끝난다
- [ ] `build/reports/jacoco/test/html/index.html`에서 `lab.bank.console`을 뺀 패키지의 Lines 커버리지가 모두 90% 이상이고, 이 화면 캡처가 PR 본문에 있다
- [ ] `src/main/java/lab/bank`에서 `System.out`, `System.in`, `Scanner`를 검색하면 `console` 패키지에서만 나온다
- [ ] `./gradlew run -q --console=plain`으로 실행해 메뉴 1~8을 각각 1회 이상 실행했다. 이 과정에서 찾은 버그마다 재현 테스트 커밋(`test:`)이 수정 커밋(`fix:`)보다 먼저 있고, PR 본문에 버그 목록이 있다 (버그가 없었다면 "없음"과 실행한 입력 목록)

## 생각해볼 질문
1. `BankConsoleApp.main`에서 `new`로 조립하는 객체 수를 세어 본다. 클래스가 100개로 늘고 `BankService`의 생성자 인자가 하나 추가되면 `main`의 몇 군데를 고쳐야 하는가? Phase 3 M3-1에서 만들 DI 컨테이너가 이 중 무엇을 대신하는가?
2. UI를 웹(Phase 4의 Spring MVC 컨트롤러)으로 바꿀 때 새로 만들 클래스와 그대로 쓸 클래스를 패키지 단위로 나눠 적는다. `MenuController`에 있는 로직 중 웹으로 옮길 때 다시 작성해야 하는 것은 무엇인가?
3. 라인 커버리지 100%인데도 버그가 남는 예를 이 미션 코드에서 하나 찾는다. JaCoCo의 `BRANCH` 카운터로 바꾸면 그 버그를 찾을 수 있는가?
4. Phase 1에서 테스트를 먼저 쓰기 가장 어려웠던 클래스 3개와, 각각 어려웠던 이유(설계가 정해지지 않음, 기대값 계산, 시간 의존 등)를 적는다.
