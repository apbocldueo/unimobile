"""EcoAgent as six-family components and ordinary AgentGraph state/routers/loop."""

from zhixing.graph import (AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec, NodeContractRef,
    Predicate, PredicateOperator, RouterCase, StateOperation, StateScope, StateSpec, SubgraphSpec)


def build_ecoagent_graph(*, max_rounds=30, fix_protocol=True, wait_seconds=2.0, model_params=None):
    """Build the complete selected online profile without service construction or I/O.

    Args:
        max_rounds: Official logical verification-loop bound.
        fix_protocol: Separately documented JSON-fence/point-tag syntax repairs.
        wait_seconds: Source post-action two-second wait.
        model_params: Public settings per planner/executor/description/summary dependency.
    Raises:
        ValueError: Bounds, switches or model slots are invalid.
    Returns:
        AgentGraph: Explicit complete flow without a paradigm-specific Kernel branch.
    """
    if type(max_rounds) is not int or not 1 <= max_rounds <= 999 or type(fix_protocol) is not bool or not 0 <= wait_seconds <= 60:
        raise ValueError('Invalid EcoAgent graph bounds')
    settings = dict(model_params or {})
    if set(settings) - {'planner', 'executor', 'description', 'summary'}:
        raise ValueError('Unknown EcoAgent model slot')
    # Startup Home + initial action + at most one action per verification round.
    # Kernel stops at >= physical bound, so retain one final non-action margin.
    policies = GraphPolicies(max_steps=max_rounds + 3, max_activations=max_rounds * 28 + 20)

    def node(builder, name, family, plugin=None, contract='frame', params=None, dependency=None, role=False, primary=False):
        """Declare one stage. Args: builder,name,family,plugin,contract,params,dependency,role,primary: Node settings. Returns: None."""
        deps = {}
        if dependency:
            values = dict(settings.get(dependency, {}))
            if dependency == 'planner':
                values.setdefault('api_key', {'secret_ref': 'ecoagent_cloud_key'})
            deps[dependency + '_llm'] = {'namespace': 'llm', 'name': 'ecoagent_llm', 'params': values}
        builder.add_component(name, namespace='agent.' + family, name='ecoagent_' + (plugin or name),
            contract=NodeContractRef(id='zhixing.ecoagent.' + contract, version='1.0'), params=params or {},
            dependencies=deps, role=GraphRole(family) if role else None, primary=primary)

    def wire(builder, edges):
        """Connect ordered ports. Args: builder,edges: Builder and address pairs. Returns: None."""
        for origin, target in edges:
            builder.connect(*origin.split('.'), *target.split('.'))

    body = AgentGraphBuilder(policies=policies).add_input()
    body.add_state('previous', StateSpec(key='ecoagent_round', data_type='ecoagent_frame', scope=StateScope.RUN, operation=StateOperation.READ))
    node(body, 'resume', 'memory', contract='resume', role=True)
    node(body, 'describe', 'perception', 'description', contract='read', dependency='description', role=True)
    node(body, 'summarize', 'verifier', 'summary', contract='read', dependency='summary', role=True)
    node(body, 'predict', 'reasoning', contract='read', dependency='executor', role=True)
    node(body, 'summary', 'verifier', params={'collect': True})
    node(body, 'description', 'perception', params={'collect': True})
    node(body, 'join', 'memory', contract='read')
    body.add_router('verified', (RouterCase(id='accepted', predicate=Predicate(field='accepted', operator=PredicateOperator.TRUTHY)),), default='replan')
    node(body, 'continue', 'memory')
    node(body, 'replan', 'planner', 'plan', contract='read', dependency='planner', role=True,
        params={'replan': True, **({'fix_protocol': False} if not fix_protocol else {})})
    node(body, 'selected', 'memory', 'merge', contract='merge')
    body.add_router('done', (RouterCase(id='yes', predicate=Predicate(field='finished', operator=PredicateOperator.TRUTHY)),), default='execute')
    node(body, 'terminal', 'memory', 'merge', contract='merge')
    node(body, 'action', 'reasoning', contract='read', dependency='executor')
    executor = {**({'fix_protocol': False} if not fix_protocol else {}), **({'wait_seconds': wait_seconds} if wait_seconds != 2.0 else {})}
    node(body, 'execute', 'action_executor', contract='execute', params=executor, role=True, primary=True)
    node(body, 'observe', 'perception', contract='read')
    node(body, 'merge', 'memory', contract='merge')
    node(body, 'commit', 'memory')
    body.add_state('save', StateSpec(key='ecoagent_round', data_type='ecoagent_frame', scope=StateScope.RUN, operation=StateOperation.WRITE)).add_output()
    wire(body, (('input.value','previous.control'), ('input.value','resume.initial'), ('previous.value','resume.previous'),
        ('resume.result','describe.frame'), ('describe.result','summarize.frame'), ('summarize.result','predict.frame'),
        ('predict.result','summary.frame'), ('summary.result','description.frame'), ('description.result','join.frame'),
        ('join.result','verified.value'), ('join.result','continue.frame'), ('join.result','replan.frame'),
        ('continue.result','selected.values'), ('replan.result','selected.values'), ('selected.result','done.value'),
        ('selected.result','terminal.values'), ('selected.result','action.frame'), ('action.result','execute.frame'),
        ('execute.result','observe.frame'), ('observe.result','merge.values'), ('terminal.result','merge.values'),
        ('merge.result','commit.frame'), ('commit.result','save.write'), ('save.value','output.result')))
    body.control('verified','accepted','continue').control('verified','replan','replan')
    body.control('done','yes','terminal').control('done','execute','action')
    loop = LoopSpec(body=SubgraphSpec(graph=body.build(), inputs={'value':'value'}, outputs={'result':'result'}, max_activations=28),
        inputs={'value':'value'}, outputs={'result':'result'}, until=Predicate(field='result.finished', operator=PredicateOperator.TRUTHY),
        max_iterations=max_rounds, max_activations=max_rounds * 28, on_exhausted='continue')
    graph = AgentGraphBuilder(policies=policies).add_input()
    node(graph, 'initialize', 'memory', contract='initialize', params={'fix_protocol': False} if not fix_protocol else {})
    node(graph, 'home', 'action_executor', 'execute', contract='execute', params={'home': True})
    node(graph, 'screen', 'perception', 'observe', contract='read')
    node(graph, 'plan', 'planner', contract='read', dependency='planner', params={'fix_protocol': False} if not fix_protocol else {})
    node(graph, 'action', 'reasoning', contract='read', dependency='executor')
    node(graph, 'execute', 'action_executor', contract='execute', params=executor)
    node(graph, 'observe', 'perception', contract='read')
    graph.add_loop('rounds', loop)
    node(graph, 'finish', 'memory', contract='finish')
    graph.add_output()
    wire(graph, (('input.task','initialize.task'), ('initialize.result','home.frame'), ('home.result','screen.frame'),
        ('screen.result','plan.frame'), ('plan.result','action.frame'), ('action.result','execute.frame'),
        ('execute.result','observe.frame'), ('observe.result','rounds.value'), ('rounds.result','finish.frame'), ('finish.result','output.result')))
    return graph.build()
