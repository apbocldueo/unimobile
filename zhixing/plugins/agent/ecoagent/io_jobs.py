"""Caller-owned generic concurrent I/O; graph tickets contain no live resources."""

from concurrent.futures import ThreadPoolExecutor, wait

from zhixing.core.llm.usage import record_usage
from .types import reply


def account(value):
    """Record returned usage on the calling task thread, including discarded work.

    Args:
        value: Portable EcoReply returned by a worker or synchronous request.
    Returns:
        EcoReply: Same response, after optional task-local accounting.
    """
    value = reply(value)
    if value.has_usage:
        record_usage(prompt_tokens=value.prompt_tokens, completion_tokens=value.completion_tokens,
                     total_tokens=value.total_tokens)
    return value


class InferenceFailure(RuntimeError):
    """Sanitized request failure retaining only its exception class for audit."""

    def __init__(self, error_type):
        """Store safe category. Args: error_type: Exception class name. Returns: None."""
        self.error_type = error_type
        super().__init__('EcoAgent inference failed (' + error_type + ')')


class InferenceJobs:
    """Lazy private thread pool owned by exactly one explicit run scope."""

    def __init__(self):
        """Create inert bookkeeping. Returns: None: No threads, network or secrets."""
        self.owner = None
        self.pool = None
        self.futures = {}
        self.rounds = {}
        self.recorded = set()
        self.closed = False

    def claim(self, owner):
        """Bind one run identity and reject cross-run sharing.

        Args:
            owner: Runtime run id.
        Raises:
            RuntimeError: Closed or already claimed by a different run.
        Returns:
            None.
        """
        if self.closed or self.owner not in (None, owner):
            raise RuntimeError('Inference jobs require a fresh run scope')
        self.owner = owner

    def submit(self, owner, round_number, kind, request):
        """Submit one model request; no task interpretation or device work occurs here.

        Args:
            owner,round_number,kind: Explicit run/round/request identity.
            request: Zero-argument I/O callable returning EcoReply.
        Raises:
            RuntimeError: Scope or ticket is reused.
        Returns:
            str: Portable ticket scoped to this owner and round.
        """
        self.claim(owner)
        ticket = f'{owner}:{round_number}:{kind}'
        if ticket in self.futures:
            raise RuntimeError('Duplicate inference ticket')
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='ecoagent-io')
        self.futures[ticket] = self.pool.submit(request)
        self.rounds[ticket] = round_number
        return ticket

    def join(self, round_number=None):
        """Wait without consuming errors; account successes only on the task thread.

        Args:
            round_number: One round or None for all owned requests.
        Returns:
            None: Predictive errors remain latent until collect().
        """
        selected = [key for key in self.futures if round_number is None or self.rounds[key] == round_number]
        wait([self.futures[key] for key in selected])
        for key in selected:
            if key not in self.recorded:
                future = self.futures[key]
                if not future.cancelled() and future.exception() is None:
                    try:
                        account(future.result())
                    except TypeError:
                        # Malformed discarded predictions are latent failures too.
                        # Only collect() is allowed to consume their contract error.
                        pass
                self.recorded.add(key)

    def collect(self, owner, round_number, ticket):
        """Consume one result, joining siblings before propagating a sanitized failure.

        Args:
            owner,round_number,ticket: Exact current scope identity.
        Raises:
            RuntimeError: Ticket is missing, stale or belongs to another run.
            InferenceFailure: The requested result failed, after all siblings joined.
        Returns:
            EcoReply: Selected model response.
        """
        self.claim(owner)
        if ticket not in self.futures or self.rounds[ticket] != round_number:
            raise RuntimeError('Invalid or stale inference ticket')
        try:
            return reply(self.futures[ticket].result())
        except Exception as error:
            self.join(round_number)
            raise InferenceFailure(type(error).__name__) from None

    def close(self):
        """Join and release every private Future on success, failure or cancellation.

        Returns:
            None: Subsequent submissions are rejected.
        """
        try:
            self.join()
        finally:
            if self.pool is not None:
                self.pool.shutdown(wait=True)
            self.closed = True
            self.futures.clear()
            self.rounds.clear()
