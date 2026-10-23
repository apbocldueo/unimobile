"""Differential online tests against the frozen author's methods and outer loop."""

import json
from pathlib import Path

import pytest

from zhixing.components import RunStatus
from zhixing.graph import load_graph_yaml
from tests.runtime.ecoagent_support import plan, reference, run_graph


@pytest.mark.parametrize('plans,settings', [
    ([plan('PRESS_BACK','INPUT [hi]')], {}),
    ([plan('PRESS_BACK')], {}),
    ([plan('INPUT [hi]','TAP Save')], {}),
    ([plan('INPUT [hi]','TAP Save'),plan('PRESS_HOME')], {'summaries':('not correct','matches')}),
    ([plan('INPUT [hi]','TAP Save'),'No need to replan.'], {'summaries':('not correct','matches')}),
    ([plan('PRESS_BACK'),'No need to replan.'], {'summaries':('not correct',)}),
    ([plan('PRESS_BACK','PRESS_HOME','INPUT [hi]')], {'max_rounds':2}),
    ([plan('PRESS_BACK')], {'summaries':('No',)}),
    ([plan('INPUT [hi]','TAP Save'),plan('PRESS_HOME')], {'summaries':('not correct','matches'), 'actions':(RuntimeError('unused'),)}),
    ([plan('PRESS_BACK','DELETE TEXT','INPUT [中文 with spaces]')], {}),
    ([plan('TAP Save')], {'actions':("Action: click(10,20) press_back() finished(content='done') click(90,80)",)}),
    ([plan('TAP Save')], {'actions':("Action: open_app(app_name='Contacts') press_back()",)}),
    ([plan('INPUT malformed')], {}),
    ([plan('PRESS_BACK_then_more')], {}),
    ([plan('INPUT [hi]','TAP Save'),plan('TAP Save')], {'summaries':('not correct','matches'),
        'actions':('Action: click(10,20)','Action: click(30,40)')}),
    ([plan('PRESS_BACK','TAP Save','PRESS_HOME'),plan('PRESS_BACK','INPUT [new]')],
        {'summaries':('matches','not correct','matches','matches')}),
    ([plan('TAP Save')], {'actions':("Action: type(content='hello world\\n')",)}),
])
def test_original_online_paths(tmp_path, plans, settings):
    """Compare complete source requests, data, cloud counters and physical sequence.

    Args:
        tmp_path: Isolated artifacts.
        plans,settings: Shared external reply scripts and source bounds.
    Raises:
        AssertionError: Original and graph online semantics diverge.
    Returns:
        None.
    """
    result, runtime, device, models, jobs = run_graph(tmp_path, plans, **settings)
    assert result.status in (RunStatus.SUCCESS, RunStatus.STEP_LIMIT), result.error
    expected, original_device, original_models = reference(plans, **settings)
    assert not expected['error'], expected
    actual = result.action_results[-1].metadata['ecoagent']
    for key in ('steps','expectations','descriptions','llm_calls','total_tokens'):
        assert actual[key] == expected[key]
    assert actual['source_task_success'] == expected['success']
    assert models.calls == original_models.calls
    assert device.events == original_device.events
    assert jobs.closed and not jobs.futures
    assert actual['benchmark_evaluated'] is False
    assert result.status is (RunStatus.SUCCESS if expected['success'] else RunStatus.STEP_LIMIT)
    assert result.interaction_count == sum(a.effect_performed for a in result.action_results)
    for ack in result.action_results:
        if any(command.startswith('adb shell input text ') for command in ack.metadata.get('commands', [])):
            assert ack.action.type.value == 'text'
    assert 'Future' not in json.dumps(result.to_safe_dict())


@pytest.mark.parametrize('plans,settings', [
    ([plan('PRESS_BACK',fence='json')], {}),
    ([plan('TAP Save')], {'actions':("Action: click(point='<point>10 20</point>')",)}),
    ([plan('INPUT [hi]','TAP Save'),plan('PRESS_HOME',fence='json')],
        {'summaries':('not correct','matches')}),
])
def test_recorded_protocol_repairs_match_patched_baseline(tmp_path, plans, settings):
    """Compare repairs against disposable official source plus the checked-in diff.

    Args:
        tmp_path,plans,settings: Shared scenario and artifact root.
    Returns:
        None.
    """
    result, runtime, device, models, jobs = run_graph(tmp_path, plans, **settings)
    assert result.status is RunStatus.SUCCESS, result.error
    expected, raw, original = reference(plans, repaired=True, **settings)
    assert expected['success'] and not expected['error']
    assert models.calls == original.calls
    assert device.events == raw.events


@pytest.mark.parametrize('settings', [
    {'actions':(RuntimeError('consumed prediction'),)},
    {'summaries':(ValueError('summary fixture'),)},
    {'descriptions':(LookupError('description fixture'),)},
    {'summaries':(ValueError('summary fixture'),), 'descriptions':(LookupError('desc'),), 'actions':(RuntimeError('action'),)},
])
def test_consumed_errors_are_fatal_and_work_is_drained(tmp_path, settings):
    """Retain source consumed/unconsumed distinction and exception-time sibling joining.

    Args:
        tmp_path,settings: Isolated artifacts and external failures.
    Returns:
        None.
    """
    plans = [plan('INPUT [hi]','TAP Save')]
    result, runtime, raw, models, jobs = run_graph(tmp_path, plans, **settings)
    expected, original_raw, original = reference(plans, **settings)
    assert result.status is RunStatus.FAILURE and expected['error']
    assert raw.events == original_raw.events
    assert models.calls == original.calls
    assert jobs.closed and not jobs.futures
    assert not any(e[0]=='device' and 'tap' in e[1] for e in raw.events)


def test_yaml_executes_same_complete_online_flow(tmp_path):
    """Use actual YAML and default resolver with injected external dependencies.

    Args:
        tmp_path: Isolated artifact root.
    Returns:
        None.
    """
    path = Path(__file__).resolve().parents[2]/'examples/graphs/ecoagent_online.yaml'
    result, runtime, raw, models, jobs = run_graph(tmp_path, [plan('INPUT [hi]','TAP Save'),plan('PRESS_HOME')],
        summaries=('not correct','matches'), graph=load_graph_yaml(path).graph)
    assert result.status is RunStatus.SUCCESS, result.error
    assert jobs.closed
