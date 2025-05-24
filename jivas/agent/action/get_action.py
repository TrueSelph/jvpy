from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.core.agent import Agent
from jivas.agent.action.action import Action
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class get_action(interact_graph_walker, Walker):
    agent_id: str = field("")
    action_id: str = field("")
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Actions, None))

    @with_entry
    def on_actions(self, here: Actions) -> None:
        for action_node in here.get_all():
            if self.action_id == action_node.id:
                self.visit(action_node)

    @with_entry
    def on_action(self, here: Action) -> None:
        Jac.report(here.export())
