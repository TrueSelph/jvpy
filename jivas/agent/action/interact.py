from __future__ import annotations
from jaclang import *
import pytz
import json
import logging
import traceback
from typing import Optional
from logging import Logger
from jivas.agent.modules.agentlib.utils import Utils
from datetime import datetime, timezone, timedelta
from jivas.agent.action.actions import Actions
from jivas.agent.action.interact_action import InteractAction
from jivas.agent.memory.memory import Memory
from jivas.agent.memory.frame import Frame
from jivas.agent.memory.interaction import Interaction
from jivas.agent.memory.interaction_response import (
        InteractionResponse,
        InteractionMessage,
        SilentInteractionMessage,
    )
from jivas.agent.core.agent import Agent
from jac_cloud.core.architype import NodeAnchor
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class interact(interact_graph_walker, Walker):
    
    logger: static[Logger] = logging.getLogger(__name__)
    agent_id: str = field("")
    session_id: str = field("")
    utterance: str = field("")
    channel: str = field("default")
    data: list[dict] = field(gen=lambda: JacList([]))
    verbose: bool = field(False)
    tts: bool = field(False)
    streaming: bool = field(False)
    generator: any = field(None)
    response: dict = field(gen=lambda: {})
    message: InteractionMessage = field(None)
    execute: bool = field(False)
    context_data: dict = field(gen=lambda: {})
    frame_node: Frame = field(None)
    interaction_node: Interaction = field(None)
    agent_node: Agent = field(None)

    class __specs__(Obj):
        auth: static[bool] = True
        private: static[bool] = True
        excluded: static[list] = JacList(
            [
                "response",
                "message",
                "execute",
                "context_data",
                "frame_node",
                "interaction_node",
                "agent_node",
            ]
        )

    @with_entry
    def on_root(self, here: Root) -> None:
        if self.init_interaction():
            self.visit(self.agent_node)
        else:
            return self.disengage()

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Actions, None))

    @with_entry
    def on_actions(self, here: Actions) -> None:
        last_interaction_node = self.frame_node.get_last_interaction(retraces=2)
        if resume_action_node := self.frame_node.get_resume_action(
            last_interaction_node
        ):
            queued_interact_actions = here.queue_interact_actions(
                here.refs()
                .filter(InteractAction, None)
                .filter(None, lambda item: item.enabled == True)
            )
            root_action = resume_action_node.get_root_action()
            trimmed_queue = self.trim_interact_actions(
                index=root_action, interact_actions=queued_interact_actions
            )
            if trimmed_queue:
                self.interaction_node.add_intent(root_action.label)
                self.interaction_node.context_data["resumed"] = True
                self.visit(trimmed_queue)
            else:
                self.visit(queued_interact_actions)
        else:
            queued_actions = here.queue_interact_actions(
                here.refs()
                .filter(InteractAction, None)
                .filter(None, lambda item: item.enabled == True)
            )
            self.visit(queued_actions)

    @with_entry
    def on_action(self, here: InteractAction) -> None:
        result = {}
        intended = self.is_intended(here)
        has_access = self.has_access(here)
        has_function = self.has_function(here)
        if intended:
            if has_access:
                self.logger.debug(f"Touching: {here.label}")
                self.execute = here.touch(self)
                if self.execute:
                    self.logger.debug(f"Executing: {here.label}")
                    here.execute(self)
                    self.interaction_node.trail.append(here.label)
                    self.execute = False
            else:
                here.deny(self)

    @with_exit
    def on_exit(self, here) -> None:
        self.respond()

    def init_interaction(self) -> bool:
        try:
            self.agent_node = jobj(id=self.agent_id)
            if not self.agent_node:
                return False
        except Exception as e:
            Jac.get_context().status = 400
            self.logger.error("invalid agent id")
            return False
        self.frame_node = self.agent_node.get_memory().get_frame(
            agent_id=self.agent_node.id, session_id=self.session_id
        )
        if not self.frame_node:
            Jac.get_context().status = 500
            self.logger.error("unable to initiate a frame")
            return False
        if not self.is_valid_message_length(
            self.utterance, self.agent_node.message_limit
        ):
            Jac.get_context().status = 400
            self.logger.warning(
                "unable to process message; message length exceeds limit"
            )
            return False
        if self.is_flood_active():
            Jac.get_context().status = 429
            self.logger.warning(f"flood control active on {self.frame_node.session_id}")
            return False
        add_interaction = False
        self.interaction_node = self.frame_node.get_last_interaction()
        if self.interaction_node is None:
            add_interaction = True
        elif self.interaction_node.is_closed():
            add_interaction = True
        if add_interaction:
            self.interaction_node = self.frame_node.add_interaction(
                utterance=self.utterance, channel=self.channel
            )
        if not self.interaction_node:
            return False
        if self.data and isinstance(self.data, list):
            required_fields = JacList(["label", "meta", "content"])
            if all(JacList([isinstance(item, dict) for item in self.data])):
                for item in self.data:
                    if all(JacList([field in item for field in required_fields])):
                        self.interaction_node.set_data_item(
                            label=item["label"],
                            meta=item["meta"],
                            content=item["content"],
                        )
                    else:
                        Jac.get_context().status = 400
                        self.logger.error(
                            f"malformed data item; requires {required_fields} in each dictionary"
                        )
                        return False
            else:
                Jac.get_context().status = 400
                self.logger.error(
                    "data must be a list of dictionaries with required fields: 'label', 'meta', 'content'"
                )
                return False
        return True

    def is_valid_message_length(self, utterance: str, max_length: int) -> bool:
        chunks = Utils.chunk_long_message(
            message=utterance, max_length=max_length, chunk_length=max_length
        )
        if len(chunks) > 1:
            return False
        else:
            return True

    def is_flood_active(self) -> None:
        flood_control = self.agent_node.flood_control
        flood_block_time = self.agent_node.flood_block_time
        window_time = self.agent_node.window_time
        flood_threshold = self.agent_node.flood_threshold
        if flood_control:
            utc = pytz.UTC
            now = datetime.now(timezone.utc)
            flood = self.frame_node.variable_get(key="flood")
            if flood:
                expiration = flood["expiration"]
                if isinstance(expiration, str):
                    expiration = datetime.strptime(
                        expiration, "%Y-%m-%d %H:%M:%S.%f"
                    ).replace(tzinfo=utc)
                elif isinstance(expiration, datetime) and expiration.tzinfo is None:
                    expiration = expiration.replace(tzinfo=utc)
                if expiration > now:
                    return True
            message_window = self.frame_node.variable_get(key="message_window")
            if message_window:
                for key in JacList(["start", "end"]):
                    value = message_window.get(key)
                    if isinstance(value, str):
                        message_window[key] = datetime.strptime(
                            value, "%Y-%m-%d %H:%M:%S.%f"
                        ).replace(tzinfo=utc)
                    elif isinstance(value, datetime):
                        if value.tzinfo is None:
                            message_window[key] = value.replace(tzinfo=utc)
                        else:
                            message_window[key] = value
                if message_window.get("end", datetime.min.replace(tzinfo=utc)) <= now:
                    message_window["start"] = now
                    message_window["end"] = now + timedelta(seconds=window_time)
                    message_window["count"] = 0
                else:
                    message_window["count"] = message_window.get("count", 0) + 1
                if message_window.get("count", 0) > flood_threshold:
                    flood = {"expiration": now + timedelta(seconds=flood_block_time)}
                    self.frame_node.variable_set(key="flood", value=flood)
                    return True
                self.frame_node.variable_set(key="message_window", value=message_window)
            else:
                message_window = {
                    "start": now,
                    "end": now + timedelta(seconds=window_time),
                    "count": 1,
                }
                self.frame_node.variable_set(key="message_window", value=message_window)
            return False
        else:
            return False

    def set_next_action(
        self, action_label: str, action_node: Optional[InteractAction] = None
    ) -> None:
        next_action_node = None
        if action_label:
            next_action_node = self.agent_node.get_action(action_label=action_label)
        elif action_node:
            next_action_node = action_node
        if next_action_node:
            self.interaction_node.add_intent(next_action_node.label)
            self.prepend_interact_action(next_action_node)

    def set_resume_action(
        self, action_label: str, action_node: Optional[InteractAction] = None
    ) -> None:
        resume_action_label = None
        if action_label:
            resume_action_label = action_label
        elif action_node:
            resume_action_label = action_node.label
        if resume_action_label:
            self.frame_node.set_resume_action(action_label=resume_action_label)

    def append_action(
        self, action_label: str, action_node: Optional[InteractAction] = None
    ) -> None:
        append_action_node = None
        if action_label:
            append_action_node = self.agent_node.get_action(action_label=action_label)
        elif action_node:
            append_action_node = action_node
        if append_action_node:
            self.interaction_node.add_intent(append_action_node.label)
            self.append_interact_action(append_action_node)

    def dequeue_action(
        self, action_label: str, action_node: Optional[InteractAction] = None
    ) -> None:
        if action_label:
            action_node = self.agent_node.get_action(action_label=action_label)
        if action_node:
            self.dequeue_interact_action(action_node)

    def append_interact_action(self, interact_action: InteractAction) -> None:
        if exit_action := self.agent_node.get_action(action_label="ExitInteractAction"):
            exit_action_node_ref = None
            for i, node_ref in enumerate(self.__jac__.next):
                if f"{node_ref.id}" == f"{exit_action.__jac__.id}":
                    exit_action_node_ref = self.__jac__.next[i]
                    self.__jac__.next.pop(i)
                    break
            self.dequeue_interact_action(interact_action)
            self.visit(interact_action)
            self.__jac__.next.append(exit_action_node_ref)
            return self.__jac__.next
        else:
            self.visit(interact_action)
        return None

    def dequeue_interact_action(self, interact_action: InteractAction) -> None:
        if self.__jac__.next and interact_action:
            for i, node_ref in enumerate(self.__jac__.next):
                if f"{node_ref.id}" == f"{interact_action.__jac__.id}":
                    self.__jac__.next.pop(i)
                    break
            return self.__jac__.next
        return None

    def prepend_interact_action(self, interact_action: InteractAction) -> None:
        if self.dequeue_interact_action(interact_action):
            path = self.__jac__.next
            self.__jac__.next = JacList([])
            self.visit(interact_action)
            self.__jac__.next.extend(path)
            return self.__jac__.next
        return None

    def trim_interact_actions(
        self, index: InteractAction, interact_actions: list
    ) -> list:
        trimmed = JacList([])
        found = False
        for action in interact_actions:
            if not found and f"{action.id}" == f"{index.id}":
                found = True
            if found:
                trimmed.append(action)
        return trimmed

    def has_access(self, action_node: Action) -> bool:
        access = True
        if action_node.get_type() in JacList(
            ["AccessControlAction", "ExitInteractAction"]
        ):
            return True
        if access_control_action_node := self.agent_node.get_action(
            action_label="AccessControlAction"
        ):
            access = access_control_action_node.has_action_access(
                session_id=self.frame_node.session_id,
                action_label=action_node.get_type(),
                channel=self.interaction_node.channel or "default",
            )
        return access

    def has_function(self, action_node: InteractAction) -> bool:
        if action_node.get_type() in JacList(
            ["IntentInteractAction", "FunctionInteractAction", "ExitInteractAction"]
        ):
            return True
        if function_interact_action_node := self.agent_node.get_action(
            action_label="FunctionInteractAction"
        ):
            if (
                function_interact_action_node.enabled
                and function_interact_action_node.strict
            ):
                if (
                    action_node.label
                    not in self.interaction_node.get_intents()
                    + function_interact_action_node.exceptions
                ):
                    return False
        return True

    def is_intended(self, action_node: InteractAction) -> bool:
        if action_node.get_type() in JacList(
            ["IntentInteractAction", "FunctionInteractAction", "ExitInteractAction"]
        ):
            return True
        if intent_interact_action_node := self.agent_node.get_action(
            action_label="IntentInteractAction"
        ):
            if (
                intent_interact_action_node.enabled
                and intent_interact_action_node.strict
            ):
                if (
                    action_node.label
                    not in self.interaction_node.get_intents()
                    + intent_interact_action_node.exceptions
                ):
                    return False
        return True

    def respond(self) -> None:
        if self.agent_node and self.interaction_node:
            interaction_data = {}
            has_response = self.interaction_node.has_response()
            if has_response:
                try:
                    self.message = self.interaction_node.get_message()
                    interaction_data = self.interaction_node.export()
                    if self.verbose:
                        interaction_data["frame"] = self.frame_node.export()
                        self.response = interaction_data
                    else:
                        self.response = {
                            "response": self.interaction_node.get_response().export()
                        }
                    if self.agent_node.is_logging():
                        self.log_interaction(data=interaction_data)
                except Exception as e:
                    self.logger.error(
                        f"an exception occurred, {traceback.format_exc()}"
                    )
            if not has_response or not self.response:
                self.message = SilentInteractionMessage()
                self.response = InteractionResponse(
                    session_id=self.frame_node.session_id, message=self.message.export()
                ).export()
            self.frame_node.prune_interactions(frame_size=self.agent_node.frame_size)
            self.interaction_node.close()
        else:
            self.message = SilentInteractionMessage()
            self.response = InteractionResponse(message=self.message.export()).export()
        if self.tts:
            if tts_action := self.agent_node.get_tts_action():
                content = (
                    self.message.get_meta("phoneme_content")
                    or self.message.get_content()
                )
                audio = tts_action.invoke(text=content, as_url=True)
                if audio:
                    self.response["response"].update({"audio_url": audio})
        if self.reporting:
            Jac.report(self.response)

    def log_interaction(self, data: dict) -> None:
        collection = NodeAnchor.Collection.get_collection("interactions")
        collection.insert_one(json.loads(json.dumps(data)))
