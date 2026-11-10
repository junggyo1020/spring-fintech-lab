# M0-2 첫 Gradle 프로젝트 & 첫 테스트

> 가이드 수준: L1 · 예상 시간: 2~3h · 선행: M0-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- IDE의 "New Project" 마법사 없이 `settings.gradle.kts`, `build.gradle.kts`, 소스 디렉터리를 직접 만들어 `./gradlew test`를 실행한다.
- 테스트를 먼저 작성하고, 컴파일 실패(빨간불) → 구현 → 통과(초록불) 순서를 커밋 2개로 남긴다.
- `./gradlew test`를 두 번 연속 실행했을 때 두 번째 출력에 나오는 `UP-TO-DATE`의 의미를 설명한다.

## 배경
Spring Initializr나 IDE 마법사가 만든 프로젝트는 빌드 설정 파일을 열어보지 않아도 실행된다. 그 상태로 Phase 5에서 MySQL 드라이버나 Testcontainers 의존성을 추가하면, 어느 블록의 어느 구성(`implementation`, `testImplementation`)에 넣어야 하는지 판단할 수 없다.
금융 시스템 빌드에서 테스트 라이브러리가 운영 jar에 섞이거나, 팀원마다 다른 Gradle 버전으로 빌드해 산출물이 달라지는 문제는 모두 빌드 설정을 읽지 못해서 생긴다.
이 미션은 M0-1에서 설치한 JDK 21과 Gradle 8.14.3으로 빌드 파일을 한 줄씩 직접 작성한다. 여기서 만든 `build.gradle.kts`는 Phase 1 workspace에서 그대로 복사해 쓴다.

## 요구사항

### 1) 디렉터리 구조
`phase-0-setup/workspace/` 아래에 다음 구조를 만든다.

```
phase-0-setup/workspace/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/lab/hello/Greeter.java
    └── test/java/lab/hello/GreeterTest.java
```

### 2) `settings.gradle.kts`

```kotlin
rootProject.name = "hello"
```

