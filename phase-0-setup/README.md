# Phase 0 — 개발 환경 & 학습 시스템 구축

## 학습 목표
- JDK 21, IntelliJ, Gradle, Git으로 **스스로 프로젝트를 만들고 테스트를 돌릴 수 있다.**
- Gradle이 무엇을 해주는지(의존성, 빌드, 테스트) 설명할 수 있다.

---

## M0-1 개발 환경 세팅

### 할 일
1. **JDK 21** 설치 (SDKMAN 추천: `sdk install java 21-tem`) → `java -version` 확인
2. **IntelliJ IDEA** 설치 (Community로 충분, Ultimate면 Spring 지원이 더 좋음)
3. **Git** 설정
   ```bash
   git config --global user.name "내 이름"
   git config --global user.email "내 이메일"
   ```
4. **Docker Desktop** 설치 (Phase 5부터 Testcontainers, MySQL에 필요. 지금 설치만)
5. 이 레포를 clone 해서 IntelliJ로 열기

### 대안: 설치 없이 브라우저에서 개발하기 (GitHub Codespaces)
회사 VDI처럼 프로그램을 설치할 수 없는 환경에서는 브라우저만으로 개발할 수 있다.
이 레포에는 `.devcontainer/devcontainer.json`이 있어서 Java 21, Gradle, Docker, VS Code Java 확장이 자동으로 준비된다.

1. GitHub 레포 페이지 → 초록색 **Code** 버튼 → **Codespaces** 탭 → **Create codespace on main**
2. 첫 실행은 몇 분 걸린다. 브라우저에 VS Code가 열리면 터미널에서 `java -version` 확인
3. 다 쓰면 왼쪽 아래 **Codespaces** → **Stop Current Codespace** (켜둔 시간만큼 무료 사용량이 차감됨)

> ⚠️ 회사 장비에서 쓰기 전에 회사 보안 정책(외부 개발 서비스 사용, 개인 용도 사용)을 먼저 확인할 것.
> VS Code 단축키는 IntelliJ와 다르다. 명령 팔레트(`F1` 또는 `Ctrl Shift P`)에서 "Rename", "Extract" 등을 검색하면 된다.

### IntelliJ 필수 단축키 (macOS / Windows)
| 기능 | macOS | Windows |
|---|---|---|
| 아무거나 찾기 | Shift 두 번 | Shift 두 번 |
| 자동 완성/빠른 수정 | ⌥ Enter | Alt Enter |
| 테스트 ↔ 구현 이동 | ⌘ ⇧ T | Ctrl Shift T |
| 메서드 추출 | ⌘ ⌥ M | Ctrl Alt M |
| 변수 추출 | ⌘ ⌥ V | Ctrl Alt V |
| 이름 변경 | ⇧ F6 | Shift F6 |
| 현재 테스트 실행 | ⌃ ⇧ R | Ctrl Shift F10 |
| 마지막 실행 재실행 | ⌃ R | Shift F10 |
| 코드 정렬 | ⌘ ⌥ L | Ctrl Alt L |
| 생성(getter, 생성자 등) | ⌘ N | Alt Insert |

> 일부러 마우스를 쓰지 말고 단축키로 해보자. 리팩터링 속도가 학습 속도다.

---

## M0-2 첫 Gradle 프로젝트 & 첫 테스트

IntelliJ의 "New Project" 마법사 대신 **직접 파일을 만들어** Gradle 구조를 이해한다.

### 1) 디렉터리 만들기

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

```bash
cd phase-0-setup/workspace
gradle wrapper --gradle-version 8.14.3   # 로컬에 gradle이 없으면 IntelliJ에서 프로젝트를 열면 자동 생성 가능
./gradlew --version
```

> **Wrapper를 쓰는 이유:** 팀원 모두가(CI 포함) 같은 Gradle 버전을 쓰게 하려고.
> `gradlew`, `gradle/wrapper/*`는 커밋한다. `.gradle/`, `build/`는 커밋하지 않는다.

### 5) 테스트 먼저 작성 — `GreeterTest.java`

요구사항:
- `new Greeter().greet("민수")` → `"안녕하세요, 민수님"`
- 이름이 `null`이거나 공백이면 `IllegalArgumentException`

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
        Greeter greeter = new Greeter();

        String result = greeter.greet("민수");

        assertThat(result).isEqualTo("안녕하세요, 민수님");
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   "})
    @DisplayName("이름이 비어 있으면 예외가 발생한다")
    void greetWithBlankName(String name) {
        Greeter greeter = new Greeter();

        assertThatThrownBy(() -> greeter.greet(name))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

### 6) 실행 → 실패 확인 → 구현 → 통과

```bash
./gradlew test       # 컴파일 실패 (Greeter 없음) ← 이것도 "실패하는 테스트"다
```

`Greeter`를 구현하고 다시 `./gradlew test` → 초록불.

### 7) 커밋 & PR
```bash
git checkout -b phase0/m0-2-hello
git add .
git commit -m "test: Greeter 인사말 테스트 추가"
# ... 구현 후
git commit -m "feat: Greeter 구현"
git push -u origin phase0/m0-2-hello
```

### 생각해볼 질문
1. `testImplementation`과 `implementation`의 차이는?
2. `platform("org.junit:junit-bom:...")`(BOM)은 무슨 역할을 하나?
3. Given / When / Then 구조로 테스트를 나누면 무엇이 좋은가?
4. `./gradlew test`를 두 번 연속 실행하면 두 번째는 왜 빠른가? (`UP-TO-DATE`)

---

## 완료 체크리스트
- [ ] `./gradlew test`가 터미널에서 통과한다
- [ ] IntelliJ에서 테스트 하나만 골라 실행할 수 있다
- [ ] 첫 PR을 올리고 머지했다
- [ ] 첫 TIL을 작성했다
