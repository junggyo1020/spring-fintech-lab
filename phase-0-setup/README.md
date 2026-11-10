# Phase 0 — 개발 환경 & 학습 시스템 구축 (0.5주)

> 가이드 수준: L1 · 선행: 없음 · 이 Phase의 workspace 시작 방법: 빈 디렉터리에서 직접 생성

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- 터미널에서 `java -version`, `./gradlew --version`, `git --version`을 실행해 JDK 21, Gradle 8.14.3, Git이 설치된 것을 보여준다.
- IDE 마법사 없이 `settings.gradle.kts`, `build.gradle.kts`를 직접 작성해 Gradle 프로젝트를 만들고 `./gradlew test`로 테스트를 실행한다.
- `implementation`과 `testImplementation`, Gradle과 Gradle Wrapper의 차이를 각각 한 문장으로 설명한다.
- 레포에 push하거나 PR을 열 때 GitHub Actions가 `./gradlew test`를 실행하고, 테스트가 실패하면 PR에 빨간 X가 표시되게 만든다.

## 이 Phase의 결과물

```
spring-fintech-lab/
├── .github/workflows/ci.yml          # M0-3
└── phase-0-setup/workspace/
    ├── ENVIRONMENT.md                # M0-1: 설치 확인 기록
    ├── settings.gradle.kts           # M0-2
    ├── build.gradle.kts
    ├── gradlew, gradlew.bat
    ├── gradle/wrapper/gradle-wrapper.jar
    ├── gradle/wrapper/gradle-wrapper.properties
    └── src/
        ├── main/java/lab/hello/Greeter.java
        └── test/java/lab/hello/GreeterTest.java
```

## 핵심 개념 정리 (미션 전에 읽기)

### 1. Gradle이 하는 일
Gradle은 `build.gradle.kts`에 적힌 설정을 읽어 다음 세 가지를 대신 실행한다.

| 일 | 직접 하면 | Gradle이 하면 |
|---|---|---|
| 의존성 다운로드 | JUnit, AssertJ jar를 Maven Central에서 받아 클래스패스에 추가 | `dependencies { }` 블록에 좌표(`group:artifact:version`)만 적는다 |
| 컴파일 | `javac -d out src/main/java/**/*.java` | `./gradlew compileJava` |
| 테스트 실행 | JUnit Platform 런처를 클래스패스와 함께 실행 | `./gradlew test`, 결과는 `build/reports/tests/test/index.html` |

**의존성 구성(configuration)**
- `implementation`: `src/main` 코드가 컴파일·실행할 때 쓴다. 테스트 코드에서도 보인다.
- `testImplementation`: `src/test` 코드에서만 쓴다. JUnit, AssertJ는 운영 코드에 들어가면 안 되므로 여기에 둔다.
- `testRuntimeOnly`: 테스트 실행 시에만 클래스패스에 올라간다. 테스트 코드에서 import하지 않는 JUnit Platform 런처가 여기 해당한다.

**작업(task)과 증분 빌드**: `./gradlew test`는 `compileJava → compileTestJava → test` 순서로 작업을 실행한다. 입력 파일이 바뀌지 않은 작업은 다시 실행하지 않고 `UP-TO-DATE`로 표시한다.

### 2. Gradle Wrapper
Wrapper는 "이 프로젝트는 Gradle 8.14.3으로 빌드한다"를 파일로 고정하는 장치다.

| 파일 | 역할 | 커밋 여부 |
|---|---|---|
| `gradlew`, `gradlew.bat` | Wrapper 실행 스크립트 (macOS·Linux / Windows) | 커밋한다 |
| `gradle/wrapper/gradle-wrapper.properties` | `distributionUrl`에 Gradle 버전(8.14.3)이 적혀 있다 | 커밋한다 |
| `gradle/wrapper/gradle-wrapper.jar` | 지정 버전의 Gradle을 내려받아 실행하는 프로그램 | 커밋한다 (레포 `.gitignore`에 예외로 등록되어 있다) |
| `.gradle/`, `build/` | 캐시와 빌드 결과물 | 커밋하지 않는다 |

- `gradle ...`은 내 컴퓨터에 설치된 Gradle을 실행한다. 설치 버전이 사람마다 다를 수 있다.
- `./gradlew ...`는 `gradle-wrapper.properties`에 적힌 버전을 처음 한 번 내려받아(`~/.gradle/wrapper/dists/`) 실행한다. 로컬 설치 버전과 무관하게 모두가 8.14.3을 쓴다. CI(M0-3)도 이 스크립트로 빌드한다.
- 설치된 Gradle은 Wrapper 파일을 처음 생성할 때(`gradle wrapper`) 한 번만 필요하다.

## 워크스페이스 만들기
M0-2에서 `phase-0-setup/workspace/`에 직접 만든다. 파일 내용과 명령어는 [M0-2](missions/M0-2-first-gradle-project.md)에 있다.

| 항목 | 값 |
|---|---|
| `rootProject.name` | `hello` |
| 루트 패키지 | `lab.hello` |
| Java | 21 (Gradle toolchain) |
| Gradle | 8.14.3 (Wrapper) |
| 테스트 의존성 | `org.junit:junit-bom:5.11.4`, `org.junit.jupiter:junit-jupiter`, `org.assertj:assertj-core:3.27.3`, `org.junit.platform:junit-platform-launcher` |

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 0.5주 (4~7시간) | M0-1, M0-2, M0-3 | 이 README의 핵심 개념 1~2절, Gradle 공식 문서 "Building Java Applications Sample" |

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M0-1](missions/M0-1-dev-environment.md) | 개발 환경 세팅 | 1~2h |
| [M0-2](missions/M0-2-first-gradle-project.md) | 첫 Gradle 프로젝트 & 첫 테스트 | 2~3h |
| [M0-3](missions/M0-3-github-actions-ci.md) | GitHub Actions CI | 1~2h |

## 읽을거리
- Gradle 공식 문서: "Building Java Applications Sample", "The Gradle Wrapper" (Gradle 8.14.3 User Manual)
- Gradle 공식 문서: "Dependency configurations" 절 (`implementation`, `testImplementation`, `testRuntimeOnly`)
- JUnit 5 User Guide: "Writing Tests" 장의 "Annotations", "Parameterized Tests" 절
- GitHub Docs: "Building and testing Java with Gradle"

## 완료 기준
- [ ] `phase-0-setup/workspace/ENVIRONMENT.md`에 M0-1의 확인 명령 4개와 출력이 기록되어 있다
- [ ] `phase-0-setup/workspace`에서 `./gradlew test`를 실행하면 `GreeterTest`의 테스트 5개가 PASSED로 출력되고 `BUILD SUCCESSFUL`이 나온다
- [ ] IDE에서 `GreeterTest`의 테스트 메서드 하나만 골라 실행하는 방법을 보여줄 수 있다
- [ ] PR을 열었을 때 GitHub Actions `ci` 워크플로가 초록 체크로 끝나고, 그 PR을 main에 머지했다
- [ ] `til/`에 첫 TIL을 `til/TEMPLATE.md` 형식으로 작성했다
