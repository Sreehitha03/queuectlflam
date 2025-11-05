# src/cli.py
import click

@click.group()
def cli():
    """QueueCTL: A CLI-based background job queue system."""
    pass

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
    cli()