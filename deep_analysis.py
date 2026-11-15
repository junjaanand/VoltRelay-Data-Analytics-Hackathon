import duckdb
import pandas as pd
import json

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
""")

# Build Cleaned Swap Events View:
# 1. Exclude Test Stations (station_id LIKE 'STN-TST%')
# 2. Fix Firmware v3.2.0 Timezone Bug: Add 5.5 hours to event_ts between 2025-03-10 and 2025-04-14 if station_firmware = 'v3.2.0'
# 3. Clean Odometer / SOC outliers (clamp or flag)
con.execute("""
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
WHERE station_id NOT LIKE 'STN-TST%'
""")

print("--- 1. Monthly Network Trends ---")
monthly_trend = con.execute("""
WITH monthly AS (
    SELECT 
        strftime(event_ts_clean, '%Y-%m') as year_month,
        count(*) as total_attempts,
        count(CASE WHEN event_type = 'swap_completed' THEN 1 END) as completed_swaps,
        count(CASE WHEN event_type != 'swap_completed' THEN 1 END) as failed_swaps,
        round(count(CASE WHEN event_type != 'swap_completed' THEN 1 END) * 100.0 / count(*), 2) as failure_rate_pct,
        round(count(CASE WHEN event_type = 'failed_no_charged_battery' THEN 1 END) * 100.0 / count(*), 2) as no_battery_pct,
        round(count(CASE WHEN event_type = 'abandoned_queue' THEN 1 END) * 100.0 / count(*), 2) as abandoned_queue_pct,
        round(avg(queue_wait_sec), 1) as avg_wait_sec,
        round(sum(amount_charged_inr), 2) as net_revenue_inr,
        round(sum(discount_inr), 2) as total_discount_inr,
        round(sum(energy_to_recharge_kwh), 2) as total_energy_kwh,
        round(sum(amount_charged_inr) / count(CASE WHEN event_type = 'swap_completed' THEN 1 END), 2) as rev_per_completed_swap
    FROM clean_swap_events
    GROUP BY year_month
    ORDER BY year_month
)
SELECT * FROM monthly
""").df()

print(monthly_trend.to_string())

# Save monthly trend
monthly_trend.to_csv('monthly_trend.csv', index=False)

