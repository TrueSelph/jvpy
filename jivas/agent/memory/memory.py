from __future__ import annotations

import logging
from datetime import datetime
from logging import Logger

from jaclang import *

from jivas.agent.core.graph_node import GraphNode
from jivas.agent.memory.frame import Frame
from jivas.agent.memory.interaction import Interaction
from jivas.agent.memory.retrace import Retrace
from jivas.agent.memory.tail import Tail
from jivas.agent.modules.agentlib.utils import Utils


class Memory(GraphNode, Node):
    logger: static[Logger] = logging.getLogger(__name__)

    def get_frame(
        self,
        agent_id: str,
        session_id: str,
        label: str = "",
        user_name: str = "",
        force_session: bool = False,
        lookup: bool = False,
    ) -> Frame:
        frame_node = Utils.node_obj(
            self.refs()
            .filter(Frame, None)
            .filter(None, lambda item: item.session_id == session_id)
        )
        if not frame_node and (not lookup):
            if force_session:
                frame_node = Frame(
                    agent_id=agent_id,
                    label=label,
                    user_name=user_name,
                    session_id=session_id,
                )
            else:
                frame_node = Frame(agent_id=agent_id, label=label, user_name=user_name)
            self.connect(frame_node)
        return frame_node

    def get_frames(self, session_id: str = "") -> list[Frame]:
        if session_id:
            return (
                self.refs()
                .filter(Frame, None)
                .filter(None, lambda item: item.session_id == session_id)
            )
        frames = self.refs().filter(Frame, None)
        return sorted(
            frames,
            key=lambda frame: (
                datetime.fromisoformat(frame.created_on)
                if hasattr(frame, "created_on") and frame.created_on
                else ""
            ),
            reverse=True,
        )

    def import_memory(self, data: dict, overwrite: bool = True) -> bool:
        if not data or not isinstance(data, dict):
            return False
        try:
            if overwrite:
                self.purge()
            agent_node = self.get_agent()
            for frame_data in data.get("memory"):
                if (
                    session_id := frame_data.get("frame", {})
                    .get("context", {})
                    .get("session_id", None)
                ):
                    frame_node = self.get_frame(
                        agent_id=agent_node.id,
                        session_id=session_id,
                        force_session=True,
                    )
                    frame_node.update(frame_data.get("frame", {}).get("context", {}))
                    interactions = frame_data.get("frame", {}).get("interactions", [])
                    for interaction_data in interactions:
                        last_interaction_node = frame_node.get_last_interaction()
                        interaction_node = Interaction(agent_id=agent_node.id)
                        if (
                            not interaction_data.get("interaction", {})
                            .get("context", {})
                            .get("response", {})
                            .get("session_id")
                        ):
                            interaction_data["interaction"]["context"]["response"][
                                "session_id"
                            ] = frame_node.session_id
                        interaction_node.update(
                            interaction_data.get("interaction", {}).get("context", {})
                        )
                        frame_node.insert_interaction(
                            interaction_node, last_interaction_node
                        )
                    self.logger.info(f"uploaded memory of: {frame_node.session_id}")
                else:
                    self.logger.error("invalid session ID on frame, skipping...")
            return True
        except Exception as e:
            self.logger.warning(f"uploaded memory failed: {e}")
        return False

    def export_memory(self, session_id: str = "") -> None:
        return self.spawn(_export_memory(session_id=session_id)).frame_data

    def memory_healthcheck(self, session_id: str = "") -> None:
        total_frames = 0
        total_interactions = 0
        frames = self.get_frames(session_id)
        total_frames = len(frames)
        for frame in frames:
            total_interactions += len(frame.get_interactions())
        return {"total_frames": total_frames, "total_interactions": total_interactions}

    def purge(self, session_id: str = None) -> None:
        return self.spawn(_purge(session_id)).removed

    def refresh(self, session_id: str) -> None:
        if frame_node := self.get_frame(None, session_id=session_id):
            frame_node.refresh_interactions()
            return True
        return False

    def get_agent(self) -> None:
        return Utils.node_obj(self.refs(dir=EdgeDir.IN))


class _purge(Walker):
    session_id: str = field("")
    removed: list = field(gen=lambda: [])

    class __specs__(Obj):
        private: static[bool] = True

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
        if not self.visit(here.refs(Tail)):
            self.removed.append(here)
            Jac.destroy(here)

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        self.visit(here.refs(Retrace))
        self.removed.append(here)
        Jac.destroy(here)


class _export_memory(Walker):
    logger: static[Logger] = logging.getLogger(__name__)
    session_id: str = field("")
    frame_data: dict = field(gen=lambda: {})

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_memory(self, here: Memory) -> None:
        self.frame_data = {"memory": []}
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
        interaction_data = []
        interactions = here.get_interactions()
        for interaction_node in interactions:
            interaction_data.append(
                {"interaction": {"context": interaction_node.export()}}
            )
        self.frame_data["memory"].append(
            {"frame": {"context": here.export(), "interactions": interaction_data}}
        )
