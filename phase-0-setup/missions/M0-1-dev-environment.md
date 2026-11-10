# M0-1 개발 환경 세팅

> 가이드 수준: L1 · 예상 시간: 1~2h · 선행: 없음

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `java -version` 출력에서 JDK 21이 기본 JDK로 잡힌 것을 보여준다.
- `git config --global --list`로 커밋 작성자 이름과 이메일이 설정된 것을 보여준다.
- 이 레포를 IDE로 열고, IntelliJ 단축키 10개(아래 표)를 마우스 없이 실행한다.
- 설치 확인 명령 4개의 출력을 `phase-0-setup/workspace/ENVIRONMENT.md`에 기록한다.

## 배경
같은 코드라도 JDK 버전이 다르면 컴파일 결과가 달라진다. 예를 들어 `record`는 Java 16, `switch` 패턴 매칭(JEP 441)은 Java 21부터 정식 기능이라 `switch` 패턴 매칭을 쓴 코드는 JDK 17에서 컴파일 오류가 난다.
금융 시스템에서는 개발자 PC, CI 서버, 운영 서버의 JDK 버전이 하나라도 다르면 "내 PC에서는 통과했는데 운영에서 실패하는" 배포 사고가 난다.
이 미션은 이후 모든 미션이 쓰는 도구의 버전을 확인하고 기록으로 남기는 단계다. 다음 미션 M0-2에서 이 JDK로 첫 Gradle 프로젝트를 만든다.

## 요구사항

### 방법 A: 내 PC에 설치하기

1. **JDK 21 설치 (SDKMAN)**
   SDKMAN은 `21-tem` 같은 줄임 이름을 받지 않는다. 목록에서 정확한 식별자를 복사해서 설치한다.
   ```bash
   curl -s "https://get.sdkman.io" | bash      # SDKMAN 설치 (macOS, Linux, WSL)
   source "$HOME/.sdkman/bin/sdkman-init.sh"
   sdk list java                               # Temurin 줄에서 21.0.x-tem 형식의 Identifier를 찾는다
   sdk install java 21.0.x-tem                 # x 자리에 목록에서 복사한 실제 번호를 넣는다
   sdk default java 21.0.x-tem
   java -version                               # 첫 줄에 "21.0."이 보여야 한다
   ```
   - Windows(WSL 없음)는 Adoptium 사이트(adoptium.net)에서 Temurin 21 JDK 설치 파일(`.msi`)을 받아 설치한다. 설치 화면에서 "Set JAVA_HOME variable" 항목을 켠다.
2. **Gradle 8.14.3 설치** (M0-2에서 Wrapper 파일을 만들 때 한 번만 쓴다)
   ```bash
   sdk install gradle 8.14.3
   gradle --version                            # "Gradle 8.14.3"
   ```
3. **IntelliJ IDEA 설치**
   - 2025.3 버전부터 Community와 Ultimate가 "IntelliJ IDEA" 하나의 배포판으로 합쳐졌다. 구독 없이 Java·Gradle·Git 핵심 기능을 쓸 수 있고, Spring 전용 지원 같은 Ultimate 기능은 구독이 있어야 켜진다.
   - Phase 0~2는 구독 없이 진행할 수 있다. Phase 3부터 쓰는 Spring 기능도 Gradle 실행과 코드 편집은 구독 없이 가능하다.
4. **Git 설정**
   ```bash
   git config --global user.name "내 이름"
   git config --global user.email "GitHub에 등록한 이메일"
   git config --global init.defaultBranch main
   git config --global --list                  # 위 3개 값이 보여야 한다
   ```
5. **Docker Desktop 설치**: Phase 5부터 MySQL, Testcontainers에 쓴다. 지금은 설치 후 `docker --version`만 확인한다.
6. **레포 열기**: 이 레포를 fork한 뒤 `git clone`하고, IntelliJ에서 File → Open으로 레포 루트 폴더를 연다.

### 방법 B: 설치 없이 브라우저에서 개발하기 (GitHub Codespaces)
프로그램을 설치할 수 없는 PC(회사 VDI 등)에서 쓴다. 레포의 `.devcontainer/devcontainer.json`이 Java 21, Gradle 8.14.3, VS Code Java 확장(`vscjava.vscode-java-pack`, `vscjava.vscode-gradle`)을 준비한다. Docker는 아직 포함되어 있지 않으며 Phase 5에서 추가한다.

1. GitHub 레포 페이지 → 초록색 **Code** 버튼 → **Codespaces** 탭 → **Create codespace on main**
2. 브라우저에 VS Code가 열리면 터미널에서 `java -version`, `gradle --version`을 실행한다.
3. 작업을 마치면 왼쪽 아래 **Codespaces** → **Stop Current Codespace**를 누른다. 실행 중인 시간만큼 GitHub 계정의 무료 사용량(core-hours)이 차감된다.

