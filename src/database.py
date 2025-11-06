import sqlite3
import os
from datetime import datetime
import click

# Path to the SQLite database file, It will be created in the project root directory
DB_PATH = os.path.join(os.getcwd(), 'queuectl.db')

def get_db_connection():
    """Returns a new connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    """Initializes the database schema (jobs and config tables)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # --- 1. Jobs Table Schema ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            state TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_retries INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            next_run_at TEXT,         -- Timestamp for exponential backoff delay
            error_message TEXT
        )
    """)
    
    # --- 2. Config Table Schema ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # --- 3. Set Default Configuration ---
    defaults = {
        'max_retries': '3', 
        'backoff_base': '2' # For delay = base ^ attempts seconds
    }
    
    for key, value in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()

# --- Placeholder CRUD Functions  ---

def get_config(key):
    """Retrieves a configuration value by key."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def get_all_configs():
    """Retrieves all configuration key-value pairs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM config")
    configs = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return configs

def set_config(key, value):
    """Inserts or updates a configuration key-value pair."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO config (key, value) 
        VALUES (?, ?)
    """, (key, value))
    conn.commit()
    conn.close()

def insert_job(job_data):
    """
    Inserts a new job into the database.
    
    :param job_data: A dictionary containing 'id', 'command', and optional 'max_retries'.
    :return: True on success, False on failure (e.g., duplicate ID).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Retrieve configuration defaults
    try:
        default_max_retries = int(get_config('max_retries'))
    except Exception:
        default_max_retries = 3

    # Prepare the data
    now = datetime.utcnow().isoformat()
    job_record = {
        "id": job_data["id"],
        "command": job_data["command"],
        "state": "pending",
        "attempts": 0,
        "max_retries": int(job_data.get("max_retries", default_max_retries)),
        "created_at": now,
        "updated_at": now,
        "next_run_at": None,
        "error_message": None
    }
    
    try:
        cursor.execute("""
            INSERT INTO jobs 
            (id, command, state, attempts, max_retries, created_at, updated_at, next_run_at, error_message) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_record["id"], job_record["command"], job_record["state"], 
            job_record["attempts"], job_record["max_retries"], job_record["created_at"], 
            job_record["updated_at"], job_record["next_run_at"], job_record["error_message"]
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Handles duplicate job ID gracefully
        click.echo(f"Error: Job ID '{job_record['id']}' already exists.", err=True)
        return False
    finally:
        conn.close()

def update_job_state(job_id, state, attempts=None, updated_at=None, next_run_at=None, error_message=None):
    """Updates a job's state and optional related fields."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Start building the SQL command
    sql_parts = ["state = ?", "updated_at = ?"]
    params = [state, updated_at or datetime.utcnow().isoformat()]

    if attempts is not None:
        sql_parts.append("attempts = ?")
        params.append(attempts)
        
    # next_run_at can be NULL, so we handle None/NULL explicitly
    if next_run_at is not None:
        sql_parts.append("next_run_at = ?")
        params.append(next_run_at)
    else: # Allows explicitly clearing next_run_at (e.g., after success or manual retry)
        sql_parts.append("next_run_at = NULL")

    if error_message is not None:
        sql_parts.append("error_message = ?")
        params.append(error_message)
    else:
        # Clear error message on state change if not provided (e.g., transition to completed)
        sql_parts.append("error_message = NULL")
    
    # Finalize SQL and parameters
    sql = f"UPDATE jobs SET {', '.join(sql_parts)} WHERE id = ?"
    params.append(job_id)

    try:
        cursor.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error during state update for {job_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
        
def get_job_status_summary():
    """Retrieves the count of jobs for every state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT state, COUNT(id) FROM jobs GROUP BY state")
    summary = {row['state']: row['COUNT(id)'] for row in cursor.fetchall()}
    conn.close()
    return summary

def get_jobs_by_state(state):
    """Retrieves a list of jobs matching a specific state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            id, command, state, attempts, max_retries, updated_at, next_run_at 
        FROM jobs 
        WHERE state = ? 
        ORDER BY updated_at DESC
    """, (state,))
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs

def retry_dlq_job(job_id):
    """Resets a 'dead' job to 'pending' state for re-processing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    # Reset attempts, next_run_at, and error_message
    cursor.execute("""
        UPDATE jobs 
        SET 
            state = 'pending', 
            attempts = 0, 
            updated_at = ?,
            next_run_at = NULL, 
            error_message = NULL
        WHERE id = ? AND state = 'dead'
    """, (now, job_id))
    
    row_count = cursor.rowcount
    conn.commit()
    conn.close()
    return row_count > 0