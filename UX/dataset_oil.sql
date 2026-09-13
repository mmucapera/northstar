-- ============================================================
-- dataset_oilandgas Ops — Oil & Supply Chain Dashboard
-- Full schema (DDL) + seed data, PostgreSQL / Supabase compatible
-- Single-file: run top to bottom.
-- ============================================================

begin;

-- ---------- Enums ----------
do $$ begin
  create type public.range_key      as enum ('24H','7D','30D');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.shipment_status as enum ('In Transit','Loading','Delayed','Queued');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.alert_severity  as enum ('CRITICAL','ELEVATED','WATCH');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.tank_status     as enum ('Nominal','High','Diverting');
exception when duplicate_object then null; end $$;

-- ---------- Tables ----------

-- Headline KPIs, one row per time range shown in the range switcher.
create table if not exists public.kpi_snapshots (
  id                 uuid primary key default gen_random_uuid(),
  range_key          public.range_key not null unique,
  production_mbpd    numeric(6,2) not null,   -- million barrels per day
  production_delta   numeric(6,2) not null,   -- % vs previous period
  production_spark   integer[]    not null,   -- sparkline series (0-100)
  refinery_util_pct  numeric(5,2) not null,
  refinery_util_delta numeric(6,2) not null,
  inventory_days     numeric(6,2) not null,
  inventory_delta    numeric(6,2) not null,
  inventory_spark    integer[]    not null,
  brent_usd          numeric(8,2) not null,
  wti_usd            numeric(8,2) not null,
  brent_delta        numeric(6,2) not null,
  captured_at        timestamptz  not null default now()
);

-- Actual vs target production curve; 9 ordered points per range.
create table if not exists public.production_trend (
  id            uuid primary key default gen_random_uuid(),
  range_key     public.range_key not null,
  point_index   smallint     not null check (point_index >= 0),
  actual_mbpd   numeric(6,2) not null,
  target_mbpd   numeric(6,2) not null,
  unique (range_key, point_index)
);

-- Crude stored per macro-region, per range.
create table if not exists public.region_inventory (
  id          uuid primary key default gen_random_uuid(),
  range_key   public.range_key not null,
  region      text         not null,
  volume_mbbl numeric(8,2) not null,          -- million barrels
  fill_pct    smallint     not null check (fill_pct between 0 and 100),
  unique (range_key, region)
);

-- Tanker movements feeding the /shipments table.
create table if not exists public.shipments (
  id             text primary key,            -- e.g. 'S-001'
  vessel         text not null,
  origin         text not null,
  destination    text not null,
  corridor       text not null,
  load_mbbl      numeric(6,2) not null,
  eta            date not null,
  status         public.shipment_status not null,
  updated_at     timestamptz not null default now()
);
create index if not exists shipments_status_idx   on public.shipments (status);
create index if not exists shipments_eta_idx      on public.shipments (eta);
create index if not exists shipments_corridor_idx on public.shipments (corridor);

-- Disruption feed rendered in the alerts panel.
create table if not exists public.disruption_alerts (
  id          uuid primary key default gen_random_uuid(),
  severity    public.alert_severity not null,
  occurred_at timestamptz not null,
  title       text not null,
  detail      text not null
);
create index if not exists alerts_occurred_idx on public.disruption_alerts (occurred_at desc);

-- Individual storage tanks powering the /inventory page.
create table if not exists public.tanks (
  id             text primary key,            -- e.g. 'T-11'
  region         text not null,
  capacity_mbbl  numeric(6,2) not null,
  fill_pct       smallint not null check (fill_pct between 0 and 100),
  days_of_cover  numeric(6,2) not null,
  status         public.tank_status not null,
  updated_at     timestamptz not null default now()
);
create index if not exists tanks_region_idx on public.tanks (region);

-- Convenience view: regional roll-up straight from tank telemetry.
create or replace view public.region_tank_rollup as
select
  region,
  round(sum(capacity_mbbl * fill_pct / 100.0), 2) as stored_mbbl,
  round(sum(capacity_mbbl), 2)                    as capacity_mbbl,
  round(avg(fill_pct))                            as avg_fill_pct,
  round(avg(days_of_cover), 1)                    as avg_days_of_cover
from public.tanks
group by region;