> 회사 장비에서 쓰기 전에 회사 보안 정책에서 외부 개발 서비스 사용과 개인 용도 사용이 허용되는지 먼저 확인한다.
> VS Code 단축키는 IntelliJ와 다르다. 명령 팔레트(`F1` 또는 `Ctrl Shift P`)에서 "Rename Symbol", "Refactor"를 검색해 실행한다.

### IntelliJ 단축키 10개 (macOS / Windows)
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

### 설치 확인 기록: `phase-0-setup/workspace/ENVIRONMENT.md`
아래 4개 명령의 출력을 그대로 붙여 넣고, 맨 위에 OS 이름·버전과 기록 날짜를 적는다.

| 명령 | 출력에서 확인할 것 |
|---|---|
| `java -version` | `21.0.`으로 시작하는 버전 |
| `gradle --version` | `Gradle 8.14.3` |
| `git --version` | 버전 번호 (2.x) |
| `docker --version` | 버전 번호. Codespaces 사용자는 "Phase 5에서 설치"라고 적는다 |

IDE 이름과 버전(IntelliJ는 Help → About, VS Code는 Help → About)도 한 줄 적는다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | SDKMAN으로 JDK 21 설치 후 새 터미널 | `java -version` | 첫 줄에 `21.0.`이 포함된다 |
| 2 | 같은 터미널 | `echo $JAVA_HOME` (Windows: `echo %JAVA_HOME%`) | JDK 21 설치 경로가 출력된다 |
| 3 | Gradle 설치 후 | `gradle --version` | `Gradle 8.14.3`과 `Launcher JVM: 21.0.x`가 출력된다 |
| 4 | Git 설정 후 | `git config --global user.email` | 4단계에서 입력한 이메일이 출력된다 |
| 5 | IntelliJ에서 레포를 연 상태 | Shift 두 번 → `curriculum-map` 입력 | 검색 결과에 `docs/curriculum-map.md`가 나오고, Enter를 누르면 파일이 열린다 |

## 제약
- JDK는 21을 쓴다. M0-2의 `build.gradle.kts`가 toolchain으로 Java 21을 요구하므로, JDK 21이 설치되어 있지 않으면 `./gradlew test`가 "요구 조건(languageVersion=21)에 맞는 Java 설치를 찾을 수 없다"는 오류로 멈춘다. CI(M0-3)도 JDK 21을 쓴다.
- `sdk install java 21-tem`처럼 목록에 없는 식별자를 쓰지 않는다. SDKMAN은 "is not available"을 출력하고 아무것도 설치하지 않는다.
- `ENVIRONMENT.md`에 출력을 손으로 다시 타이핑하지 않고 터미널 출력을 복사해 붙인다.

## 힌트
<details>
<summary>힌트 1: java -version이 다른 버전을 보여줄 때</summary>

`which java`(Windows: `where java`)로 어떤 경로의 `java`가 먼저 잡히는지 확인한다. SDKMAN이 설치한 JDK는 `~/.sdkman/candidates/java/current/bin/java`에 있다.
`sdk current java`로 SDKMAN이 기본값으로 쓰는 버전을 확인하고, 다르면 `sdk default java <식별자>`를 다시 실행한 뒤 새 터미널을 연다.
</details>

<details>
<summary>힌트 2: IntelliJ가 프로젝트 JDK를 못 찾을 때</summary>

File → Project Structure → Project → SDK에서 "Add SDK" → "JDK..."를 고르고 `~/.sdkman/candidates/java/21.0.x-tem` 경로를 지정한다.
Settings → Build, Execution, Deployment → Build Tools → Gradle의 "Gradle JVM"도 같은 JDK 21로 맞춘다.
</details>

## 완료 기준
- [ ] `phase-0-setup/workspace/ENVIRONMENT.md`에 OS, 날짜, IDE 버전, 위 표의 명령 4개 출력이 들어 있다
- [ ] 새 터미널에서 `java -version`을 실행하면 첫 줄에 `21.0.`이 보인다
- [ ] `git config --global --list` 출력에 `user.name`, `user.email`, `init.defaultbranch=main`이 보인다
- [ ] 단축키 표의 10개 기능을 마우스 없이 한 번씩 실행했다

## 생각해볼 질문
1. SDKMAN 같은 버전 관리 도구 없이 JDK를 직접 설치하면, JDK 17 프로젝트와 JDK 21 프로젝트를 오갈 때 무엇을 매번 바꿔야 하는가? (`JAVA_HOME`, `PATH`)
2. Docker로 실행하는 MySQL과 내 PC에 직접 설치한 MySQL은 팀원 5명이 같은 버전을 쓰게 만드는 방법이 어떻게 다른가? (Phase 5 예고)
