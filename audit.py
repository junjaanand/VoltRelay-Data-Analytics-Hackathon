import duckdb
import pandas as pd
import numpy as np

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

# Create views for all tables
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

print("All views created successfully!")

# Let's inspect Test Stations
print("\n--- Check Test Stations ---")
test_stns = con.execute("""
SELECT count(*), count(distinct station_id) 
FROM raw_swap_events 
WHERE station_id LIKE 'STN-TST%'
""").fetchall()
print("Test station swaps:", test_stns)

# Check Firmware v3.2.0 Timezone bug
print("\n--- Check Firmware v3.2.0 Timezone Bug ---")
fw_bug = con.execute("""
SELECT station_firmware, 
       min(event_ts), max(event_ts), count(*)
FROM raw_swap_events
WHERE station_firmware = 'v3.2.0'
  AND event_ts >= '2025-03-10' AND event_ts <= '2025-04-15'
GROUP BY station_firmware
""").fetchall()
print("Firmware bug period events:", fw_bug)

# Check City Name Variations in riders
print("\n--- Check City Names in riders ---")
cities = con.execute("""
SELECT home_city, count(*) 
FROM raw_riders 
GROUP BY home_city 
ORDER BY count(*) DESC
""").fetchall()
for c in cities:
    print(c)

# Check Offline Batch duplicates
print("\n--- Check Offline Batch Sync ---")
sync = con.execute("""
SELECT sync_mode, count(*) 
FROM raw_swap_events 
GROUP BY sync_mode
""").fetchall()
print("Sync modes:", sync)

# Check Event Types
print("\n--- Check Event Types ---")
ev_types = con.execute("""
SELECT event_type, count(*), round(count(*)*100.0/(SELECT count(*) FROM raw_swap_events), 2) as pct
FROM raw_swap_events
GROUP BY event_type
ORDER BY count(*) DESC
""").fetchall()
for et in ev_types:
    print(et)

