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

# 1. Investigate Fleet Partners
print("=== Fleet Partners ===")
fp = con.execute("SELECT * FROM raw_fleet_partners").df()
print(fp.to_string())

# 2. Investigate Batteries Table
print("\n=== Batteries Supplier & SOH Degradation ===")
bat = con.execute("""
SELECT supplier, pack_type, count(*) as count,
       round(avg(initial_soh_pct), 2) as avg_init_soh,
       round(avg(current_soh_pct), 2) as avg_curr_soh,
       round(avg(initial_soh_pct - current_soh_pct), 2) as avg_degradation,
       count(retired_date) as retired_count
FROM raw_batteries
GROUP BY supplier, pack_type
ORDER BY supplier, pack_type
""").df()
print(bat.to_string())

# 3. Retirement reasons
print("\n=== Battery Retirement Reasons ===")
ret = con.execute("""
SELECT supplier, retirement_reason, count(*) 
FROM raw_batteries 
WHERE retired_date IS NOT NULL 
GROUP BY supplier, retirement_reason
""").df()
print(ret.to_string())

# 4. Hourly station status vs ambient temperature and quarantined packs
print("\n=== Station Hourly Status by Month ===")
stn_hourly = con.execute("""
SELECT 
    strftime(cast(hour_start as timestamp), '%Y-%m') as year_month,
    round(avg(ambient_temp_c), 1) as avg_ambient_temp,
    round(avg(cabinet_temp_c), 1) as avg_cabinet_temp,
    round(avg(packs_charging), 2) as avg_packs_charging,
    round(avg(packs_quarantined), 2) as avg_packs_quarantined,
    round(avg(avg_charge_minutes), 1) as avg_charge_min,
    round(avg(charged_2w_avg), 2) as avg_charged_2w,
    round(avg(outage_minutes), 1) as avg_outage_min
FROM raw_station_hourly
WHERE station_id NOT LIKE 'STN-TST%'
GROUP BY year_month
ORDER BY year_month
""").df()
print(stn_hourly.to_string())

# 5. Pricing pilots (Tariff codes by city)
print("\n=== Tariff Codes by City ===")
tariff_city = con.execute("""
SELECT s.city, e.tariff_code, count(*) as count,
       round(avg(e.amount_charged_inr), 2) as avg_charged,
       round(avg(e.discount_inr), 2) as avg_discount
FROM clean_swap_events e
JOIN raw_stations s ON e.station_id = s.station_id
GROUP BY s.city, e.tariff_code
ORDER BY s.city, e.tariff_code
""").df()
print(tariff_city.to_string())

