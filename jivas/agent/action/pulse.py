from __future__ import annotations
from jaclang import *
from jivas.agent.core.agent import Agent
from jivas.agent.action.action import Action
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class pulse(interact_graph_walker, Walker):
    action_label: str = field("")
    agent_id: str = field("")

    class __specs__(Obj):
        auth: static[bool] = True

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Actions, None))

    @with_entry
    def on_actions(self, here: Actions) -> None:
        self.visit(
            here.refs()
            .filter(Action, None)
            .filter(None, lambda item: item.enabled == True)
            .filter(None, lambda item: item.label == self.action_label)
        )

    @with_entry
    def on_action(self, here: Action) -> None:
        here.pulse()
