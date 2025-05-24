from __future__ import annotations
from jaclang import *
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.app import App
from jivas.agent.core.agents import Agents

class list_agents(agent_graph_walker, Walker):

    class __specs__(Obj):
        private: static[bool] = False
        excluded: static[list] = JacList(["agent_id"])

    @with_entry
    def on_agents(self, here: Agents) -> None:
        if agents := here.get_all():
            for agent in agents:
                Jac.report(agent.export())