### 3) `build.gradle.kts`

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core:3.27.3")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("passed", "failed", "skipped")
    }
}
```

### 4) Gradle Wrapper 생성
Wrapper 파일은 설치된 Gradle로 한 번만 만든다. M0-1에서 `sdk install gradle 8.14.3`으로 설치했거나, Codespaces(devcontainer)를 쓰면 Gradle 8.14.3이 이미 설치되어 있다.

```bash
cd phase-0-setup/workspace
gradle --version                          # Gradle 8.14.3 확인
gradle wrapper --gradle-version 8.14.3    # gradlew, gradlew.bat, gradle/wrapper/* 생성
./gradlew --version                       # Wrapper가 Gradle 8.14.3을 내려받아 실행한다
```

생성된 `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties` 4개 파일을 커밋한다. `.gradle/`, `build/`는 레포 `.gitignore`에 이미 등록되어 있다.

### 5) `Greeter` 명세

| 시그니처 | 동작 |
|---|---|
| `public class Greeter` | 기본 생성자만 있다 |
| `public String greet(String name)` | `"안녕하세요, " + name + "님"`을 반환한다 |
| 같은 메서드, `name`이 `null`, `""`, 공백만 있는 문자열 | `IllegalArgumentException`을 던진다 |

이름 앞뒤 공백은 그대로 둔다. `greet(" 민수")`는 `"안녕하세요,  민수님"`(쉼표 뒤 공백 2개)을 반환한다.

### 6) 테스트 먼저 작성 — `GreeterTest.java`
아래 코드를 직접 타이핑한다. 복사·붙여넣기를 하지 않는다. 이 Phase는 JUnit 5와 AssertJ 문법을 처음 보는 단계라 테스트 전체를 제공한다.

```java
package lab.hello;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GreeterTest {

    @Test
    @DisplayName("이름을 받아 인사말을 만든다")
    void greet() {
        // given
        Greeter greeter = new Greeter();

        // when
        String result = greeter.greet("민수");

        // then
        assertThat(result).isEqualTo("안녕하세요, 민수님");
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   "})
    @DisplayName("이름이 비어 있으면 예외가 발생한다")
    void greetWithBlankName(String name) {
        // given
        Greeter greeter = new Greeter();

        // when & then
        assertThatThrownBy(() -> greeter.greet(name))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

### 7) 실행 → 실패 확인 → 구현 → 통과

```bash
./gradlew test       # 컴파일 실패: "cannot find symbol ... class Greeter". 이것도 실패하는 테스트다
```

`Greeter`를 구현하고 다시 `./gradlew test`를 실행해 5개 테스트가 PASSED로 출력되는 것을 확인한다. 이어서 같은 명령을 한 번 더 실행하고 `> Task :test UP-TO-DATE`가 출력되는 것을 확인한다.

### 8) 커밋 & PR

```bash
git checkout -b phase0/m0-2-hello
git add phase-0-setup/workspace
git commit -m "[test] Greeter 인사말 테스트 추가"
# Greeter 구현 후
git add phase-0-setup/workspace
git commit -m "[feat] Greeter 구현"
git push -u origin phase0/m0-2-hello
```

GitHub에서 PR을 연다. PR 본문에 `./gradlew test` 출력 중 PASSED 5줄을 붙인다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `new Greeter()` | `greet("민수")` | `"안녕하세요, 민수님"` |
| 2 | `new Greeter()` | `greet(null)` | `IllegalArgumentException` |
| 3 | `new Greeter()` | `greet("")` | `IllegalArgumentException` |
| 4 | `new Greeter()` | `greet(" ")` | `IllegalArgumentException` |
| 5 | `new Greeter()` | `greet("   ")` | `IllegalArgumentException` |
| 6 | `Greeter.java`가 없는 상태 | `./gradlew test` | `compileTestJava` 단계에서 `BUILD FAILED` |
| 7 | 1~5 통과 후 파일 변경 없음 | `./gradlew test` 재실행 | `> Task :test UP-TO-DATE` |

## 제약
- IDE의 "New Project" 마법사, Spring Initializr를 쓰지 않는다. 빌드 파일을 직접 작성하는 것이 이 미션의 목적이다.
- `gradle test`(설치된 Gradle)가 아니라 `./gradlew test`(Wrapper)로 실행한다. CI(M0-3)도 Wrapper로 실행한다.
- 테스트 커밋(`[test]`)과 구현 커밋(`[feat]`)을 하나로 합치지 않는다. 리뷰어가 커밋 순서로 테스트를 먼저 썼는지 확인한다.

## 힌트
<details>
<summary>힌트 1: 공백 문자열 검사</summary>

`String`의 Javadoc에서 `isBlank()`(Java 11 추가)를 찾아본다. `isEmpty()`와 어떤 입력에서 결과가 다른가? `null`에 대해 `isBlank()`를 호출하면 무엇이 발생하는가?
</details>

<details>
<summary>힌트 2: 테스트가 0개 실행될 때</summary>

`./gradlew test`가 성공했는데 PASSED 줄이 하나도 없다면 `tasks.test { useJUnitPlatform() }`가 빠졌는지, `testRuntimeOnly("org.junit.platform:junit-platform-launcher")`가 있는지 확인한다.
`build/reports/tests/test/index.html`을 브라우저로 열면 실행된 테스트 수가 보인다.
</details>

<details>
<summary>힌트 3: gradle 명령을 찾을 수 없을 때</summary>

`gradle: command not found`가 나오면 M0-1 요구사항 2번(`sdk install gradle 8.14.3`)을 실행한다. Windows에서 SDKMAN을 쓰지 않으면 gradle.org의 "Installing manually" 절차로 8.14.3 바이너리 배포판을 받아 `PATH`에 추가한다.
</details>

## 완료 기준
- [ ] `phase-0-setup/workspace`에서 `./gradlew test`를 실행하면 `GreeterTest`의 테스트 5개가 PASSED로 출력되고 `BUILD SUCCESSFUL`이 나온다
- [ ] `gradle/wrapper/gradle-wrapper.properties`의 `distributionUrl`에 `gradle-8.14.3-bin.zip`이 들어 있고, 이 파일과 `gradlew`가 커밋되어 있다
- [ ] `git log --oneline` 에서 `[test]` 커밋이 `[feat]` 커밋보다 먼저 있다
- [ ] PR이 열려 있고 본문에 PASSED 5줄이 붙어 있다

## 생각해볼 질문
1. JUnit을 `implementation`으로 선언하면 무엇이 달라지는가? `./gradlew dependencies --configuration runtimeClasspath` 출력을 두 경우로 비교해서 답한다.
2. `platform("org.junit:junit-bom:5.11.4")`를 쓰면 `junit-jupiter`에 버전을 적지 않아도 되는 이유는? BOM이 없으면 `junit-jupiter`와 `junit-platform-launcher`의 버전을 각각 어떻게 맞춰야 하는가?
3. 테스트 메서드를 given / when / then 세 부분으로 나누면, 테스트가 실패했을 때 원인을 찾는 순서가 어떻게 달라지는가?
4. Phase 1에서는 `Greeter` 대신 `Money` 같은 도메인 객체를 테스트한다. `Money`의 `plus`가 원본 객체를 바꾸지 않는다는 것을 테스트하려면 then 절에 무엇을 검증해야 하는가?
