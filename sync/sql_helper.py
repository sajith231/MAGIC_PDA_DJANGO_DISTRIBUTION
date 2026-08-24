"""
SQL Helper - Database connection management for SyncService
Uses ODBC (pyodbc) to connect to SAP SQL Anywhere via DSN

Supports two modes:
  METHOD 1 (default) - Connect directly via DSN from config.json
  METHOD 2           - Read dba.sounds from first DB, connect to second DB
"""

import os
import sys
import time
import subprocess
import logging
import pyodbc

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# BACKWARD-COMPATIBILITY (DO NOT REMOVE)
# ------------------------------------------------------------------
def _get_config():
    return {
        "dsn": os.getenv("DB_DSN"),
        "db_uid": os.getenv("DB_UID"),
        "db_pwd": os.getenv("DB_PWD"),
    }


# ------------------------------------------------------------------
# MODULE-LEVEL STATE FOR METHOD 2 (second database)
# ------------------------------------------------------------------
_second_db_config = None   # dict: {connector: SecondDatabaseConnector} or None


def set_second_db(connector):
    """Set the second database connector for METHOD 2."""
    global _second_db_config
    _second_db_config = {"connector": connector}
    logger.info("Second database connector set — all get_connection() calls will use DB2")


def clear_second_db():
    """Clear the second database connector (revert to METHOD 1)."""
    global _second_db_config
    if _second_db_config and _second_db_config.get("connector"):
        try:
            _second_db_config["connector"].close()
        except Exception:
            pass
    _second_db_config = None
    logger.info("Second database connector cleared — reverting to DSN mode")


# ------------------------------------------------------------------
# PRIMARY CONNECTION LOGIC (METHOD 1 — DSN-based)
# ------------------------------------------------------------------
def get_connection():
    """
    Create and return a database connection.
    If METHOD 2 is active, returns connection to the second database.
    Otherwise, uses the DSN from environment variables.
    """
    if _second_db_config is not None:
        connector = _second_db_config["connector"]
        return connector.get_connection()

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


def release_connection(conn):
    """
    Release a connection obtained from get_connection().

    METHOD 2 (second database): get_connection() hands out the SINGLE
    shared SecondDatabaseConnector connection. Closing it here would
    break any other request still using it ("The cursor's connection
    was closed."). The connector owns its lifecycle — it health-checks
    with SELECT 1 and reconnects automatically when needed.

    METHOD 1 (DSN): each call creates a fresh per-request connection,
    so closing it is safe and expected.
    """
    if _second_db_config is not None:
        return
    try:
        conn.close()
    except Exception:
        pass


