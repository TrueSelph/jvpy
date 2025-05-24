from __future__ import annotations

from jaclang import *

from jivas.agent.action.action import Action
from jivas.agent.action.interact_graph_walker import interact_graph_walker


class InteractAction(Action, Node):
    anchors: list = field(gen=lambda: [])
    functions: list = field(gen=lambda: [])
    weight: int = field(0)

    @abstract
    def touch(self, visitor: interact_graph_walker) -> bool:
        pass

    @abstract
    def execute(self, visitor: interact_graph_walker) -> dict:
        pass

    def deny(self, visitor: interact_graph_walker) -> dict:
        pass

    def get_children(self) -> None:
        return self.refs().filter(Action, None)

    def get_root_action(self) -> None:
        return self.spawn(_get_root_action()).root_action


class _get_root_action(Walker):
    root_action: InteractAction = field(None)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_action(self, here: InteractAction) -> None:
        if not self.visit(here.refs(dir=EdgeDir.IN).filter(InteractAction, None)):
            self.root_action = here
