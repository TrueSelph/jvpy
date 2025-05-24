from __future__ import annotations

from jaclang import *

from jivas.agent.modules.agentlib.utils import Utils


class Data(Obj):
    label: str = field("")
    meta: dict = field(gen=lambda: {})
    content: any = field("")

    def load(self, data: dict) -> None:
        if data:
            for attr in data.keys():
                if hasattr(self, attr):
                    setattr(self, attr, data[attr])

    def export(self, ignore_keys: list = ["__jac__"]) -> None:
        node_export = Utils.export_to_dict(self, ignore_keys)
        return node_export
