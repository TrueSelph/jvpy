from __future__ import annotations

import logging
import traceback
from logging import Logger

from jaclang import *

from jivas.agent.core.agent import Agent
from jivas.agent.core.agent_graph_walker import agent_graph_walker


class install_action(agent_graph_walker, Walker):
    reporting: bool = field(False)
    override_action: bool = field(True)
    package_name: str = field("")
    version: str = field("")
    jpr_api_key: str = field("")
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        action_exists = False
        descriptor_data = here.get_descriptor()
        if not descriptor_data:
            message = "unable to load descriptor data"
            self.logger.error(message)
            Jac.get_context().status = 500
            Jac.report(message)
            return False
        dep_action_info = here.get_actions().get_action_info(
            namespace_package_name=self.package_name,
            version=self.version,
            jpr_api_key=self.jpr_api_key,
        )
        if not dep_action_info:
            message = f"unable to locate action {self.package_name} {self.version}"
            self.logger.error(message)
            Jac.get_context().status = 403
            Jac.report(message)
            return False
        try:
            action_info = {
                "action": dep_action_info.get("name"),
                "context": {"version": dep_action_info.get("version"), "enabled": True},
            }
            for action in descriptor_data["actions"]:
                if action["action"] == self.package_name:
                    if self.override_action:
                        action["context"] = action_info["context"]
                        here.get_actions().deregister_action(
                            action_label=action.get("context", {}).get("label", "")
                        )
                    else:
                        action["context"]["version"] = action_info["context"]["version"]
                    action_exists = True
                    break
            if not action_exists:
                descriptor_data["actions"].append(action_info)
            if here.update(
                data=descriptor_data, with_actions=True, jpr_api_key=self.jpr_api_key
            ):
                message = f"{self.package_name} {self.version} installed successfully"
                self.logger.info(message)
                Jac.get_context().status = 200
                Jac.report(message)
                return True
            else:
                message = f"unable to install action {self.package_name} {self.version}"
                self.logger.error(message)
                Jac.get_context().status = 500
                Jac.report(message)
                return False
        except Exception as e:
            message = f"unable to complete operation, {traceback.format_exc()}"
            self.logger.error(message)
            Jac.get_context().status = 500
            Jac.report(message)
            return False
