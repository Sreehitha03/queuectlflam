import sqlite3
import time
from datetime import datetime, timedelta
from .database import get_db_connection, update_job_state, get_config

def acquire_job_atomically():
    """
    Selects the oldest pending job and atomically marks it as processing.
    This prevents multiple workers from processing the same job.
    """
    conn = get_db_connection()
    # Use EXCLUSIVE mode to prevent race conditions during the SELECT/UPDATE cycle
    conn.isolation_level = 'EXCLUSIVE' 
    cursor = conn.cursor()
    job = None
    
    try:
        now = datetime.utcnow().isoformat()
        
        # 1. Select the oldest pending job whose next_run_at is due (or NULL)
        cursor.execute("""
            SELECT id, command, attempts, max_retries 
            FROM jobs 
            WHERE state = 'pending' 
            AND (next_run_at IS NULL OR next_run_at <= ?)
            ORDER BY created_at ASC 
            LIMIT 1
        """, (now,))
        
        job_row = cursor.fetchone()
        
        if job_row:
            job = dict(job_row)
            
            # 2. ATOMICALLY transition the state to processing
            update_time = datetime.utcnow().isoformat()
            
            cursor.execute("""
                UPDATE jobs 
                SET state = 'processing', updated_at = ?
                WHERE id = ? AND state = 'pending'
            """, (update_time, job['id']))
            
            # The transaction succeeds if exactly one row was updated
            if cursor.rowcount == 1:
                conn.commit()
                return job
            else:
                # Race condition lost (another worker was faster or job state changed)
                conn.rollback()
                return None
        else:
            return None # No pending jobs
            
    except sqlite3.Error as e:
        # Log error and rollback on failure
        print(f"Database error during job acquisition: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()
