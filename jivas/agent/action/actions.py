from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
import tarfile
import traceback
from logging import Logger
from typing import Union

import pkg_resources
import requests
import yaml
from jaclang import *
from jaclang import jac_import
from jvcli.api import RegistryAPI
from jvcli.utils import is_version_compatible
from jvserve.lib.agent_interface import AgentInterface

from jivas.agent.action.action import Action
from jivas.agent.action.exit_interact_action import ExitInteractAction
from jivas.agent.action.interact_action import InteractAction
from jivas.agent.core.graph_node import GraphNode
from jivas.agent.core.purge import purge
from jivas.agent.modules.agentlib.utils import Utils

JACLIST_REGEX = re.compile(r"JacList\(\[\s*.*?\s*\]\)", re.DOTALL)


class Actions(GraphNode, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    package_root: static[str] = Utils.get_actions_root()

    def get(
        self, action_label: str = "", action_type: str = "", only_enabled: bool = True
    ) -> Union[Action, list, None]:
        result = None
        if action_type and (not action_label):
            result = self.get_by_type(action_type, only_enabled)
        elif action_label and (not action_type):
            result = self.get_by_label(action_label, only_enabled)
        return result

    def get_by_label(self, action_label: str, only_enabled: bool = True) -> Action:
        actions = self.get_all(only_enabled=only_enabled)
        for action_node in actions:
            if action_node.label == action_label:
                return action_node
        return None

    def get_by_type(self, action_type: str, only_enabled: bool = True) -> list:
        result = []
        actions = self.get_all(only_enabled=only_enabled)
        for action_node in actions:
            if action_type == action_node.get_type():
                result.append(action_node)
        return result

    def get_all(
        self, only_interact_actions: bool = False, only_enabled: bool = False
    ) -> list:
        if only_interact_actions:
            return self.spawn(
                _get_interact_actions(filter_enabled=only_enabled)
            ).action_nodes
        return self.spawn(_get_actions(filter_enabled=only_enabled)).action_nodes

    def queue_interact_actions(self, actions: list) -> list:
        return sorted(actions, key=lambda action: action.weight)

    def get_action_info(
        self, namespace_package_name: str, version: str = None, jpr_api_key: str = None
    ) -> dict:
        action_info = {}
        namespace, package_name = namespace_package_name.split("/")
        if package_path := Utils.find_package_folder(
            self.package_root, namespace_package_name
        ):
            info_yaml_path = os.path.join(package_path, "info.yaml")
            try:
                with open(info_yaml_path, "r") as file:
                    _info = yaml.safe_load(file)
                    package_version = _info.get("package", {}).get("version", "~0.0.1")
                    if is_version_compatible(package_version, version):
                        self.logger.info(
                            f"{namespace_package_name} {package_version} loaded locally"
                        )
                        module_root = Utils.path_to_module(package_path)
                        has_app = os.path.isfile(
                            os.path.join(package_path, "app", "app.py")
                        )
                        action_info = _info["package"]
                        action_info["config"]["path"] = package_path
                        action_info["config"]["app"] = has_app
                        action_info["config"]["module_root"] = module_root
                        action_info["config"][
                            "module"
                        ] = f"{module_root}.{package_name}"
            except yaml.YAMLError as e:
                self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        if not action_info:
            if _info := RegistryAPI.get_package_info(
                namespace_package_name, version, api_key=jpr_api_key
            ):
                self.logger.info(
                    f"{namespace_package_name} {version} found in registry"
                )
                action_info = _info.get("package", None)
        if action_info:
            action_info["config"]["namespace"] = namespace
            action_info["config"]["package_name"] = package_name
        return action_info

    def import_action(self, action_data: dict) -> bool:
        module_root = (
            action_data.get("context", {})
            .get("_package", {})
            .get("config", {})
            .get("module_root", None)
        )
        if module_root:
            jac_import(f"{module_root}.lib", base_path="./")
            return True
        return False

    def register_action(self, action_data: dict, parent: str = "") -> Action:
        action_node = None
        if not action_data:
            self.logger.error(
                f"unable to register action {label}, missing or invalid action data"
            )
            return None
        label = action_data.get("context", {}).get(
            "label", action_data.get("action", None)
        )
        architype = (
            action_data.get("context", {}).get("_package", {}).get("architype", None)
        )
        module = (
            action_data.get("context", {})
            .get("_package", {})
            .get("config", {})
            .get("module", None)
        )
        singleton = (
            action_data.get("context", {})
            .get("_package", {})
            .get("config", {})
            .get("singleton", False)
        )
        action_type = (
            action_data.get("context", {})
            .get("_package", {})
            .get("meta", {})
            .get("type", "action")
        )
        if not architype or not module or (not label):
            self.logger.error(
                f"unable to register action {label}, missing label, architype or module name"
            )
            return None
        try:
            if singleton:
                if existing_action := self.get(action_type=label, only_enabled=False):
                    self.logger.error(f"action already exists: {label}")
                    return None
            elif existing_action := self.get(action_label=label, only_enabled=False):
                self.logger.error(f"action already exists: {existing_action.label}")
                return None
            action_node = AgentInterface.spawn_node(
                node_name=architype,
                attributes=action_data.get("context", {}),
                module_name=module,
            )
            if action_node:
                if not parent:
                    action_parent_node = self
                else:
                    action_parent_node = self.get_by_type(
                        action_type=parent, only_enabled=False
                    )
                action_parent_node.connect(action_node)
                action_node.on_register()
                self.logger.info(f"registered action: {action_node.label}")
            if "children" in action_data and action_type == "interact_action":
                for child_data in action_data["children"]:
                    self.register_action(action_data=child_data, parent=architype)
        except Exception as e:
            self.logger.error(
                f"an exception occurred wile registering action {label}, {traceback.format_exc()}"
            )

    def install_actions(
        self, agent_id: str, action_list: list, jpr_api_key: str = None
    ) -> bool:
        loaded_actions_data = None
        if agent_id:
            loaded_actions_data = self.load_actions(
                agent_id=agent_id, action_list=action_list, jpr_api_key=jpr_api_key
            )
        if not loaded_actions_data:
            self.logger.error("no actions loaded; unable to proceed with import")
            return False
        self.deregister_actions()
        for action_data in loaded_actions_data:
            self.register_action(action_data=action_data)
        self.connect(ExitInteractAction())
        for action_node in self.get_all():
            action_node.post_register()
        return True

    def deregister_action(self, action_type: str = "", action_label: str = "") -> None:
        target = []
        if action_type and (not action_label):
            target = self.get_by_type(action_type=action_type, only_enabled=False)
        elif action_label and (not action_type):
            target.append(
                self.get_by_label(action_label=action_label, only_enabled=False)
            )
        for action_node in target:
            action_node.on_deregister()
            action_node.spawn(purge())

    def deregister_actions(self) -> None:
        for action_node in self.get_all():
            action_node.on_deregister()
        self.spawn(purge(purge_spawn_node=False))
        Utils.jac_clean_actions()

    def search_action_list(
        self, namespace_package_name: str, action_list: list
    ) -> dict:
        for action_data in action_list:
            if action_data.get("action") == namespace_package_name:
                return action_data
        return {}

    def index_action_packages(
        self,
        agent_id: str,
        action_list: list,
        action_index: dict = {},
        jpr_api_key: str = "",
    ) -> dict:
        for action_data in action_list:
            namespace_package_name = action_data.get("action", None)
            is_not_indexed = namespace_package_name not in action_index.keys()
            package_version = action_data.get("context", {}).get("version", "~0.0.1")
            if is_not_indexed and namespace_package_name:
                if action_info := self.get_action_info(
                    namespace_package_name, package_version, jpr_api_key
                ):
                    action_data["context"]["agent_id"] = agent_id
                    action_data["context"]["_package"] = action_info
                    architype = action_info.get("architype", None)
                    action_data["context"]["label"] = action_data.get(
                        "context", {}
                    ).get("label", architype)
                    action_data["context"]["description"] = action_info.get(
                        "meta", {}
                    ).get("description", "")
                    if action_deps := action_info.get("dependencies", {}).get(
                        "actions", {}
                    ):
                        action_dep_list = []
                        for action_dep in action_deps.keys():
                            action_dep_version = action_deps[action_dep]
                            action_dep_list.append(
                                {
                                    "action": action_dep,
                                    "context": {
                                        "version": action_dep_version,
                                        "enabled": True,
                                    },
                                }
                            )
                        action_index = self.index_action_packages(
                            agent_id=agent_id,
                            action_list=action_dep_list,
                            action_index=action_index,
                            jpr_api_key=jpr_api_key,
                        )
                        if not all(
                            (key in action_index.keys() for key in action_deps.keys())
                        ):
                            continue
                    if "children" in action_data:
                        action_index = self.index_action_packages(
                            agent_id=agent_id,
                            action_list=action_data["children"],
                            action_index=action_index,
                            jpr_api_key=jpr_api_key,
                        )
                    if namespace_package_name not in action_index.keys():
                        action_index[namespace_package_name] = action_data
                else:
                    self.logger.error(
                        f"unable to find action {namespace_package_name} {package_version}"
                    )
        return action_index

    def index_pip_packages(self, action_data_index: dict) -> dict:
        pip_packages_index = {}
        for namespace_package_name, action_data in action_data_index.items():
            if (
                pip_packages := action_data.get("context", {})
                .get("_package", {})
                .get("dependencies", {})
                .get("pip", {})
            ):
                pip_packages_index.update(pip_packages)
        return pip_packages_index

    def batch_pip_package_install(self, packages: dict) -> None:
        package_specs = []
        for pkg, ver in packages.items():
            if not ver:
                package_specs.append(pkg)
            elif bool(re.match("^(==|>=|<=|>|<|~=|!=)", ver)):
                package_specs.append(f"{pkg}{ver}")
            else:
                package_specs.append(f"{pkg}=={ver}")
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-input"]
        command.extend(package_specs)
        self.logger.info(f"Attempting to install package dependencies: {package_specs}")
        try:
            subprocess.run(command, check=True, stderr=None, stdout=None)
            self.logger.info("Package dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            self.logger.error(
                "An error occurred while installing one or more package dependencies. There may be a conflict or a missing package."
            )

    def has_pip_package(self, package_name: str, version: str = None) -> bool:
        try:
            package_distribution = pkg_resources.get_distribution(package_name)
            if version is None:
                return True
            else:
                if not re.match("^(==|>=|<=|>|<|~=|!=)", version):
                    version = f"=={version}"
                return pkg_resources.parse_version(
                    package_distribution.version
                ) in pkg_resources.Requirement.parse(f"{package_name}{version}")
        except pkg_resources.DistributionNotFound:
            return False

    def has_pip_packages(self, packages: dict) -> bool:
        for pkg, ver in packages.items():
            if not self.has_pip_package(pkg, ver):
                return False
        return True

    def has_action_dependencies(
        self, action_data_index: dict, action_dependencies: dict
    ) -> bool:
        if not all(
            (key in action_data_index.keys() for key in action_dependencies.keys())
        ):
            return False
        return True

    def load_action_package(
        self, indexed_action_data: dict, jpr_api_key: str = ""
    ) -> dict:
        namespace_package_name = (
            indexed_action_data.get("context", {}).get("_package", {}).get("name")
        )
        package_version = indexed_action_data.get("context", {}).get(
            "version", "~0.0.1"
        )
        required_jivas_version = (
            indexed_action_data.get("context", {})
            .get("_package", {})
            .get("dependencies", {})
            .get("jivas", None)
        )
        package_path = (
            indexed_action_data.get("context", {})
            .get("_package", {})
            .get("config", {})
            .get("path", None)
        )
        jivas_version = Utils.get_jivas_version()
        if not is_version_compatible(jivas_version, required_jivas_version):
            self.logger.error(
                f"incompatible JIVAS version for: {namespace_package_name} ( required: {required_jivas_version}  system: {jivas_version} ) ...skipping"
            )
            return {}
        if package_path is None:
            package_data = RegistryAPI.download_package(
                namespace_package_name, package_version, api_key=jpr_api_key
            )
            if not package_data:
                self.logger.error(
                    f"unable to load action package: {namespace_package_name} {package_version} ...skipping"
                )
                return {}
            try:
                package_file = requests.get(package_data["file"])
                target_dir = os.path.join(self.package_root, namespace_package_name)
                os.makedirs(target_dir, exist_ok=True)
                with tarfile.open(
                    fileobj=io.BytesIO(package_file.content), mode="r:gz"
                ) as tar_file:
                    tar_file.extractall(target_dir)
                self.logger.info(
                    f"downloaded action package: {namespace_package_name} {package_version}"
                )
            except Exception as e:
                self.logger.error(
                    f"unable to save action package: {namespace_package_name}...skipping, {e}"
                )
                return {}
            if action_info := self.get_action_info(
                namespace_package_name, package_version, jpr_api_key
            ):
                indexed_action_data["context"]["_package"] = action_info
                if not action_info.get("config", {}).get("path", None):
                    self.logger.error(
                        f"unable to load action package: {namespace_package_name} {package_version}...skipping"
                    )
                    return {}
        return indexed_action_data

    def load_actions(
        self, agent_id: str, action_list: list, jpr_api_key: str = None
    ) -> list:
        action_data_index = self.index_action_packages(
            agent_id=agent_id, action_list=action_list, jpr_api_key=jpr_api_key
        )
        if not action_data_index:
            return []
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "--root-user-action=ignore",
            ]
        )
        indexed_pip_packages = self.index_pip_packages(action_data_index)
        self.batch_pip_package_install(indexed_pip_packages)
        action_data_index_copy = action_data_index.copy()
        for namespace_package_name, action_data in action_data_index_copy.items():
            loaded_action_data = self.load_action_package(
                indexed_action_data=action_data, jpr_api_key=jpr_api_key
            )
            if not loaded_action_data:
                del action_data_index[namespace_package_name]
                continue
            if not self.has_pip_packages(
                loaded_action_data.get("context", {})
                .get("_package", {})
                .get("dependencies", {})
                .get("pip", {})
            ):
                self.logger.error(
                    f"missing pip package dependencies for {namespace_package_name}...skipping"
                )
                del action_data_index[namespace_package_name]
                continue
            action_type = (
                loaded_action_data.get("context", {})
                .get("_package", {})
                .get("meta", {})
                .get("type", "action")
            )
            if "children" in loaded_action_data and action_type == "interact_action":

                def update_child_actions(child_action_list):
                    for i, child_action_data in enumerate(child_action_list):
                        action_type = (
                            child_action_data.get("context", {})
                            .get("_package", {})
                            .get("meta", {})
                            .get("type", "action")
                        )
                        if namespace_package_name := child_action_data.get(
                            "action", None
                        ):
                            if namespace_package_name in action_data_index:
                                child_action_list[i] = action_data_index[
                                    namespace_package_name
                                ]
                                del action_data_index[namespace_package_name]
                            if (
                                "children" in child_action_data
                                and action_type == "interact_action"
                            ):
                                update_child_actions(child_action_data["children"])

                update_child_actions(loaded_action_data["children"])
            action_data_index[namespace_package_name] = loaded_action_data
            action_deps = (
                loaded_action_data.get("context", {})
                .get("_package", {})
                .get("dependencies", {})
                .get("actions", {})
            )
            if not self.has_action_dependencies(action_data_index, action_deps):
                self.logger.error(
                    f"missing action dependencies for {namespace_package_name}...skipping"
                )
                del action_data_index[namespace_package_name]
                continue
            self.import_action(loaded_action_data)
        loaded_action_list = []
        for action_data in action_list:
            namespace_package_name = action_data.get("action")
            if loaded_action_data := action_data_index.get(namespace_package_name):
                action_entry = self.search_action_list(
                    namespace_package_name, action_list
                )
                loaded_action_data["context"].update(action_entry.get("context", {}))
                loaded_action_list.append(loaded_action_data)
                del action_data_index[namespace_package_name]
        loaded_action_list.extend(action_data_index.values())
        try:
            ordered_action_list = Utils.order_interact_actions(loaded_action_list)
            return ordered_action_list
        except Exception as e:
            self.logger.error(
                "A dependency conflict was detected among configured actions. Unordered actions will be loaded but functionality may be impaired."
            )
            return loaded_action_list


class _get_actions(Walker):
    action_nodes: list = field(gen=lambda: [])
    filter_enabled: bool = field(False)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_actions(self, here: Actions) -> None:
        if self.filter_enabled:
            self.visit(
                here.refs()
                .filter(Action, None)
                .filter(None, lambda item: item.enabled == True)
            )
        else:
            self.visit(here.refs().filter(Action, None))

    @with_entry
    def on_action(self, here: Action) -> None:
        self.action_nodes.append(here)
        self.visit(here.refs().filter(Action, None))


class _get_interact_actions(Walker):
    action_nodes: list = field(gen=lambda: [])
    filter_enabled: bool = field(False)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_actions(self, here: Actions) -> None:
        if self.filter_enabled:
            self.visit(
                here.refs()
                .filter(InteractAction, None)
                .filter(None, lambda item: item.enabled == True)
            )
        else:
            self.visit(here.refs().filter(InteractAction, None))

    @with_entry
    def on_action(self, here: InteractAction) -> None:
        self.action_nodes.append(here)
        self.visit(here.refs().filter(InteractAction, None))
