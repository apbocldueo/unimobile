"""Real thread overlap, ownership, cancellation, accounting and cleanup evidence."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from zhixing.components import RunStatus, RuntimeContext
from zhixing.core.llm.usage import get_task_usage_dict, reset_task_usage
from zhixing.ecoagent import build_ecoagent_graph
from zhixing.plugins.agent.ecoagent.environment import EcoEnvironment
from zhixing.plugins.agent.ecoagent.io_jobs import InferenceFailure, InferenceJobs
from zhixing.plugins.agent.ecoagent.types import EcoReply
from zhixing.runtime import SimpleCancellationSignal
from zhixing.sdk import AgentRunConfig, compile_agent
from tests.runtime.ecoagent_support import Device, Models, plan, run_graph


def test_complete_graph_overlaps_all_three_requests(tmp_path):
    """A barrier cannot complete unless the production graph really issues all three requests.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    barrier=threading.Barrier(3,timeout=5)
    result,runtime,device,models,jobs=run_graph(tmp_path,[plan('INPUT [hi]','TAP Save')],max_rounds=1,barrier=barrier)
    assert result.status is RunStatus.STEP_LIMIT,result.error
    assert len(models.calls['action'])==len(models.calls['summary'])==len(models.calls['description'])==1
    assert jobs.closed and not jobs.futures


def test_replan_waits_for_old_prediction_before_requesting_cloud(tmp_path):
    """Prove source join-before-replan, and count usage of the discarded prediction.

    Args:
        tmp_path: Isolated artifact root.
    Returns:
        None.
    """
    entered,release,finished=threading.Event(),threading.Event(),threading.Event()
    models=Models([plan('INPUT [hi]','TAP Save'),plan('PRESS_HOME')],summaries=('not correct','matches'))
    original=models.complete
    def complete(operation,prompt,images):
        """Hold only the old prediction. Args: operation,prompt,images: Request. Returns: EcoReply: Original fixture."""
        if operation=='action':
            entered.set();assert release.wait(5)
            value=original(operation,prompt,images);finished.set();return value
        if operation=='replanning':assert finished.is_set()
        return original(operation,prompt,images)
    models.complete=complete
    raw=Device();graph=build_ecoagent_graph()
    dependencies={k+'_llm':models for k in ('planner','executor','description','summary')}
    agent=compile_agent(graph,dependencies=dependencies)
    def execute():
        """Execute with a task-local usage scope. Returns: tuple: Result/usage/closed jobs."""
        reset_task_usage()
        with EcoEnvironment(raw,sleep=raw.sleep) as boundary:
            jobs=boundary.jobs
            result=agent.run('fixture task',AgentRunConfig(artifact_root=tmp_path,max_steps=graph.policies.max_steps),device=boundary)
        return result,get_task_usage_dict(),jobs
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(execute)
        try:
            assert entered.wait(5)
            assert not models.calls['replanning']
        finally:
            release.set()
        result,usage,jobs=future.result(timeout=10)
    assert result.status is RunStatus.SUCCESS,result.error
    assert usage['call_count']==7 and usage['total_tokens']==70
    assert result.action_results[-1].metadata['ecoagent']['llm_calls']==2
    assert jobs.closed and not jobs.futures
    assert not any(e[0]=='device' and 'tap' in e[1] for e in raw.events)


def test_cancellation_after_submissions_joins_and_never_executes_prediction(tmp_path):
    """Cancel at a real node boundary after submission; context exit drains workers.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    models=Models([plan('INPUT [hi]','TAP Save')])
    graph=build_ecoagent_graph()
    signal=SimpleCancellationSignal()
    def events(event):
        """Cancel after prediction submit. Args: event: Kernel event. Returns: None."""
        if event.node_path=='rounds/predict' and event.kind=='complete':signal.cancel()
    runtime=RuntimeContext(max_steps=graph.policies.max_steps,cancellation=signal,event_sink=events)
    raw=Device()
    with EcoEnvironment(raw,sleep=raw.sleep) as boundary:
        jobs=boundary.jobs
        result=compile_agent(graph,dependencies={k+'_llm':models for k in ('planner','executor','description','summary')}).run(
            'fixture task',AgentRunConfig(artifact_root=tmp_path,max_steps=graph.policies.max_steps),runtime=runtime,device=boundary)
    assert signal.cancelled
    assert result.status is RunStatus.CANCELLED,result.error
    assert jobs.closed and not jobs.futures
    assert not any(e[0]=='device' and 'tap' in e[1] for e in raw.events)


def test_two_sdk_runs_require_fresh_owned_jobs_and_do_not_share_state(tmp_path):
    """Run the same executable twice; reject reuse of an active dependency across run ids.

    Args:
        tmp_path: Isolated artifact root.
    Returns:
        None.
    """
    models=Models([plan('PRESS_BACK'),plan('PRESS_BACK')])
    # Independent model scripts per run; the same executable resolves the named dependency provider anew.
    class PerRunModel:
        """Repeat a stateless external service while framework state must stay isolated."""
        def complete(self,operation,prompt,images):
            """Reply independently. Args: operation,prompt,images: Request. Returns: EcoReply: Scenario reply."""
            return EcoReply(plan('PRESS_BACK') if operation=='planning' else 'matches',10)
    graph=build_ecoagent_graph();model=PerRunModel()
    agent=compile_agent(graph,dependencies={k+'_llm':model for k in ('planner','executor','description','summary')})
    raw=Device();boundary=EcoEnvironment(raw,sleep=raw.sleep)
    payloads=[]
    for i in range(2):
        with boundary:
            jobs=boundary.jobs
            result=agent.run('fixture task',AgentRunConfig(artifact_root=tmp_path,max_steps=graph.policies.max_steps),device=boundary)
            assert result.status is RunStatus.SUCCESS,result.error
            payloads.append(result.action_results[-1].metadata['ecoagent'])
        assert jobs.closed
    assert payloads[0]==payloads[1] and payloads[0]['logical_rounds']==1
    assert len(list(tmp_path.iterdir()))==2
    jobs=InferenceJobs();jobs.claim('one')
    with pytest.raises(RuntimeError,match='fresh run'):jobs.claim('two')
    jobs.close()


def test_ticket_duplicates_staleness_errors_and_lazy_start():
    """Check request identity and latent failures without private exceptions in State.

    Returns:
        None.
    """
    jobs=InferenceJobs()
    assert jobs.pool is None
    def fail():
        """Fail externally. Raises: LookupError: Fixture. Returns: None."""
        raise LookupError('private endpoint detail')
    ticket=jobs.submit('run',0,'prediction',fail)
    jobs.join(0)  # Does not consume the failed prediction.
    with pytest.raises(RuntimeError,match='Duplicate'):jobs.submit('run',0,'prediction',fail)
    with pytest.raises(RuntimeError,match='stale'):jobs.collect('run',1,ticket)
    with pytest.raises(InferenceFailure) as error:jobs.collect('run',0,ticket)
    assert error.value.error_type=='LookupError' and 'private' not in str(error.value)
    bad=jobs.submit('run',1,'prediction',lambda:object())
    jobs.join(1)  # Invalid unused reply is latent too.
    with pytest.raises(InferenceFailure):jobs.collect('run',1,bad)
    jobs.close()
    assert jobs.closed and not jobs.futures
    with pytest.raises(RuntimeError):jobs.submit('run',2,'prediction',fail)
