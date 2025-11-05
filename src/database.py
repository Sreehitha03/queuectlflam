import sqlite3
import os
from datetime import datetime
import click

# Path to the SQLite database file
# It will be created in the project root directory
DB_PATH = os.path.join(os.getcwd(), 'queuectl.db')

def get_db_connection():
    """Returns a new connection to the SQLite database."""
    # Connect to the DB file. It's created if it doesn't exist.
    conn = sqlite3.connect(DB_PATH)
    # Allows accessing columns by name (e.g., row['id'])
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
    # Default values required by the assignment
    defaults = {
        'max_retries': '3', 
        'backoff_base': '2' # For delay = base ^ attempts seconds
    }
    
    for key, value in defaults.items():
        # INSERT OR IGNORE prevents overwriting existing config values
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()

# --- Placeholder CRUD Functions (To be expanded in later steps) ---

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