def get_primary_connection():
    """
    Always returns a connection to the PRIMARY database (DSN-based),
    regardless of METHOD 2. Used for login/authentication where user
    accounts (acc_users) live in the first DB.
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
        print("❌ Primary database connection failed")
        print(f"   DSN={dsn}, UID={uid}")
        raise


# ------------------------------------------------------------------
# SECOND DATABASE DISCOVERY — read dba.sounds from first DB
# ------------------------------------------------------------------
def fetch_second_db_info(connection):
    """
    Read the dba.sounds table from the FIRST database.
    Returns (pf, df) where:
      pf = database name of the second DB
      df = file path (.db) of the second DB
    """
    cur = connection.cursor()
    cur.execute("SELECT pf, df FROM dba.sounds")
    row = cur.fetchone()
    cur.close()

    if not row:
        raise RuntimeError("dba.sounds table is empty — cannot discover second database")

    pf = (row[0] or "").strip()
    df = (row[1] or "").strip()

    if not pf or not df:
        raise RuntimeError(
            f"dba.sounds has incomplete data — pf='{pf}', df='{df}'"
        )

    logger.info("Second DB discovered — pf=%s, df=%s", pf, df)
    return pf, df


# ------------------------------------------------------------------
# SECOND DATABASE CONNECTOR — multi-driver / multi-template fallback
# ------------------------------------------------------------------
class SecondDatabaseConnector:
    """
    Connects to a SQL Anywhere database by file path (.db) with
    multi-driver and multi-template fallback, plus manual engine launch.
    """

    DB_USER = "DBA"
    DB_PWD = "MMIRANN"

    DRIVER_PRIORITY = [
        "SQL Anywhere 17",
        "SQL Anywhere 16",
        "SQL Anywhere 12",
        "SQL Anywhere 9",
    ]

    ENGINE_EXES = [
        ("dbeng17.exe", "dbeng17"),
        ("dbeng16.exe", "dbeng16"),
        ("dbeng12.exe", "dbeng12"),
        ("dbeng9.exe",  "dbeng9"),
    ]

    def __init__(self, db_name, db_file_path):
        """
        db_name      = pf value from dba.sounds (database name)
        db_file_path = df value from dba.sounds (full path to .db file)
        """
        self.db_name = db_name
        self.db_file_path = db_file_path
        self._connection = None
        self._engine_process = None

    def _find_installed_drivers(self):
        """Return list of installed SQL Anywhere ODBC drivers in priority order."""
        all_drivers = pyodbc.drivers()
        found = []
        for name in self.DRIVER_PRIORITY:
            if name in all_drivers:
                found.append(name)
        if not found:
            # fallback: any driver containing "SQL Anywhere"
            for d in all_drivers:
                if "SQL Anywhere" in d:
                    found.append(d)
                    break
        return found

    def _build_templates(self, driver):
        """Build connection string templates for a given driver."""
        uid = self.DB_USER
        pwd = self.DB_PWD
        df = self.db_file_path
        pf = self.db_name

        templates = [
            # File-based: DBF only (direct local connection)
            f"DRIVER={{{driver}}};DBF={df};UID={uid};PWD={pwd}",
            # File-based with DBN
            f"DRIVER={{{driver}}};DBF={df};DBN={pf};UID={uid};PWD={pwd}",
            # File-based with ENG (embedded engine)
            f"DRIVER={{{driver}}};DBF={df};UID={uid};PWD={pwd};ENG=dbeng17",
            f"DRIVER={{{driver}}};DBF={df};UID={uid};PWD={pwd};ENG=dbeng16",
            # DBN on localhost via TCP (named database server)
            f"DRIVER={{{driver}}};DBN={pf};UID={uid};PWD={pwd};HOST=localhost;PORT=2638",
            # DBN on localhost (minimal)
            f"DRIVER={{{driver}}};DBN={pf};UID={uid};PWD={pwd};HOST=localhost",
        ]
        return templates

    def _try_connect(self, conn_str):
        """Attempt a single connection. Returns connection or None."""
        try:
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
            # verify it works
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            return conn
        except Exception:
            return None

    def _try_manual_engine_launch(self):
        """Launch dbeng process manually, then retry connection."""
        df = self.db_file_path

        for exe_name, engine_name in self.ENGINE_EXES:
            # find the engine executable
            engine_path = self._find_engine_exe(exe_name)
            if not engine_path:
                continue

            logger.info("Launching %s for %s", engine_path, df)
            try:
                proc = subprocess.Popen(
                    [engine_path, df],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._engine_process = proc
                time.sleep(3)  # wait for engine to start

                # try connecting with the engine name
                uid = self.DB_USER
                pwd = self.DB_PWD
                pf = self.db_name
                conn_str = (
                    f"DBF={df};DBN={pf};UID={uid};PWD={pwd};"
                    f"ENG={engine_name}"
                )
                conn = self._try_connect(conn_str)
                if conn:
                    logger.info("Connected via manual engine launch: %s", engine_name)
                    return conn

                # try without ENG
                conn_str = f"DBF={df};DBN={pf};UID={uid};PWD={pwd}"
                conn = self._try_connect(conn_str)
                if conn:
                    logger.info("Connected via manual engine (no ENG): %s", engine_name)
                    return conn

            except Exception as e:
                logger.warning("Manual launch failed for %s: %s", engine_name, e)
                if self._engine_process:
                    try:
                        self._engine_process.kill()
                    except Exception:
                        pass
                    self._engine_process = None

        return None

    def _find_engine_exe(self, exe_name):
        """Search common paths for the DB engine executable."""
        import glob as globmod

        search_paths = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "SQL Anywhere", "**"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "SQL Anywhere", "**"),
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "SQL Anywhere", "**"),
        ]

        for pattern in search_paths:
            matches = globmod.glob(os.path.join(pattern, exe_name), recursive=True)
            if matches:
                return matches[0]

        # try PATH
        for dir_path in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(dir_path.strip(), exe_name)
            if os.path.isfile(candidate):
                return candidate

        return None

    def connect(self):
        """
        Attempt to connect to the second database.
        Tries multi-driver, multi-template, then manual engine launch.
        Returns a pyodbc connection.
        Raises RuntimeError if all attempts fail.
        """
        if self._connection:
            try:
                cur = self._connection.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                return self._connection
            except Exception:
                self._connection = None

        drivers = self._find_installed_drivers()
        if not drivers:
            raise RuntimeError(
                "No SQL Anywhere ODBC drivers found on this system"
            )

        errors = []

        for driver in drivers:
            templates = self._build_templates(driver)
            for i, conn_str in enumerate(templates):
                try:
                    conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
                    # verify connection
                    cur = conn.cursor()
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    cur.close()
                    self._connection = conn
                    logger.info(
                        "Connected to second DB via driver=%s template=%d",
                        driver, i + 1
                    )
                    return conn
                except Exception as e:
                    errors.append(f"{driver} template#{i+1}: {e}")
                    continue

        # last resort: manual engine launch
        logger.info("All templates failed — trying manual engine launch")
        conn = self._try_manual_engine_launch()
        if conn:
            self._connection = conn
            return conn

        error_summary = "\n".join(errors[-5:])  # last 5 errors
        raise RuntimeError(
            f"Cannot connect to second database '{self.db_name}' "
            f"at '{self.db_file_path}'.\n"
            f"Tried {len(drivers)} drivers, 6 templates each, and manual engine launch.\n"
            f"Last errors:\n{error_summary}"
        )

    def get_connection(self):
        """Return an active connection, reconnecting if necessary."""
        if self._connection:
            try:
                cur = self._connection.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                return self._connection
            except Exception:
                self._connection = None

        return self.connect()

    def close(self):
        """Close the connection and kill engine process if launched."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

        if self._engine_process:
            try:
                self._engine_process.kill()
            except Exception:
                pass
            self._engine_process = None


# ------------------------------------------------------------------
# TEST
# ------------------------------------------------------------------
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
