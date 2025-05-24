from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.core.agent import Agent
from jivas.agent.action.action import Action
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class list_actions(interact_graph_walker, Walker):
    agent_id: str = field('')
    actions: list = field(gen=lambda: JacList([]))
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False
        excluded: static[list] = JacList(['actions'])

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
        other_actions = JacList([action for action in self.actions if action.get('_package', {}).get('meta', {}).get('type', 'action') != 'interact_action' and action['label'] != 'ExitInteractAction'])
        interact_actions = JacList([action for action in self.actions if action.get('_package', {}).get('meta', {}).get('type', 'action') == 'interact_action' or action['label'] == 'ExitInteractAction'])
        self.actions = sorted(interact_actions, key=lambda action: int(action['weight'])) + other_actions
        Jac.report(self.actions)