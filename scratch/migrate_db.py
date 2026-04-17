import sqlite3
import os

DB_PATH = "leadstation_v2.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Checking for missing column: phone_number...")
        cursor.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
        conn.commit()
        print("Successfully added phone_number column to users table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column phone_number already exists.")
        else:
            print(f"OperationalError: {e}")
    except Exception as e:
        print(f"Migration Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
