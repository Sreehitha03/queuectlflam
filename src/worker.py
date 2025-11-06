import sqlite3
import time
import subprocess
from datetime import datetime, timedelta

from .database import get_db_connection, update_job_state, get_config

def acquire_job_atomically():
    """
    Selects the oldest pending job and atomically marks it as processing.
    This prevents multiple workers from processing the same job.
    """
    conn = get_db_connection()
    # Using EXCLUSIVE mode to prevent race conditions during the SELECT/UPDATE cycle
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


def run_worker(worker_id, stop_event):
    """
    The main loop for a single worker process.
    :param worker_id: Unique ID for logging.
    :param stop_event: A multiprocessing.Event to signal graceful shutdown.
    """
    print(f"[{worker_id}] Worker started. Looking for jobs...")

    while not stop_event.is_set():
        job = acquire_job_atomically()

        if job:
            job_id = job['id']
            command = job['command']
            attempts = job['attempts'] + 1  
            max_retries = job['max_retries']
            
            print(f"[{worker_id}] Processing Job {job_id} (Attempt {attempts}/{max_retries}) - Command: {command}")

            try:
                result = subprocess.run(command, shell=True, check=False, 
                                        capture_output=True, text=True, timeout=30) 
                
                exit_code = result.returncode

                if exit_code == 0:
                    # --- SUCCESS ---
                    update_job_state(job_id, 'completed')
                    print(f"[{worker_id}] ✅ Job {job_id} completed successfully.")
                else:
                    # --- FAILURE: Determine Retry or DLQ ---
                    error_msg = f"Command failed with exit code {exit_code}. Output: {result.stderr.strip()}"
                    
                    if attempts > max_retries:
                        # Move to Dead Letter Queue (DLQ)
                        update_job_state(job_id, 'dead', attempts=attempts, error_message=error_msg)
                        print(f"[{worker_id}] ❌ Job {job_id} failed permanently and moved to DLQ.")
                    else:
                        # Calculate Exponential Backoff Delay
                        backoff_base = int(get_config('backoff_base'))
                        delay = backoff_base ** attempts 
                        next_run_at = datetime.utcnow() + timedelta(seconds=delay)
                        
                        update_job_state(job_id, 'pending', 
                                         attempts=attempts, 
                                         next_run_at=next_run_at.isoformat(),
                                         error_message=error_msg)
                        
                        print(f"[{worker_id}] ⚠️ Job {job_id} failed. Retrying in {delay}s at {next_run_at.strftime('%H:%M:%S UTC')}")
                    time.sleep(0.05)
                        
            except subprocess.TimeoutExpired:
                # Timeout handling (Good for robustness)
                error_msg = "Job execution timed out after 30 seconds."
                update_job_state(job_id, 'pending', attempts=attempts, error_message=error_msg)
                print(f"[{worker_id}] ⏳ Job {job_id} timed out. Resetting to pending.")
            
            except Exception as e:
                error_msg = f"Worker internal error: {e}"
                print(f"[{worker_id}] 🚨 Worker internal error for Job {job_id}: {e}")
                update_job_state(job_id, 'pending', attempts=job['attempts'], error_message=error_msg) 
            
        else:
            time.sleep(1)

    print(f"[{worker_id}] Worker received stop signal. Shutting down gracefully.")