# Docker 배포 정리

이 디렉터리는 현재 저장소를 Docker 기준으로 배포하기 위한 최소 세트를 담고 있습니다.

## 포함 파일

- `Dockerfile`: API와 solver connector가 공통으로 쓰는 이미지
- `entrypoint.sh`: `api` 또는 `connector` 모드로 프로세스를 시작하는 진입 스크립트
- `compose.yml`: `api + solver-cbc + solver-highs + optional postgres` 구성
- `.env.example`: 배포용 환경변수 예제

## 1. 환경파일 준비

PowerShell:

```powershell
Copy-Item docker/.env.example docker/.env
```

macOS/Linux:

```bash
cp docker/.env.example docker/.env
```

`docker/.env`에서 먼저 확인할 값:

- `API_PORT`: 외부에 노출할 API 포트
- `DATABASE_URL`: 외부 DB를 쓰면 접속 문자열 입력, DB를 안 쓰면 비워둠
- `HIGHS_THREADS`, `OMP_NUM_THREADS`: HiGHS thread 수

## 2. 기본 실행

DB 없이 API + CBC + HiGHS만 올리는 경우:

```powershell
docker compose --env-file docker/.env -f docker/compose.yml up -d --build
```

확인:

```powershell
Invoke-RestMethod http://localhost:8000/healthz
```

이 구성에서는 `api`만 외부에 포트를 열고, solver container는 내부 네트워크에서만 통신합니다.

## 3. PostgreSQL까지 함께 실행

내장 PostgreSQL을 같이 띄우려면 `docker/.env`에서 아래 값을 맞춘 뒤 profile을 켭니다.

```text
DATABASE_URL=postgresql://dsopt:dsopt123@postgres:5432/ds_opt_app
POSTGRES_DB=ds_opt_app
POSTGRES_USER=dsopt
POSTGRES_PASSWORD=dsopt123
```

실행:

```powershell
docker compose --profile db --env-file docker/.env -f docker/compose.yml up -d --build
```

초기 스키마와 seed는 첫 volume 생성 시 아래 스크립트로 자동 반영됩니다.

- `scripts/create_tables.sql`
- `scripts/data_insert.sql`

이미 volume이 만들어진 뒤에는 init script가 다시 실행되지 않습니다.

## 4. 운영 명령

상태 확인:

```powershell
docker compose --env-file docker/.env -f docker/compose.yml ps
```

로그 확인:

```powershell
docker compose --env-file docker/.env -f docker/compose.yml logs -f api
docker compose --env-file docker/.env -f docker/compose.yml logs -f solver-cbc
docker compose --env-file docker/.env -f docker/compose.yml logs -f solver-highs
```

중지:

```powershell
docker compose --env-file docker/.env -f docker/compose.yml down
```

DB volume까지 제거하면서 초기화:

```powershell
docker compose --profile db --env-file docker/.env -f docker/compose.yml down -v
```

## 5. 배포 시 참고

- 외부 DB를 사용할 때는 `postgres` profile을 켜지 말고 `DATABASE_URL`만 실제 주소로 지정하면 됩니다.
- 현재 compose는 `CBC`, `HiGHS`만 내장합니다. `CPLEX`는 별도 라이선스/런타임이 필요하므로 URL 연결 방식만 남겨두었습니다.
- 이미지 내부 health check는 `/healthz` 기준입니다.
