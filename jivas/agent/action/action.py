from __future__ import annotations

import logging
from logging import Logger

from jaclang import *

from jivas.agent.core.graph_node import GraphNode


class Action(GraphNode, Node):

    version: str = field("")
    label: str = field("")
    description: str = field("basic agent action")
    enabled: bool = field(True)
    _package: dict = field(gen=lambda: {})
    agent_id: str = field("")
    logger: static[Logger] = logging.getLogger(__name__)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.protected_attrs += ["_package", "label", "version", "agent_id"]
        self.transient_attrs += ["agent_id"]

    def on_register(self) -> None:
        pass

    def post_register(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def on_deregister(self) -> None:
        pass

    def pulse(self) -> None:
        pass

    def analytics(self) -> None:
        pass

    def healthcheck(self) -> Union[bool, dict]:
        return True

    def update(self, data: dict = {}) -> GraphNode:
        if data:
            for attr in data.keys():
                if attr not in self.protected_attrs:
                    if hasattr(self, attr):
                        if attr == "enabled" and getattr(self, attr) != data[attr]:
                            if data[attr] == True:
                                self.on_enable()
                            else:
                                self.on_disable()
                        setattr(self, attr, data[attr])
                    else:
                        self._context[attr] = data[attr]
        self.get_agent().dump_descriptor()
        self.post_update()
        return self

    def get_agent(self) -> None:
        return jobj(id=self.agent_id)

    def get_namespace(self) -> None:
        return self._package.get("config", {}).get("namespace", None)

    def get_module(self) -> None:
        return self._package.get("config", {}).get("module", None)

    def get_module_root(self) -> None:
        return self._package.get("config", {}).get("module_root", None)

    def get_package_path(self) -> None:
        return self._package.get("config", {}).get("path", None)

    def get_version(self) -> None:
        return self.version

    def get_package_name(self) -> None:
        return self._package.get("config", {}).get("package_name", None)

    def get_namespace_package_name(self) -> None:
        return self._package.get("name", None)
