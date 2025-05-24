from __future__ import annotations

import logging
from logging import Logger

from jaclang import *

from jivas.agent.action.action import Action
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_graph_walker import interact_graph_walker
from jivas.agent.core.agent import Agent


class list_actions(interact_graph_walker, Walker):
    agent_id: str = field("")
    actions: list = field(gen=lambda: [])
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False
        excluded: static[list] = ["actions"]

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Actions, None))

    @with_entry
    def on_actions(self, here: Actions) -> None:
        self.visit(here.refs().filter(Action, None))

    @with_entry
    def on_action(self, here: Action) -> None:
        action_data = here.export()
        self.actions.append(action_data)
        self.visit(here.refs().filter(Action, None))

    @with_exit
    def on_exit(self, here) -> None:
        other_actions = [
            action
            for action in self.actions
            if action.get("_package", {}).get("meta", {}).get("type", "action")
            != "interact_action"
            and action["label"] != "ExitInteractAction"
        ]
        interact_actions = [
            action
            for action in self.actions
            if action.get("_package", {}).get("meta", {}).get("type", "action")
            == "interact_action"
            or action["label"] == "ExitInteractAction"
        ]
        self.actions = (
            sorted(interact_actions, key=lambda action: int(action["weight"]))
            + other_actions
        )
        Jac.report(self.actions)
