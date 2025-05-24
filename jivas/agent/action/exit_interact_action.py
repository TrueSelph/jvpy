from __future__ import annotations

from jaclang import *

from jivas.agent.action.interact_action import InteractAction
from jivas.agent.action.interact_graph_walker import interact_graph_walker


class ExitInteractAction(InteractAction, Node):
    label: str = field("ExitInteractAction")
    description: str = field("core exit action node for walker cleanup and return")
    weight: int = field(10000)

    def touch(self, visitor: interact_graph_walker) -> bool:
        return True

    def execute(self, visitor: interact_graph_walker) -> dict:
        return {}
