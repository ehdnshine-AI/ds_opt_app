-- ============================================
-- 1) 시나리오 기본정보
-- ============================================
create table if not exists public.optimization_scenario (
    scenario_id bigserial primary key,
    scenario_code varchar(100) not null unique,
    scenario_name varchar(200) not null,
    description text,
    problem_type varchar(50) not null default 'MILP',
    solver_name varchar(50) not null default 'HiGHS',
    is_active boolean not null default true,
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp
);

comment on table public.optimization_scenario is '최적화 시나리오 기본정보';
comment on column public.optimization_scenario.scenario_id is '시나리오 PK';
comment on column public.optimization_scenario.scenario_code is '시나리오 코드';
comment on column public.optimization_scenario.scenario_name is '시나리오명';
comment on column public.optimization_scenario.description is '설명';
comment on column public.optimization_scenario.problem_type is '문제 유형 (LP/MILP 등)';
comment on column public.optimization_scenario.solver_name is '사용 solver';
comment on column public.optimization_scenario.is_active is '사용 여부';


-- ============================================
-- 2) Solver payload 저장
-- ============================================
create table if not exists public.optimization_payload (
    payload_id bigserial primary key,
    scenario_id bigint not null,
    payload_version integer not null default 1,
    sense varchar(10) not null,
    solver varchar(50) not null,
    problem_type varchar(50) not null,
    time_limit_sec integer,
    payload_json jsonb not null,
    objective_count integer not null,
    constraint_count integer not null,
    variable_count integer not null,
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp,
    constraint fk_optimization_payload_scenario
        foreign key (scenario_id)
        references public.optimization_scenario (scenario_id)
        on delete cascade,
    constraint uq_optimization_payload_scenario_version
        unique (scenario_id, payload_version)
);

comment on table public.optimization_payload is '최적화 solver payload 저장';
comment on column public.optimization_payload.payload_id is 'payload PK';
comment on column public.optimization_payload.scenario_id is '시나리오 FK';
comment on column public.optimization_payload.payload_version is 'payload 버전';
comment on column public.optimization_payload.sense is '목적함수 방향(max/min)';
comment on column public.optimization_payload.solver is 'solver 이름';
comment on column public.optimization_payload.problem_type is '문제유형';
comment on column public.optimization_payload.time_limit_sec is '시간제한';
comment on column public.optimization_payload.payload_json is '전체 payload JSONB';
comment on column public.optimization_payload.objective_count is 'objective 길이';
comment on column public.optimization_payload.constraint_count is '제약식 수';
comment on column public.optimization_payload.variable_count is '변수 수';


-- ============================================
-- 3) 변수 인덱스 맵
-- ============================================
create table if not exists public.optimization_var_index_map (
    map_id bigserial primary key,
    scenario_id bigint not null,
    payload_version integer not null default 1,
    var_index integer not null,
    var_group varchar(50) not null,
    key_json jsonb not null,
    var_name_text varchar(300) not null,
    created_at timestamp not null default current_timestamp,
    constraint fk_var_map_scenario
        foreign key (scenario_id)
        references public.optimization_scenario (scenario_id)
        on delete cascade,
    constraint uq_var_map_unique
        unique (scenario_id, payload_version, var_index)
);

comment on table public.optimization_var_index_map is '최적화 변수 인덱스 맵';
comment on column public.optimization_var_index_map.var_index is 'solution 배열 인덱스';
comment on column public.optimization_var_index_map.var_group is '변수 그룹(x, y, ship, inv, bo, regUsed, otUsed)';
comment on column public.optimization_var_index_map.key_json is '변수 키 JSON';
comment on column public.optimization_var_index_map.var_name_text is '가독성용 변수명 문자열';


-- ============================================
-- 4) 인덱스
-- ============================================
create index if not exists idx_optimization_payload_scenario_id
    on public.optimization_payload (scenario_id);

create index if not exists idx_optimization_payload_payload_json_gin
    on public.optimization_payload
    using gin (payload_json);

create index if not exists idx_optimization_var_index_map_scenario_version
    on public.optimization_var_index_map (scenario_id, payload_version);

create index if not exists idx_optimization_var_index_map_group
    on public.optimization_var_index_map (var_group);


-- ============================================
-- 5) updated_at 자동 갱신 함수
-- ============================================
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = current_timestamp;
    return new;
end;
$$;

drop trigger if exists trg_optimization_scenario_updated_at on public.optimization_scenario;
create trigger trg_optimization_scenario_updated_at
before update on public.optimization_scenario
for each row
execute function public.set_updated_at();

drop trigger if exists trg_optimization_payload_updated_at on public.optimization_payload;
create trigger trg_optimization_payload_updated_at
before update on public.optimization_payload
for each row
execute function public.set_updated_at();