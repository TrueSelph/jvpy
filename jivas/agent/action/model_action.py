from __future__ import annotations

import logging
import traceback
from logging import Logger
from typing import Optional, Union

from jaclang import *

from jivas.agent.action.action import Action
from jivas.agent.memory.interaction import Interaction
from jivas.agent.modules.agentlib.utils import Utils


class ModelAction(Action, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    api_key: str = field("")
    model_name: str = field("gpt-4o")
    model_temperature: float = field(0.7)
    model_max_tokens: int = field(2048)

    @abstract
    def invoke(
        self, prompt_messages: list, prompt_variables: dict, kwargs: dict = {}
    ) -> Optional[ModelActionResult]:
        pass

    def call_model(
        self,
        prompt_messages: list,
        prompt_variables: dict,
        interaction_node: Optional[Interaction] = None,
        logging: bool = False,
        streaming: bool = False,
        kwargs: dict = {},
    ) -> Optional[ModelActionResult]:
        kwargs.update({"streaming": streaming})
        if model_action_result := self.invoke(
            prompt_messages, prompt_variables, kwargs
        ):
            if interaction_node:
                if "ModelActionResult" not in interaction_node.context_data:
                    interaction_node.context_data["ModelActionResult"] = []
                interaction_node.context_data["ModelActionResult"].append(
                    model_action_result.export()
                )
                interaction_node.add_tokens(model_action_result.get_tokens())
            if logging:
                self.logger.warning(model_action_result.get_result())
            return model_action_result
        return None

    def healthcheck(self) -> Union[bool, dict]:
        if self.model_name == "" or self.api_key == "":
            return False
        test_prompt_messages = [{"system": "Output the result of 2 + 2"}]
        test_kwargs = {
            "model_name": self.model_name,
            "model_temperature": self.model_temperature,
            "model_max_tokens": self.model_max_tokens,
        }
        try:
            if model_action_result := self.call_model(
                prompt_messages=test_prompt_messages,
                prompt_variables={},
                kwargs=test_kwargs,
            ):
                interaction_message = model_action_result.get_result()
                if not interaction_message:
                    return False
                else:
                    return True
            return False
        except Exception as e:
            self.logger.error(
                f"An exception occurred in {self.label}:\\n{traceback.format_exc()}\\n"
            )
            return False


class ModelActionResult(Obj):
    prompt: str = field("")
    functions: str = field("")
    result: str = field("")
    generator: any = field(None)
    tokens: int = field(0)
    temperature: float = field(0)
    model_name: str = field("")
    max_tokens: int = field(0)
    meta: dict = field(gen=lambda: {})

    def get_prompt(self) -> None:
        return self.prompt

    def get_functions(self) -> None:
        return self.functions

    def get_result(self) -> None:
        if self.result:
            return self.result
        else:
            return None

    def get_json_result(self) -> None:
        if json_result := Utils.convert_str_to_json(self.result):
            return json_result
        else:
            return {}

    def get_tokens(self) -> None:
        return self.tokens

    def get_max_tokens(self) -> None:
        return self.max_tokens

    def get_temperature(self) -> None:
        return self.temperature

    def get_model_name(self) -> None:
        return self.model_name

    def get_meta(self) -> None:
        return self.meta

    def get_generator(self) -> None:
        return self.generator

    def export(self, ignore_keys: list = ["__jac__"]) -> None:
        node_export = Utils.export_to_dict(self, ignore_keys)
        return node_export
