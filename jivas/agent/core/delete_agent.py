from __future__ import annotations
from jaclang import *
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agents import Agents

class delete_agent(agent_graph_walker, Walker):
    agent_id: str = field("")

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agents(self, here: Agents) -> None:
        agent_node = here.delete(self.agent_id)
        if self.reporting:
            Jac.report(agent_node)
