from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.modules.agentlib.utils import Utils
from jivas.agent.core.app import App

class graph_walker(Walker):
    reporting: bool = field(True)
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_root(self, here: Root) -> None:
        if not self.visit(here.refs().filter(App, None)):
            self.logger.error(
                "App graph not initialized. Import an agent and try again."
            )

    def export(self, ignore_keys: list = JacList(["__jac__"])) -> None:
        node_export = Utils.export_to_dict(self, ignore_keys)
        return node_export

    def update(self, data: dict = {}) -> graph_walker:
        if data:
            for attr in data.keys():
                if hasattr(self, attr):
                    self.attr = data[attr]
        self.post_update()
        return self

    def post_update(self) -> None:
        pass
