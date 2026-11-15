import duckdb
import pandas as pd

# First let's read 100 rows with pandas to see columns and dtypes
df_sample = pd.read_csv('data/swap_events.csv', nrows=100)
print("Pandas read sample successfully! Columns:")
print(df_sample.columns.tolist())
print("\nDtypes:")
print(df_sample.dtypes)

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

con = duckdb.connect()
query = f"""
SELECT count(*) 
FROM read_csv('data/swap_events.csv', columns={columns_def}, header=true, delim=',', strict_mode=false, ignore_errors=true)
"""
cnt = con.execute(query).fetchone()[0]
print(f"\nDuckDB count with explicit columns: {cnt:,}")
