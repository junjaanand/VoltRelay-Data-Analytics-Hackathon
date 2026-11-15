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

# 1. ZipDrop Before vs After Nov 1, 2024
print("=== 1. ZipDrop Before vs After Amendment (2024-11-01) ===")
zd = con.execute("""
SELECT 
    CASE WHEN event_ts_clean < '2024-11-01' THEN 'Before_Amendment' ELSE 'After_Amendment' END as period,
    count(*) as total_attempts,
    count(CASE WHEN event_type = 'swap_completed' THEN 1 END) as completed_swaps,
    round(avg(list_price_inr), 2) as avg_list_price,
    round(avg(discount_inr), 2) as avg_discount,
    round(avg(amount_charged_inr), 2) as avg_amount_charged,
    round(avg(discount_inr) * 100.0 / avg(list_price_inr), 2) as effective_discount_pct,
    round(avg(amount_charged_inr - energy_to_recharge_kwh * 9.2), 2) as margin_per_swap
FROM clean_swap_events e
JOIN raw_riders r ON e.rider_id = r.rider_id
WHERE r.partner_id = 'FP-03'
GROUP BY period
""").df()
print(zd.to_string())

# 2. Support Tickets Analysis
print("\n=== 2. Support Tickets Breakdown ===")
tickets = con.execute("""
SELECT category, count(*) as count,
       round(count(*) * 100.0 / (SELECT count(*) FROM raw_support_tickets), 2) as pct,
       round(avg(csat_score), 2) as avg_csat,
       round(avg(resolution_hours), 1) as avg_res_hours
FROM raw_support_tickets
GROUP BY category
ORDER BY count DESC
""").df()
print(tickets.to_string())

# Sample rider comments in support tickets
print("\n=== Sample Support Ticket Comments ===")
sample_comments = con.execute("""
SELECT category, rider_comment 
FROM raw_support_tickets 
WHERE rider_comment IS NOT NULL
LIMIT 15
""").df()
for idx, row in sample_comments.iterrows():
    print(f"[{row['category']}] {row['rider_comment']}")

# 3. Churn by Signup Cohort
print("\n=== 3. Rider Signup Cohort Churn ===")
cohort = con.execute("""
WITH rider_activity AS (
    SELECT 
        r.rider_id,
        strftime(cast(r.signup_date as timestamp), '%Y-%m') as signup_cohort,
        r.vehicle_class,
        COALESCE(r.partner_id, 'RETAIL') as partner_type,
        count(e.event_id) as total_swaps,
        min(e.event_ts_clean) as first_swap,
        max(e.event_ts_clean) as last_swap,
        -- Days active
        datediff('day', cast(min(r.signup_date) as timestamp), max(e.event_ts_clean)) as active_days
    FROM raw_riders r
    LEFT JOIN clean_swap_events e ON r.rider_id = e.rider_id
    GROUP BY r.rider_id, signup_cohort, r.vehicle_class, partner_type, r.signup_date
)
SELECT 
    signup_cohort,
    count(*) as cohort_size,
    round(avg(total_swaps), 1) as avg_swaps,
    count(CASE WHEN active_days <= 30 THEN 1 END) as churned_day30,
    round(count(CASE WHEN active_days <= 30 THEN 1 END) * 100.0 / count(*), 2) as churn_rate_30d_pct,
    count(CASE WHEN last_swap < '2025-05-01' THEN 1 END) as inactive_by_may,
    round(count(CASE WHEN last_swap < '2025-05-01' THEN 1 END) * 100.0 / count(*), 2) as inactive_pct
FROM rider_activity
GROUP BY signup_cohort
ORDER BY signup_cohort
""").df()
print(cohort.to_string())

