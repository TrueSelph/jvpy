from __future__ import annotations
from jaclang import *
from typing import Optional
from jivas.agent.memory.memory_walker import memory_walker
from jivas.agent.memory.memory import Memory

class add_frame(memory_walker, Walker):
    label: str = field("")
    user_name: str = field("")
    session_id: Optional[str] = field("")
    force_session: Optional[bool] = field(True)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_memory(self, here: Memory) -> None:
        frame_node = here.get_frame(
            agent_id=self.agent_id,
            user_name=self.user_name,
            label=self.label,
            session_id=self.session_id,
            force_session=self.force_session,
        )
        if not frame_node:
            Jac.get_context().status = 500
            Jac.report("unable to add frame node")
            return
        Jac.report(frame_node.export())
