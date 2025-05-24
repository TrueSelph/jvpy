from __future__ import annotations

import logging
from logging import Logger

from jaclang import *

from jivas.agent.core.agents import Agents
from jivas.agent.core.app import App
from jivas.agent.core.graph_walker import graph_walker


class agent_graph_walker(graph_walker, Walker):
    agent_id: str = field("")
    logger: static[Logger] = logging.getLogger(__name__)

    @with_entry
    def on_app(self, here: App) -> None:
        if not self.visit(here.refs().filter(Agents, None)):
            self.logger.error(
                "App graph not initialized. Import an agent and try again."
            )

    @with_entry
    def on_agents(self, here: Agents) -> None:
        if self.agent_id:
            try:
                if agent_node := jobj(id=self.agent_id):
                    if agent_node.published:
                        self.visit(agent_node)
                else:
                    Jac.get_context().status = 400
                    Jac.report("Invalid agent id")
                    return self.disengage()
            except Exception as e:
                Jac.get_context().status = 400
                Jac.report("Invalid agent id")
                return self.disengage()
