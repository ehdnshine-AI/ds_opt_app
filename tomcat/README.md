# Ubuntu 22.04 Nginx + Tomcat Deployment Guide

이 디렉토리는 Ubuntu 22.04에서 아래 구조를 구성하기 위한 템플릿입니다.

- solver connector(CBC/HiGHS)는 기존 방식으로 별도 실행
- solver 호출 계층은 Python API(`app/api/main.py`) 유지
- 외부 공개는 nginx
- Tomcat은 UI/포털 또는 Java 웹앱 용도

```text
Internet
  -> nginx :80 / :443
     -> /            -> tomcat10 :8080
     -> /api/*       -> ds-opt-api :8000
     -> /healthz     -> ds-opt-api :8000
     -> /docs        -> ds-opt-api :8000
     -> /openapi.json-> ds-opt-api :8000

Internal services
  ds-opt-api          -> 127.0.0.1:8000
  ds-opt-solver-cbc   -> 127.0.0.1:8101
  ds-opt-solver-highs -> 127.0.0.1:8102
  tomcat10            -> 127.0.0.1:8080
```

## 디렉토리 구성

- `install_ubuntu22.sh`
  Ubuntu 22.04 기본 패키지/계정/디렉토리 준비
- `setup_systemd.sh`
  API caller(`ds-opt-api`) systemd 서비스 설치
- `setup_nginx_tomcat.sh`
  nginx 사이트 설정 + tomcat ROOT 예시 배치
- `systemd/ds-opt-api.service`
  API caller 서비스 템플릿
- `nginx/ds_opt_app.conf`
  nginx 라우팅 템플릿
- `env/app.env.example`
  API caller 환경변수 예시

## 설치 패키지

`install_ubuntu22.sh`에서 다음 패키지를 설치합니다.

- `nginx`
- `openjdk-17-jdk`
- `tomcat10`
- `tomcat10-admin`
- `python3`
- `python3-venv`
- `python3-pip`
- `build-essential`
- `pkg-config`
- `curl`
- `git`
- `python3-dev`
- `libpq-dev`

## 권장 디렉토리

```text
/opt/ds_opt_app/current  -> 앱 소스
/opt/ds_opt_app/venv     -> Python venv
/var/log/ds_opt_app      -> API 로그
/etc/ds_opt_app/app.env  -> API 환경변수
```

solver connector 환경변수/실행 방식은 현재 운영 방식(systemd/manual)에 맞춰 별도로 관리합니다.

## 빠른 적용 순서

1. 서버에 소스 배치
2. `sudo ./tomcat/install_ubuntu22.sh`
3. `/etc/ds_opt_app/app.env` 작성
4. `sudo ./tomcat/setup_systemd.sh`
5. `sudo ./tomcat/setup_nginx_tomcat.sh`
6. `sudo systemctl daemon-reload`
7. `sudo systemctl enable --now ds-opt-api nginx tomcat10`
8. `sudo nginx -t && sudo systemctl reload nginx`

## app.env 예시

`/etc/ds_opt_app/app.env`

```bash
CBC_SOLVER_URL=http://127.0.0.1:8101/solve
HIGHS_SOLVER_URL=http://127.0.0.1:8102/solve
CPLEX_SOLVER_URL=
SOLVER_REQUEST_TIMEOUT=30
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/dbname
PULP_LOG_DIR=/var/log/ds_opt_app
PYTHONPATH=/opt/ds_opt_app/current
```

## nginx 라우팅 정책

- `/` -> Tomcat
- `/api/`, `/docs`, `/openapi.json`, `/healthz`, `/readyz` -> FastAPI(`ds-opt-api`)
- solver connector는 외부 직접 노출하지 않음

## 운영 체크리스트

- `sudo nginx -t`
- `systemctl status tomcat10`
- `systemctl status ds-opt-api`
- `curl http://127.0.0.1:8000/healthz`
- `curl http://127.0.0.1:8101/healthz`
- `curl http://127.0.0.1:8102/healthz`
