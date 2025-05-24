from __future__ import annotations

from jaclang import *

from jivas.agent.core.agent import Agent
from jivas.agent.core.agent_graph_walker import agent_graph_walker


class healthcheck(agent_graph_walker, Walker):

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        healthcheck_report = here.get_healthcheck_report()
        if healthcheck_report.get("status", 503) == 200:
            Jac.get_context().status = 200
        else:
            Jac.get_context().status = 503
        Jac.report(healthcheck_report)
