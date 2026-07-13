import sqlite3
import pandas as pd  # Optional: makes tables look pretty if installed

DB_FILE = "hanbreaker_history.db"


def inspect_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 1. See what tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables in Database: {tables}\n")

        # 2. Look for the Device Event Table (Namespace 2, HanBreakerDevice)
        event_table = "2_HanBreakerDevice"
        if event_table in tables:
            print(f"=== RAW EVENTS FROM '{event_table}' ===")

            # Use pandas if available for beautiful formatting
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{event_table}"', conn)
                # Keep only the important columns to fit on screen
                columns_to_show = ["_Timestamp", "_EventTypeName", "Message", "EventTypeString", "Channel",
                                   "DurationMs", "Value"]
                existing_cols = [c for c in columns_to_show if c in df.columns]
                print(df[existing_cols].tail(20).to_string(index=False))  # Show last 20 events

            except ImportError:
                # Fallback to standard python printing
                cursor.execute(
                    f'SELECT _Timestamp, _EventTypeName, Message FROM "{event_table}" ORDER BY _Id DESC LIMIT 20')
                for row in cursor.fetchall():
                    print(row)
        else:
            print(f"Error: Could not find event table '{event_table}'.")

        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")


if __name__ == "__main__":
    inspect_database()