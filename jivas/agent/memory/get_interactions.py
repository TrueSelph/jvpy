from __future__ import annotations

from jaclang import *

from jivas.agent.memory.advance import Advance
from jivas.agent.memory.frame import Frame
from jivas.agent.memory.interaction import Interaction
from jivas.agent.memory.memory import Memory
from jivas.agent.memory.memory_walker import memory_walker


class get_interactions(memory_walker, Walker):
    session_id: str = field("")

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_memory(self, here: Memory) -> None:
        if self.session_id:
            self.visit(
                here.refs()
                .filter(Frame, None)
                .filter(None, lambda item: item.session_id == self.session_id)
            )
        else:
            self.visit(here.refs().filter(Frame, None))

    @with_entry
    def on_frame(self, here: Frame) -> None:
        self.visit(here.refs(Advance).filter(Interaction, None))

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        Jac.report(here.export())
        self.visit(here.refs(Advance).filter(Interaction, None))
