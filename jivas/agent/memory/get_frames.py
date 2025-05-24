from __future__ import annotations

from jaclang import *

from jivas.agent.memory.memory import Memory
from jivas.agent.memory.memory_walker import memory_walker


class get_frames(memory_walker, Walker):
    session_id: str = field("")

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_memory(self, here: Memory) -> None:
        frame_nodes = here.get_frames(self.session_id)
        for frame_node in frame_nodes:
            Jac.report(frame_node.export())