-- ---------- Grants (PostgREST / Data API) ----------
grant select on public.kpi_snapshots, public.production_trend, public.region_inventory,
                public.shipments, public.disruption_alerts, public.tanks,
                public.region_tank_rollup to anon, authenticated;
grant all on public.kpi_snapshots, public.production_trend, public.region_inventory,
             public.shipments, public.disruption_alerts, public.tanks to service_role;

-- ---------- Row Level Security ----------
alter table public.kpi_snapshots     enable row level security;
alter table public.production_trend  enable row level security;
alter table public.region_inventory  enable row level security;
alter table public.shipments         enable row level security;
alter table public.disruption_alerts enable row level security;
alter table public.tanks             enable row level security;

do $$
declare t text;
begin
  foreach t in array array['kpi_snapshots','production_trend','region_inventory','shipments','disruption_alerts','tanks'] loop
    execute format('drop policy if exists "public read %1$s" on public.%1$I', t);
    execute format('create policy "public read %1$s" on public.%1$I for select to anon, authenticated using (true)', t);
  end loop;
end $$;

-- ============================================================
-- Seed data (matches src/lib/mock-data.ts exactly)
-- ============================================================


-- KPI snapshots
insert into public.kpi_snapshots (range_key, production_mbpd, production_delta, production_spark, refinery_util_pct, refinery_util_delta, inventory_days, inventory_delta, inventory_spark, brent_usd, wti_usd, brent_delta) values
  ('24H', 4.28, 2.4, '{40,55,48,62,70,66,80,92}', 86.4, 0.8, 21.7, -1.1, '{90,85,80,74,70,62,55,48}', 92.4, 88.1, 3.2),
  ('7D', 4.19, 1.2, '{44,50,58,52,64,71,76,84}', 84.9, -0.6, 22.3, 0.7, '{82,78,84,80,74,70,66,68}', 90.8, 86.9, 1.6),
  ('30D', 4.05, -0.9, '{72,66,60,58,52,56,50,46}', 83.1, -2.4, 23.9, 2.8, '{70,74,68,76,72,80,84,88}', 87.2, 83.5, -1.8)
on conflict (range_key) do nothing;

-- Production trend (actual vs target)
insert into public.production_trend (range_key, point_index, actual_mbpd, target_mbpd) values
  ('24H', 0, 3.9, 4.05),
  ('24H', 1, 4.05, 4.1),
  ('24H', 2, 4, 4.15),
  ('24H', 3, 4.2, 4.25),
  ('24H', 4, 4.15, 4.3),
  ('24H', 5, 4.35, 4.45),
  ('24H', 6, 4.3, 4.5),
  ('24H', 7, 4.5, 4.6),
  ('24H', 8, 4.45, 4.55),
  ('7D', 0, 3.75, 3.9),
  ('7D', 1, 3.95, 4),
  ('7D', 2, 3.85, 4.05),
  ('7D', 3, 4.1, 4.2),
  ('7D', 4, 4, 4.25),
  ('7D', 5, 4.25, 4.4),
  ('7D', 6, 4.15, 4.45),
  ('7D', 7, 4.4, 4.55),
  ('7D', 8, 4.3, 4.5),
  ('30D', 0, 4.3, 4.1),
  ('30D', 1, 4.15, 4.05),
  ('30D', 2, 4.2, 4),
  ('30D', 3, 4, 3.95),
  ('30D', 4, 4.05, 3.95),
  ('30D', 5, 3.9, 3.9),
  ('30D', 6, 3.95, 3.85),
  ('30D', 7, 3.8, 3.8),
  ('30D', 8, 3.85, 3.85)
on conflict (range_key, point_index) do nothing;

-- Regional inventory
insert into public.region_inventory (range_key, region, volume_mbbl, fill_pct) values
  ('24H', 'US Gulf', 3.2, 78),
  ('24H', 'North Sea', 2.1, 52),
  ('24H', 'Middle East', 4.6, 92),
  ('24H', 'Asia-Pacific', 5.8, 99),
  ('24H', 'Western Europe', 1.7, 38),
  ('7D', 'US Gulf', 3.4, 81),
  ('7D', 'North Sea', 2.3, 56),
  ('7D', 'Middle East', 4.4, 88),
  ('7D', 'Asia-Pacific', 5.5, 94),
  ('7D', 'Western Europe', 1.9, 42),
  ('30D', 'US Gulf', 3.8, 88),
  ('30D', 'North Sea', 2.6, 63),
  ('30D', 'Middle East', 4.1, 82),
  ('30D', 'Asia-Pacific', 5.1, 86),
  ('30D', 'Western Europe', 2.2, 49)
