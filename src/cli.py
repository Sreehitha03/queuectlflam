# src/cli.py 
import click
import json
import uuid 
import os
import signal
import multiprocessing
from datetime import datetime
import sys

# Import worker function and DB utilities
from .worker import run_worker
from .database import (
    init_db, 
    insert_job, 
    set_config, 
    get_all_configs, 
    get_job_status_summary,  
    get_jobs_by_state,       
    retry_dlq_job            
)

# File used to track active worker processes
WORKER_PID_FILE = "queuectl_workers.pid" 

# -------------------
# 1. Main CLI Group
# -------------------
@click.group()
@click.pass_context 
def cli(ctx):
    """QueueCTL: A CLI-based background job queue system."""
    # Initialize the database on every command call
    init_db()
    ctx.ensure_object(dict)

# ----------------- 2. Enqueue Command Implementation -----------------

@cli.command()
@click.argument('job_json', required=False) # MAKE ARGUMENT OPTIONAL
def enqueue(job_json):
    """
    Adds a new job to the queue.
    Example: queuectl enqueue '{"id":"job1","command":"sleep 2"}'
    Example (Robust): echo '{"id":"j1","command":"sleep 2"}' | python -m src.cli enqueue
    """
    if not job_json:
        # If no argument is provided, read from STDIN (piped input)
        try:
            job_json = sys.stdin.read().strip()
        except:
            click.echo("Error: No job data provided via argument or STDIN.", err=True)
            return

    # --- Start of existing logic ---
    try:
        # Robust stripping logic
        job_json = job_json.strip().strip("'").strip('"') 
        
        # Check if the stripped string is empty before attempting loads
        if not job_json:
             click.echo("Error: Empty job data provided.", err=True)
             return

        job_data = json.loads(job_json)
    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON format provided. (Ensure inner double quotes are used)", err=True)
        return

    # Basic Validation
    if 'command' not in job_data:
        click.echo("Error: Job must contain a 'command' field.", err=True)
        return
        
    if 'id' not in job_data:
        job_data['id'] = str(uuid.uuid4())
        click.echo(f"Warning: No job ID provided, assigned ID: {job_data['id']}", err=True)
        
    if insert_job(job_data):
        click.echo(f"✅ Job {job_data['id']} successfully enqueued.")
    else:
        # Error message handled within insert_job (IntegrityError)
        pass


# ----------------- 3. Config Command Implementation -----------------

@cli.group()
def config():
    """Manages system configuration (retry, backoff, etc.)."""
    pass

@config.command()
@click.argument('key')
@click.argument('value')
def set(key, value):
    """Sets a configuration key-value pair (e.g., max-retries 5)."""
    allowed_keys = ['max_retries', 'backoff_base']
    key = key.replace('-', '_') 

    if key not in allowed_keys:
        click.echo(f"Error: Configuration key '{key}' is not supported. Use one of: {', '.join(allowed_keys)}.", err=True)
        return

    try:
        int(value) 
    except ValueError:
        click.echo(f"Error: Value for key '{key}' must be an integer.", err=True)
        return

    set_config(key, value)
    click.echo(f"✅ Config updated: {key} = {value}")

@config.command()
def show():
    """Shows the current system configuration."""
    configs = get_all_configs()
    click.echo("\n--- Current QueueCTL Configuration ---")
    for k, v in configs.items():
        click.echo(f"{k.ljust(15)}: {v}")
    click.echo("-------------------------------------\n")


# ----------------- 4. Worker Management Implementation -----------------

@cli.group()
def worker():
    """Manages worker processes."""
    pass

@worker.command()
@click.option('--count', default=1, help='Number of workers to start.', type=int)
def start(count):
    """Starts one or more worker processes."""
    if os.path.exists(WORKER_PID_FILE):
        click.echo("Error: Workers appear to already be running. Stop them first.", err=True)
        return

    workers = []
    stop_event = multiprocessing.Event()
    pids = []

    for i in range(1, count + 1):
        worker_id = f"Worker-{i}"
        p = multiprocessing.Process(target=run_worker, args=(worker_id, stop_event))
        p.start()
        workers.append(p)
        pids.append(str(p.pid))
    
    with open(WORKER_PID_FILE, 'w') as f:
        f.write("\n".join(pids))
        
    click.echo(f"✅ Started {len(workers)} worker(s). PIDs written to {WORKER_PID_FILE}")
    
    try:
        for p in workers:
            p.join()
    except KeyboardInterrupt:
        click.echo("\nReceived interrupt signal. Initiating graceful worker shutdown...")
        stop_event.set()
        for p in workers:
            p.join(timeout=5)
    
    if os.path.exists(WORKER_PID_FILE):
        os.remove(WORKER_PID_FILE)
    click.echo("All workers stopped.")


