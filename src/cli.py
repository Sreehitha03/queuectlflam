# src/cli.py (Corrected for Step 2)
import click
from .database import init_db # Import the database initialization function

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

# --- Command Imports will go here later ---

# 1. Enqueue Command (Placeholder)
@cli.command()
@click.argument('job_json')
def enqueue(job_json):
    """Adds a new job to the queue."""
    click.echo(f"Attempting to enqueue: {job_json}")
    # Logic will be implemented in Step 3

# 2. Worker Command Group (Placeholder)
@cli.group()
def worker():
    """Manages worker processes."""
    pass

@worker.command()
@click.option('--count', default=1, help='Number of workers to start.', type=int)
def start(count):
    """Starts one or more worker processes."""
    click.echo(f"Starting {count} workers...")
    # Logic will be implemented in Step 5

@worker.command()
def stop():
    """Stops running workers gracefully."""
    click.echo("Stopping workers...")
    # Logic will be implemented in Step 5

# --- Other commands (status, list, dlq, config) will go here later ---

if __name__ == '__main__':
    # Pass the context object when calling the cli group directly
    cli(obj={})