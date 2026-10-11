// BI-Wizard CI (Pipeline as Code). 앞 단계가 실패하면 뒤 단계는 실행하지 않는다(선언형 파이프라인 기본 동작).
//
// 전제: Linux 에이전트에 Docker Engine과 Docker Compose v2(`docker compose`)가 있다.
//       (Jenkins 에이전트의 Docker 사용 가능 여부는 docs/deploy-coordination.md 6번에서 확인 중이다.)
// 단계: Checkout -> Env Validation -> Backend Lint/Test -> Frontend Lint/Test/Build -> docker compose config -> Docker Build
// 마이그레이션 왕복 테스트(tmpfs 테스트 DB)는 Jenkins 실행 환경 확인 후 별도로 결정하므로 아직 넣지 않는다(D6).
//
// Secret: 이 파이프라인은 실제 Secret을 쓰지 않는다. `.env.example`에서 만든 더미 값(.env.ci)으로 compose 설정만 검증한다.
//         운영 배포 단계가 생기면 Jenkins Credential을 .env의 변수 이름(POSTGRES_PASSWORD 등)에 매핑한다.
//
// 새 환경변수를 추가하면 .env.example -> backend Settings -> compose.yml -> scripts/ci-validate-env.sh -> README/Skill -> 테스트
// 순서로 함께 고친다(scripts/ci-validate-env.sh의 REQUIRED/SECRETS 목록이 승인된 변수 목록이다).
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        DOCKER_BUILDKIT = '1'
        COMPOSE_PROJECT_NAME = 'bi-wizard-ci'
        CI_ENV_FILE = '.env.ci'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Env Validation') {
            steps {
                // .env.example 검증(승인된 변수 목록, Secret 비어 있음, compose.yml 변수 일치) + 더미 값 .env.ci 생성
                sh 'sh scripts/ci-validate-env.sh "$CI_ENV_FILE"'
            }
        }

        stage('Backend Lint/Test') {
            steps {
                // backend/Dockerfile의 test 스테이지: ruff check, ruff format --check, pytest
                sh 'docker build --target test --tag "bi-wizard-backend-test:${BUILD_NUMBER}" backend'
            }
        }

        stage('Frontend Lint/Test/Build') {
            steps {
                // frontend/Dockerfile의 test 스테이지: eslint, tsc, vitest. 이어서 build 스테이지: vite build
                sh 'docker build --target test --tag "bi-wizard-frontend-test:${BUILD_NUMBER}" frontend'
                sh 'docker build --target build --tag "bi-wizard-frontend-build:${BUILD_NUMBER}" frontend'
            }
        }

        stage('docker compose config') {
            steps {
                sh 'docker compose --env-file "$CI_ENV_FILE" config --quiet'
                sh 'docker compose --env-file "$CI_ENV_FILE" --profile test config --quiet'
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker compose --env-file "$CI_ENV_FILE" build'
            }
        }
    }

    post {
        failure {
            echo '파이프라인이 실패했습니다. 실패한 Stage의 로그를 확인하세요. 이후 Stage는 실행되지 않았습니다.'
        }
    }
}
