from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.core.agent import Agent
from jivas.agent.action.action import Action
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class update_action(interact_graph_walker, Walker):
    agent_id: str = field("")
    action_id: str = field("")
    action_data: dict = field(gen=lambda: {})
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Actions, None))

    @with_entry
    def on_actions(self, here: Actions) -> None:
        self.visit(
            here.refs()
            .filter(Action, None)
            .filter(None, lambda item: item.id == self.action_id)
        )

    @with_entry
    def on_action(self, here: Action) -> None:
        if action_node := here.update(data=self.action_data):
            Jac.report(action_node.export())
