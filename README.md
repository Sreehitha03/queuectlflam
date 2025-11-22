# QueueCTL: A Persistent, CLI-Based Background Job Queue System (Python)

**QueueCTL** is a minimal, production-grade background job queue system built in **Python**.  
It reliably executes background shell commands using **concurrent workers**, **automatic retries** with exponential backoff, and **persistent storage** that survives restarts.

---

## Features

 Command-Line Interface built with **Python Click**  
 **Persistent job storage** using SQLite (`queuectl.db`)  
 **Concurrent worker execution** via Python’s Multiprocessing  
 **Automatic retry** with configurable exponential backoff  
 **Dead Letter Queue (DLQ)** for permanently failed jobs  
 **Race-condition safety** through atomic job acquisition  
 **Cross-platform input robustness** via STDIN-based JSON input  

---

## 🔗 Submission Details

| Requirement | Status | Implementation Detail |
|-----------------------------|--------------|------------------------|
| **Working CLI Application** | ✅ Complete | All commands implemented using **Python Click** |
| **Persistent Job Storage**  | ✅ Complete | Data stored using **SQLite** |
| **Multiple Worker Support** | ✅ Complete | Uses **Multiprocessing** for true parallelism |
| **Retry & DLQ Support**     | ✅ Complete | Exponential backoff and permanent DLQ storage |
| **Concurrency Safety**      | ✅ Fixed    | Atomic acquisition + race condition mitigation |
| **Input Robustness**        | ✅ Fixed    | Jobs enqueued through **STDIN** for safe JSON handling |
 
🎥  **Video Demo Link:** [View Demo Video](https://drive.google.com/file/d/1huW0wRjFC_dvsFFn7y9nrENpJf1_BrQp/view?usp=sharing)

---

## Architecture Overview

### Concurrency & Reliability
- **Atomic Job Acquisition** ensures that no two workers process the same job simultaneously.  
- A minor `time.sleep(0.05)` ensures **database writes are fully committed** before other workers attempt job acquisition, preventing duplicate execution.  
- Job states and configuration are stored in **SQLite**, providing **data persistence** across application restarts.

### Job Lifecycle & Backoff Logic

Jobs follow this lifecycle:  
`pending → processing → completed / failed / dead`

| State | Transition Condition | Delay (Backoff Formula) |
|--------|----------------------|--------------------------|
| **pending**        | Job created | — |
| **processing**     | Worker starts executing the job | — |
| **failed (retry)** | Job fails and `attempts ≤ max_retries` | Delay = `base^attempts` seconds |
| **dead (DLQ)**     | Job fails and `attempts > max_retries` | Moved to DLQ |
| **completed**      | Command succeeds | — |


### Usage Instructions

Use STDIN for enqueuing JSON jobs to avoid shell quoting issues across platforms.

Command     Type	    Example Command
Enqueue     Job	        echo '{"id":"job1","command":"echo Hello"}' | python -m src.cli enqueue
Check       Status	    python -m src.cli status
Start       Worker(s)	python -m src.cli worker start --count 2
View        DLQ Jobs	python -m src.cli dlq list
Retry       DLQ Job	    python -m src.cli dlq retry <job-id>

## Validation & Demo Scenarios

To demonstrate QueueCTL’s functionality, open two terminals:

CMD A → for running workers

CMD B → for managing jobs

Below are three core scenarios that showcase the system’s capabilities.

## Scenario 1: Basic Job Completion

Purpose:
Demonstrate successful job processing and transition from pending → completed.

Explanation:
A simple command (echo Success) is enqueued.
The worker fetches the pending job, executes it, and marks it as completed in the database.

Commands:

| Terminal | Step Description | Command |
|---|---|---|
| **CMD B** | Enqueue Job | `echo '{"id":"S1-success","command":"echo Success in Parallel"}' \| python -m src.cli enqueue` |
| **CMD A** | Start Worker | `python -m src.cli worker start --count 1` |
| **CMD B** | Verify Status | `python -m src.cli status` |

Expected Output:

Job S1-success transitions from pending → processing → completed.

Worker logs show successful job execution.

## Scenario 2: Retry, Exponential Backoff, and DLQ

Purpose:
Show how failed jobs retry automatically using exponential backoff and move to DLQ when retries exceed the limit.

Explanation:
A failing command (exit 1) is enqueued.
The system retries based on configured max_retries and back_off_base.
After exhausting retries, the job moves to the Dead Letter Queue (DLQ).

Commands:

| Terminal | Step Description | Command |
|---|---|---|
| **CMD B** | Set Max Retries | `python -m src.cli config set max-retries 1` |
| **CMD B** | Set Backoff Base | `python -m src.cli config set back-off-base 3` |
| **CMD B** | Enqueue Failing Job | `echo '{"id":"S2-fail","command":"exit 1"}' \| python -m src.cli enqueue` |
| **CMD A** | Start Worker | `python -m src.cli worker start --count 1` |
| **CMD B** | Verify DLQ Status | `python -m src.cli dlq list` |
| **CMD B** | Retry DLQ Job | `python -m src.cli dlq retry S2-fail` |

Expected Output:

Job retries once, waiting 3^attempts seconds between tries.

After final failure, job appears in DLQ via python -m src.cli dlq list.

Retrying DLQ job re-enqueues it successfully.

## Scenario 3: Concurrency Safety & Parallel Execution

Purpose:
Prove multiple workers can process different jobs concurrently without duplicate acquisition.

Explanation:
Two long-running jobs (ping commands) are enqueued.
Two worker processes execute them in parallel, ensuring no overlap or race condition occurs.

| Terminal | Step Description | Command |
|---|---|---|
| **CMD B** | Enqueue Job | `echo '{"id":"S1-success","command":"echo Success in Parallel"}' \| python -m src.cli enqueue` |
| **CMD A** | Start Worker (Blocking) | `python -m src.cli worker start --count 1` |
| **CMD B** | Verify Final Status | `python -m src.cli status` |

Expected Output:

Both jobs run simultaneously on different worker processes.

No duplicate job execution or missed state updates.

Status shows both jobs moving independently from processing → completed.

### Setup Instructions

### Technologies Used
- **Python 3.10+**
- **Click** — Command-line interface
- **SQLite3** — Job persistence
- **Multiprocessing** — Worker concurrency

---

### Installation Steps

```bash
# Clone the repository
git clone https://github.com/Sreehitha03/queuectlflam.git
cd queuectlflam

# (Optional) Create & activate virtual environment
python -m venv .venv
. .\.venv\Scripts\activate  # For PowerShell

# Install dependencies
pip install -r requirements.txt
