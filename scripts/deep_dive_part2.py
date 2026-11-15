import duckdb
import pandas as pd

con = duckdb.connect()

columns_def = {
    'event_id': 'VARCHAR',
    'rider_id': 'VARCHAR',
    'station_id': 'VARCHAR',
    'event_ts': 'VARCHAR',
    'event_type': 'VARCHAR',
    'attempt_seq': 'BIGINT',
    'queue_wait_sec': 'BIGINT',
    'battery_in_id': 'VARCHAR',
    'battery_out_id': 'VARCHAR',
    'soc_in_pct': 'DOUBLE',
    'soh_in_pct': 'DOUBLE',
    'soc_out_pct': 'DOUBLE',
    'soh_out_pct': 'DOUBLE',
    'km_since_last_swap': 'DOUBLE',
    'tariff_code': 'VARCHAR',
    'list_price_inr': 'DOUBLE',
    'discount_inr': 'DOUBLE',
    'amount_charged_inr': 'DOUBLE',
    'payment_mode': 'VARCHAR',
    'energy_to_recharge_kwh': 'DOUBLE',
    'station_firmware': 'VARCHAR',
    'sync_mode': 'VARCHAR'
}

con.execute(f"""
CREATE OR REPLACE VIEW raw_swap_events AS 
SELECT * FROM read_csv('data/swap_events.csv', columns={columns_def}, header=true, delim=',', strict_mode=false, ignore_errors=true);

CREATE OR REPLACE VIEW raw_stations AS SELECT * FROM read_csv_auto('data/stations.csv');
CREATE OR REPLACE VIEW raw_riders AS SELECT * FROM read_csv_auto('data/riders.csv');
CREATE OR REPLACE VIEW raw_batteries AS SELECT * FROM read_csv_auto('data/batteries.csv');
CREATE OR REPLACE VIEW raw_fleet_partners AS SELECT * FROM read_csv_auto('data/fleet_partners.csv');
CREATE OR REPLACE VIEW raw_station_hourly AS SELECT * FROM read_csv_auto('data/station_hourly_status.csv');
CREATE OR REPLACE VIEW raw_support_tickets AS SELECT * FROM read_csv_auto('data/support_tickets.csv');
CREATE OR REPLACE VIEW raw_city_daily AS SELECT * FROM read_csv_auto('data/city_daily_context.csv');

CREATE OR REPLACE VIEW clean_swap_events AS
SELECT 
    event_id,
    rider_id,
    station_id,
    CASE 
        WHEN station_firmware = 'v3.2.0' AND event_ts >= '2025-03-10' AND event_ts <= '2025-04-15'
        THEN cast(event_ts as timestamp) + INTERVAL '5 hours 30 minutes'
        ELSE cast(event_ts as timestamp)
    END as event_ts_clean,
    event_type,
    attempt_seq,
    queue_wait_sec,
    battery_in_id,
    battery_out_id,
    soc_in_pct,
    soh_in_pct,
    soc_out_pct,
    soh_out_pct,
    CASE WHEN km_since_last_swap < 0 THEN NULL ELSE km_since_last_swap END as km_since_last_swap_clean,
    tariff_code,
    list_price_inr,
    discount_inr,
    amount_charged_inr,
    payment_mode,
    energy_to_recharge_kwh,
    station_firmware,
    sync_mode
FROM raw_swap_events
WHERE station_id NOT LIKE 'STN-TST%';
""")

# 1. Expansion Wave Performance Analysis
print("=== 1. Expansion Wave Performance ===")
wave_perf = con.execute("""
SELECT 
    s.expansion_wave,
    s.charger_generation,
    count(distinct s.station_id) as n_stations,
    count(e.event_id) as total_events,
    round(count(e.event_id) * 1.0 / count(distinct s.station_id), 0) as events_per_station,
    round(count(CASE WHEN e.event_type != 'swap_completed' THEN 1 END) * 100.0 / count(e.event_id), 2) as failure_rate_pct,
    round(count(CASE WHEN e.event_type = 'failed_no_charged_battery' THEN 1 END) * 100.0 / count(e.event_id), 2) as no_battery_pct,
    round(avg(e.queue_wait_sec), 1) as avg_wait_sec,
    round(sum(e.amount_charged_inr) / 1000000.0, 2) as total_rev_m_inr
FROM raw_stations s
LEFT JOIN clean_swap_events e ON s.station_id = e.station_id
WHERE s.station_id NOT LIKE 'STN-TST%'
GROUP BY s.expansion_wave, s.charger_generation
ORDER BY s.expansion_wave, s.charger_generation
""").df()
print(wave_perf.to_string())

