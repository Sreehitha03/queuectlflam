# src/cli.py 
import multiprocessing
import os # We'll use this to save PIDs
from .worker import run_worker
import click
import json
import uuid 
# Import the new functions
from .database import init_db, insert_job, set_config, get_all_configs

# ----------------------------------------------------
# 1. Main CLI Group (MUST BE DEFINED ONLY ONCE)
# ----------------------------------------------------
@click.group()
@click.pass_context 
def cli(ctx):
    """QueueCTL: A CLI-based background job queue system."""
    # Initialize the database on every command call (Crucial for persistence)
    init_db()
    # Ensure ctx.obj is a dict for sharing data (best practice)
    ctx.ensure_object(dict)

# ----------------- 1. Enqueue Command Implementation -----------------

@cli.command()
@click.argument('job_json')
def enqueue(job_json):
    """
    Adds a new job to the queue.
    Example: queuectl enqueue '{"id":"job1","command":"sleep 2"}'
    """
    try:
        job_data = json.loads(job_json)
    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON format provided.", err=True)
        return

    # Basic Validation
    if 'command' not in job_data:
        click.echo("Error: Job must contain a 'command' field.", err=True)
        return
        
    if 'id' not in job_data:
        # Assign a UUID if no ID is provided (Assumption/Trade-off)
        job_data['id'] = str(uuid.uuid4())
        click.echo(f"Warning: No job ID provided, assigned ID: {job_data['id']}", err=True)
        
    if insert_job(job_data):
        click.echo(f"✅ Job {job_data['id']} successfully enqueued.")
    else:
        # Error message handled within insert_job (IntegrityError)
        pass


# ----------------- 2. Config Command Implementation -----------------

@cli.group()
def config():
    """Manages system configuration (retry, backoff, etc.)."""
    pass

@config.command()
@click.argument('key')
@click.argument('value')
def set(key, value):
    """Sets a configuration key-value pair (e.g., max_retries 5)."""
    # Allowed configuration keys
    allowed_keys = ['max_retries', 'backoff_base']
    
    # Normalize key input (allows user to use max-retries or max_retries)
    key = key.replace('-', '_') 

    if key not in allowed_keys:
        click.echo(f"Error: Configuration key '{key}' is not supported. Use one of: {', '.join(allowed_keys)}.", err=True)
        return

    try:
        # Validate that values are integers (since config values are numerical)
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
    # Clean, formatted output
    for k, v in configs.items():
        click.echo(f"{k.ljust(15)}: {v}")
    click.echo("-------------------------------------\n")


# ----------------- 3. Worker Command Group (Keep placeholders) -----------------
@cli.group()
def worker():
    """Manages worker processes."""
    pass


WORKER_PID_FILE = "queuectl_workers.pid" 

@worker.command()
@click.option('--count', default=1, help='Number of workers to start.', type=int)
def start(count):
    """Starts one or more worker processes."""
    if os.path.exists(WORKER_PID_FILE):
        click.echo("Error: Workers appear to already be running. Stop them first.", err=True)
        return

    workers = []
    stop_event = multiprocessing.Event()
    
    # Save PIDs to file for tracking and graceful shutdown
    pids = []

    for i in range(1, count + 1):
        # Pass the stop_event to each worker process
        worker_id = f"Worker-{i}"
        p = multiprocessing.Process(target=run_worker, args=(worker_id, stop_event))
        p.start()
        workers.append(p)
        pids.append(str(p.pid))
    
    # Write PIDs to file
    with open(WORKER_PID_FILE, 'w') as f:
        f.write("\n".join(pids))
        
    click.echo(f"✅ Started {len(workers)} worker(s). PIDs written to {WORKER_PID_FILE}")
    
    try:
        # Wait for workers to finish (blocking)
        for p in workers:
            p.join()
    except KeyboardInterrupt:
        click.echo("\nReceived interrupt signal. Initiating graceful worker shutdown...")
        stop_event.set()
        # Wait for workers to cleanly exit their loop
        for p in workers:
            p.join(timeout=5)
    
    # Clean up PID file after all workers exit
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
        import signal
        for pid in pids:
            try:
                # Send SIGINT (Ctrl+C equivalent)
                os.kill(pid, signal.SIGINT)
                click.echo(f"Sent shutdown signal to PID {pid}.")
            except ProcessLookupError:
                click.echo(f"PID {pid} not found (already dead).", err=True)
            except Exception as e:
                 click.echo(f"Could not signal PID {pid}: {e}", err=True)

    # Remove PID file immediately to prevent re-runs until workers are confirmed dead
    if os.path.exists(WORKER_PID_FILE):
        os.remove(WORKER_PID_FILE)
        
    click.echo("Worker shutdown signaled. Monitor the original terminal for completion.")