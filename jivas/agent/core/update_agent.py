from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.modules.agentlib.utils import Utils
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agent import Agent

class update_agent(agent_graph_walker, Walker):
    agent_data: dict = field(gen=lambda: {})
    with_actions: bool = field(False)
    reporting: bool = field(True)
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        if agent_node := here.update(
            data=self.agent_data, with_actions=self.with_actions
        ):
            if agent_node:
                if self.reporting:
                    Jac.report(agent_node.get_descriptor())
            else:
                self.logger.error("unable to update agent")
                if self.reporting:
                    Jac.get_context().status = 500
                    Jac.report("unable to update agent")
