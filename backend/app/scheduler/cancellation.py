"""Per-job CP-SAT cancellation registry.

Each background scheduler thread registers the CpSolver instances it constructs
with the job_id that owns the run. A cancel endpoint can then look up the
job and call ``solver.stop_search()`` on every registered solver, which makes
``CpSolver.Solve()`` return promptly with status=UNKNOWN. The job thread
checks ``is_cancelled(job_id)`` before writing back results so a cancelled run
records ``status='cancelled'`` rather than overwriting it with a stale value.

``CpSolver.stop_search()`` is documented as thread-safe: it sets a flag that
the C++ workers poll periodically. Calling it on an already-finished solver
is a no-op.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from ortools.sat.python.cp_model import CpSolver

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_solvers_by_job: dict[str, set["CpSolver"]] = {}
_cancelled_jobs: set[str] = set()


@contextmanager
def register_solver(job_id: str | None, solver: "CpSolver") -> Iterator[None]:
    """Register *solver* against *job_id* for the duration of a Solve() call.

    A None job_id (ad-hoc CLI / test calls) is a no-op.
    """
    if job_id is None:
        yield
        return
    with _lock:
        _solvers_by_job.setdefault(job_id, set()).add(solver)
        already_cancelled = job_id in _cancelled_jobs
    if already_cancelled:
        try:
            solver.stop_search()
        except Exception:
            logger.exception("stop_search on pre-cancelled job %s failed", job_id)
    try:
        yield
    finally:
        with _lock:
            bucket = _solvers_by_job.get(job_id)
            if bucket is not None:
                bucket.discard(solver)
                if not bucket:
                    _solvers_by_job.pop(job_id, None)


def cancel_job(job_id: str) -> int:
    """Stop any active solvers for *job_id* and mark the job cancelled.

    Returns the number of solvers stopped. Marking happens unconditionally so
    a cancel that lands after the solver naturally finished still tells
    ``_run_schedule_job`` to skip the result write.
    """
    with _lock:
        _cancelled_jobs.add(job_id)
        solvers = list(_solvers_by_job.get(job_id, ()))
    stopped = 0
    for solver in solvers:
        try:
            solver.stop_search()
            stopped += 1
        except Exception:
            logger.exception("stop_search failed for job %s", job_id)
    if stopped:
        logger.info("cancel_job: stopped %d solver(s) for job %s", stopped, job_id)
    return stopped


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return job_id in _cancelled_jobs


def clear_cancelled(job_id: str) -> None:
    """Drop *job_id* from the cancelled set. Called from the background thread
    once it has finished writing the terminal ``cancelled`` status, so the
    in-memory set doesn't grow unbounded over the life of the process.
    """
    with _lock:
        _cancelled_jobs.discard(job_id)
