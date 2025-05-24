from __future__ import annotations

from jaclang import *

from jivas.agent.memory.memory import Memory
from jivas.agent.memory.memory_walker import memory_walker


class update_frame(memory_walker, Walker):
    session_id: str = field("")
    label: str = field("")
    user_name: str = field("")

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_memory(self, here: Memory) -> None:
        if not self.session_id:
            Jac.get_context().status = 400
            Jac.report("missing session_id")
            return
        if not self.label or self.user_name:
            Jac.get_context().status = 400
            Jac.report("nothing supplied to update frame")
            return
        frame_node = here.get_frame(agent_id=self.agent_id, session_id=self.session_id)
        if not frame_node:
            Jac.get_context().status = 500
            Jac.report("unable to update frame node")
            return
        frame_node.set_label(self.label)
        frame_node.set_user_name(self.user_name)
        frame_node.update()
        Jac.report(frame_node.export())