@worker.command()
def stop():
    """Stops running workers gracefully."""
    if not os.path.exists(WORKER_PID_FILE):
        click.echo("No active worker PID file found. Workers are likely not running.")
        return

    click.echo("Attempting graceful shutdown of workers...")
    
    try:
        with open(WORKER_PID_FILE, 'r') as f:
            pids = [int(p.strip()) for p in f.readlines() if p.strip()]
    except Exception:
        pids = []

    if pids:
        # Note: Sending SIGINT works on most Unix/Windows systems for process termination.
        for pid in pids:
            try:
                os.kill(pid, signal.SIGINT)
                click.echo(f"Sent shutdown signal to PID {pid}.")
            except ProcessLookupError:
                click.echo(f"PID {pid} not found (already dead).", err=True)
            except Exception as e:
                 click.echo(f"Could not signal PID {pid}: {e}", err=True)

    if os.path.exists(WORKER_PID_FILE):
        os.remove(WORKER_PID_FILE)
        
    click.echo("Worker shutdown signaled. Monitor the original terminal for completion.") 

# ----------------- 5. Status Command Implementation -----------------

@cli.command()
def status():
    """Show summary of all job states & active workers."""
    summary = get_job_status_summary()
    
    active_workers = 0
    if os.path.exists(WORKER_PID_FILE):
        try:
            with open(WORKER_PID_FILE, 'r') as f:
                active_workers = len([p.strip() for p in f.readlines() if p.strip()])
        except Exception:
            pass 

    click.echo("\n--- QueueCTL System Status ---")
    click.echo(f"Active Workers: {active_workers}\n")
    
    states = ['pending', 'processing', 'completed', 'failed', 'dead']
    total_jobs = 0

    click.echo("--- Job Summary ---")
    for state in states:
        count = summary.get(state, 0)
        click.echo(f"{state.ljust(12)}: {count}")
        total_jobs += count
        
    click.echo("-" * 21)
    click.echo(f"{'TOTAL'.ljust(12)}: {total_jobs}")
    click.echo("---------------------------\n")


# ----------------- 6. List Jobs Command Implementation -----------------

@cli.command()
@click.pass_context # MUST add context to use ctx.forward/invoke later
@click.option('--state', default='pending', help='State to filter jobs by.', type=str)
def list(ctx, state): # MUST accept ctx as the first argument
    """List jobs by state (pending, processing, completed, dead, etc.)."""
    jobs = get_jobs_by_state(state)
    
    click.echo(f"\n--- Jobs in '{state.upper()}' State ({len(jobs)} total) ---")
    
    if not jobs:
        click.echo("No jobs found in this state.")
        return

    # Simple table-like output for readability
    click.echo(f"{'ID'.ljust(38)} | {'ATT/MAX'.ljust(9)} | {'UPDATED AT'.ljust(20)} | COMMAND")
    click.echo("-" * 100)

    for job in jobs:
        # NOTE: Ensure updated_at is properly handled as datetime object for formatting
        attempts_str = f"{job['attempts']}/{job['max_retries']}"
        # We need to explicitly convert from ISO string to datetime object for strftime
        try:
             updated_dt = datetime.fromisoformat(job['updated_at']).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
             updated_dt = job['updated_at'] # Fallback if format is wrong

        command_short = (job['command'][:40] + '...') if len(job['command']) > 40 else job['command']
        
        click.echo(f"{job['id'].ljust(38)} | {attempts_str.ljust(9)} | {updated_dt.ljust(20)} | {command_short}")
    
    click.echo("-" * 100)

# ----------------- 7. DLQ Command Group Implementation -----------------

@cli.group()
def dlq():
    """Manages the Dead Letter Queue (DLQ)."""
    pass

@dlq.command(name='list') # Need to name it 'list' as it's a sub-command
@click.pass_context # MUST add context here
def dlq_list(ctx): # MUST accept ctx as the argument
    """View jobs in the Dead Letter Queue."""
    # Correct way to invoke one command from another:
    # ctx.invoke calls the function directly; ctx.forward calls the command group process.
    # Since 'list' takes an option/argument, we use invoke.
    ctx.invoke(list, state='dead') # Use the function name (list) and pass kwargs

@dlq.command()
@click.argument('job_id')
def retry(job_id):
    """Retries a permanently failed job from the DLQ."""
    if retry_dlq_job(job_id):
        click.echo(f"✅ Job {job_id} successfully moved to PENDING for retry (attempts reset).")
    else:
        click.echo(f"❌ Error: Job {job_id} not found in DLQ or is not in 'dead' state.", err=True)
if __name__ == '__main__':
    cli(obj={}) 