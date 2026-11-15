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
""")

# Check offline_batch duplicates
print("--- Check Offline Batch Duplicates ---")
dup_check = con.execute("""
SELECT count(*) as total_offline,
       count(distinct (rider_id, station_id, event_ts)) as unique_offline_triplets
FROM raw_swap_events
WHERE sync_mode = 'offline_batch'
""").fetchall()
print("Offline batch duplicates count:", dup_check)

# Let's check pairs of events within 60 seconds for same rider & station
near_dups = con.execute("""
WITH ranked AS (
    SELECT event_id, rider_id, station_id, event_ts, event_type, sync_mode,
           LAG(event_ts) OVER (PARTITION BY rider_id, station_id ORDER BY event_ts) as prev_ts,
           LAG(event_id) OVER (PARTITION BY rider_id, station_id ORDER BY event_ts) as prev_id
    FROM raw_swap_events
    WHERE sync_mode = 'offline_batch'
)
SELECT count(*) 
FROM ranked 
WHERE prev_ts IS NOT NULL 
  AND epoch(cast(event_ts as timestamp)) - epoch(cast(prev_ts as timestamp)) <= 60
""").fetchone()[0]
print("Offline batch swaps within 60s for same rider & station:", near_dups)

# Check Odometer and SOC Outliers
print("\n--- Outlier Checks ---")
outliers = con.execute("""
SELECT 
    count(CASE WHEN km_since_last_swap < 0 THEN 1 END) as neg_km,
    count(CASE WHEN km_since_last_swap > 500 THEN 1 END) as extreme_km,
    count(CASE WHEN soc_in_pct > 100 THEN 1 END) as soc_in_over_100,
    count(CASE WHEN soc_out_pct > 100 THEN 1 END) as soc_out_over_100,
    count(CASE WHEN soh_in_pct > 100 THEN 1 END) as soh_in_over_100,
    count(CASE WHEN soh_out_pct > 100 THEN 1 END) as soh_out_over_100,
    count(CASE WHEN queue_wait_sec < 0 THEN 1 END) as neg_wait
FROM raw_swap_events
""").fetchall()
print("Outliers:", outliers)

# Check Stations Table
print("\n--- Stations Summary ---")
stn_summary = con.execute("""
SELECT city, expansion_wave, charger_generation, count(*) as n_stations,
       sum(slots_2w) as slots_2w, sum(slots_3w) as slots_3w,
       avg(monthly_rent_inr) as avg_rent, avg(grid_tariff_inr_kwh) as avg_tariff
FROM raw_stations
GROUP BY city, expansion_wave, charger_generation
ORDER BY city, expansion_wave
""").df()
print(stn_summary.to_string())