# 2. Fleet Partner Economics & Profitability
print("\n=== 2. Fleet Partner Economics ===")
partner_econ = con.execute("""
WITH partner_swaps AS (
    SELECT 
        COALESCE(r.partner_id, 'RETAIL_INDEPENDENT') as partner_id,
        count(e.event_id) as total_attempts,
        count(CASE WHEN e.event_type = 'swap_completed' THEN 1 END) as completed_swaps,
        round(count(CASE WHEN e.event_type != 'swap_completed' THEN 1 END) * 100.0 / count(e.event_id), 2) as failure_rate_pct,
        round(sum(e.amount_charged_inr), 2) as total_revenue,
        round(sum(e.discount_inr), 2) as total_discount,
        round(sum(e.energy_to_recharge_kwh), 2) as total_energy_kwh,
        -- Energy cost estimate using average grid tariff ~ 9.2 INR/kWh
        round(sum(e.energy_to_recharge_kwh * COALESCE(st.grid_tariff_inr_kwh, 9.2)), 2) as total_energy_cost,
        round(avg(e.amount_charged_inr), 2) as avg_rev_per_swap
    FROM clean_swap_events e
    JOIN raw_riders r ON e.rider_id = r.rider_id
    LEFT JOIN raw_stations st ON e.station_id = st.station_id
    GROUP BY COALESCE(r.partner_id, 'RETAIL_INDEPENDENT')
)
SELECT 
    ps.partner_id,
    COALESCE(fp.partner_name, 'Independent Riders') as partner_name,
    COALESCE(fp.partner_segment, 'Retail') as segment,
    ps.total_attempts,
    ps.completed_swaps,
    ps.failure_rate_pct,
    round(ps.total_revenue / 1000000.0, 2) as rev_m_inr,
    round(ps.total_discount / 1000000.0, 2) as disc_m_inr,
    round(ps.total_energy_cost / 1000000.0, 2) as energy_cost_m_inr,
    round((ps.total_revenue - ps.total_energy_cost) / 1000000.0, 2) as gross_margin_m_inr,
    round((ps.total_revenue - ps.total_energy_cost) / ps.completed_swaps, 2) as margin_per_completed_swap,
    round((ps.total_revenue - ps.total_energy_cost) * 100.0 / ps.total_revenue, 2) as gross_margin_pct
FROM partner_swaps ps
LEFT JOIN raw_fleet_partners fp ON ps.partner_id = fp.partner_id
ORDER BY ps.total_attempts DESC
""").df()
print(partner_econ.to_string())

# 3. Rider Churn / Retention Analysis
print("\n=== 3. Rider Churn vs Early Failure Experience ===")
churn_analysis = con.execute("""
WITH rider_first_swaps AS (
    SELECT 
        rider_id,
        min(event_ts_clean) as first_swap_ts,
        max(event_ts_clean) as last_swap_ts,
        count(*) as lifetime_attempts,
        count(CASE WHEN event_type = 'swap_completed' THEN 1 END) as lifetime_completed,
        -- Did rider experience a failure in their first 3 attempts?
        max(CASE WHEN attempt_seq_in_rider <= 3 AND event_type != 'swap_completed' THEN 1 ELSE 0 END) as failed_in_first_3
    FROM (
        SELECT 
            rider_id,
            event_ts_clean,
            event_type,
            row_number() OVER (PARTITION BY rider_id ORDER BY event_ts_clean) as attempt_seq_in_rider
        FROM clean_swap_events
    )
    GROUP BY rider_id
)
SELECT 
    failed_in_first_3,
    count(*) as n_riders,
    round(avg(lifetime_attempts), 1) as avg_lifetime_attempts,
    round(avg(lifetime_completed), 1) as avg_lifetime_completed,
    count(CASE WHEN lifetime_attempts <= 3 THEN 1 END) as churned_immediately,
    round(count(CASE WHEN lifetime_attempts <= 3 THEN 1 END) * 100.0 / count(*), 2) as immediate_churn_rate_pct,
    count(CASE WHEN last_swap_ts < '2025-05-01' THEN 1 END) as churned_before_last_2m,
    round(count(CASE WHEN last_swap_ts < '2025-05-01' THEN 1 END) * 100.0 / count(*), 2) as churned_by_may_pct
FROM rider_first_swaps
GROUP BY failed_in_first_3
""").df()
print(churn_analysis.to_string())

