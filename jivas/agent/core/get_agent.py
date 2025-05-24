from __future__ import annotations
from jaclang import *
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agent import Agent

class get_agent(agent_graph_walker, Walker):

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        Jac.report(here.export())
