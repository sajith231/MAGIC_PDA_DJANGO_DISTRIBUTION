"""
SQL Helper - Database connection management for SyncService
Uses ODBC (pyodbc) to connect to SAP SQL Anywhere via DSN

NOTE:
- _get_config() is kept ONLY for backward compatibility
- Real DB values come from environment variables
"""

import os
import pyodbc


# ------------------------------------------------------------------
# BACKWARD-COMPATIBILITY (DO NOT REMOVE)
# Some existing code imports _get_config
# ------------------------------------------------------------------
def _get_config():
    """
    Compatibility function.
    Values are NOT used anymore.
    """
    return {
        "dsn": os.getenv("DB_DSN"),
        "db_uid": os.getenv("DB_UID"),
        "db_pwd": os.getenv("DB_PWD"),
    }


# ------------------------------------------------------------------
# REAL CONNECTION LOGIC
# ------------------------------------------------------------------
def get_connection():
    """
    Create and return a database connection using ODBC DSN.
    Environment variables MUST be set by SyncService.py
    """

    dsn = os.getenv("DB_DSN")
    uid = os.getenv("DB_UID")
    pwd = os.getenv("DB_PWD")

    if not dsn:
        raise RuntimeError("DB_DSN not set")
    if not uid:
        raise RuntimeError("DB_UID not set")
    if not pwd:
        raise RuntimeError("DB_PWD not set")

    try:
        conn_str = f"DSN={dsn};UID={uid};PWD={pwd}"
        return pyodbc.connect(conn_str, autocommit=True)
    except Exception as e:
        print("❌ Database connection failed")
        print(f"   DSN={dsn}, UID={uid}")
        raise


def test_connection():
    """Test database connectivity"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print("❌ Database connection test failed:", e)
        return False


if __name__ == "__main__":
    test_connection()
