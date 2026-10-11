"""Exception types.

Each failure mode gets its own class so the CLI (and Airflow) can react
differently: bad inputs are a data-delivery problem, a DQ alarm is a data-content
problem, and neither should be blindly retried.
"""


class PipelineError(Exception):
    """Base class for every error the pipeline raises on purpose."""

    exit_code = 1


class InputDataError(PipelineError):
    """A source file is missing, empty, malformed, or lacks an expected column."""

    exit_code = 2


class DataQualityError(PipelineError):
    """At least one data-quality check failed (the 'alarm')."""

    exit_code = 3

    def __init__(self, message, results=None):
        super().__init__(message)
        self.results = results or []