on conflict (range_key, region) do nothing;

-- Shipments (ETA year assumed 2026)
insert into public.shipments (id, vessel, origin, destination, corridor, load_mbbl, eta, status) values
  ('S-001', 'test2 Meridian', 'Ras Tanura', 'Singapore', 'ME → APAC', 2, '2026-06-14', 'In Transit'),
  ('S-002', 'Ironclad Vessel', 'Houma', 'Rotterdam', 'US → EU', 1.6, '2026-06-18', 'Loading'),
  ('S-003', 'Caspian Star', 'Bassorah', 'Fujairah', 'ME → ME', 1.2, '2026-06-11', 'Delayed'),
  ('S-004', 'Nordfjord Pioneer', 'Sullom Voe', 'Le Havre', 'NS → EU', 0.9, '2026-06-16', 'In Transit'),
  ('S-005', 'Tidewater Kestrel', 'Kuwait', 'Pusan', 'ME → APAC', 1.8, '2026-06-20', 'Loading'),
  ('S-006', 'Baltic Corridor', 'Primorsk', 'Rostock', 'RU → EU', 0.7, '2026-06-12', 'In Transit'),
  ('S-007', 'Meridian Dawn', 'Houston', 'Antwerp', 'US → EU', 1.1, '2026-06-22', 'Queued'),
  ('S-008', 'Severn Resolve', 'Kuara', 'Ningbo', 'AF → APAC', 1.4, '2026-06-25', 'In Transit'),
  ('S-009', 'Polaris Endeavor', 'Es Sider', 'Trieste', 'MED → EU', 0.6, '2026-06-13', 'Delayed'),
  ('S-010', 'Corvus Voyager', 'Santos', 'Qingdao', 'SA → APAC', 1.9, '2026-06-28', 'In Transit'),
  ('S-011', 'Halcyon Tide', 'Mina al-Ahmadi', 'Ulsan', 'ME → APAC', 1.5, '2026-06-19', 'Queued'),
  ('S-012', 'Verdant Star', 'Cabinda', 'Galveston', 'AF → US', 1, '2026-06-24', 'Loading')
on conflict (id) do nothing;

-- Disruption alerts
insert into public.disruption_alerts (severity, occurred_at, title, detail) values
  ('CRITICAL', '2026-06-10 09:42:00+00', 'Strait of Hormuz — tanker traffic reduced 34% after advisory', 'Caspian Star rerouted · +36h ETA impact'),
  ('ELEVATED', '2026-06-10 07:15:00+00', 'Sturgeon River pipeline valve 4B — flow throttled to 62%', 'Est. recovery 14:00 UTC · 180k bpd held'),
  ('WATCH', '2026-06-10 05:50:00+00', 'Gulf terminal tank farm T-11 at 91% capacity', 'Divert 400k bbl to T-14 · auto-scheduled');

-- Tanks
insert into public.tanks (id, region, capacity_mbbl, fill_pct, days_of_cover, status) values
  ('T-04', 'US Gulf', 0.8, 74, 19.2, 'Nominal'),
  ('T-11', 'US Gulf', 1.2, 91, 22.8, 'Diverting'),
  ('T-14', 'US Gulf', 1.4, 62, 16.4, 'Nominal'),
  ('N-02', 'North Sea', 0.9, 48, 14.1, 'Nominal'),
  ('N-07', 'North Sea', 1.1, 55, 15.6, 'Nominal'),
  ('M-01', 'Middle East', 2.2, 95, 28.3, 'High'),
  ('M-05', 'Middle East', 2.6, 89, 26.1, 'High'),
  ('A-03', 'Asia-Pacific', 3.1, 99, 31.7, 'High'),
  ('A-08', 'Asia-Pacific', 2.9, 97, 30.2, 'High'),
  ('E-06', 'Western Europe', 0.7, 34, 9.8, 'Nominal'),
  ('E-09', 'Western Europe', 1, 41, 11.3, 'Nominal')
on conflict (id) do nothing;

commit;
