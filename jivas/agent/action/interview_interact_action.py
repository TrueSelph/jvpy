from __future__ import annotations
from jaclang import *
from enum import Enum, auto
import json
from typing import Union
from enum import unique
from openai import OpenAI
from jivas.agent.action.interact_action import InteractAction
from jivas.agent.action.interact_graph_walker import interact_graph_walker

class InterviewInteractAction(InteractAction, Node):
    model_action: str = field("LangChainModelAction")
    model_name: str = field("gpt-4o")
    model_max_tokens: int = field(4096)
    model_temperature: float = field(0.0)
    history: bool = field(True)
    history_size: int = field(1)
    max_statement_length: int = field(2048)
    auto_intents: bool = field(True)
    auto_confirm: bool = field(False)
    question_directive: str = field("Ask the question: '{question}'.")
    insist_response_directive: str = field(
        "Insist that a response is required then ask the question: '{question}'."
    )
    confirmation_directive: str = field(
        '\n    Perform the following steps to confirm user submission:\n        a. Summarize submission:\n            - Extract all user-provided submission details from:\n                {summary}\n            - Format them as a clear, bulleted list under the statement: "Here\'s what I\'ve recorded:"\n        b. Request Explicit Confirmation:\n            - Present the summary followed by:\n            "Are all details correct? Feel free to suggest changes or cancel altogether."\n    '
    )
    revision_directive: str = field(
        "Encourage the user to suggest any changes to the information provided."
    )
    extraction_prompt: str = field(
        "\n        Review the user's message and the conversation history to accurately extract the following entities.\n        Be strict on the constraints specified for each entity. Return a JSON object with keys exactly as listed below.\n        Include only keys for which you could extract a valid value adhering to all constraints.\n\n        Entities to extract:\n        {entities}\n\n        Return ONLY the JSON object with the extracted entities, no delimiters. Do not include any other text or explanation.\n        The JSON must have the following structure (only include keys with valid values):\n        {sample_json}\n        "
    )
    revision_extraction_prompt: str = field(
        "\n        Review the user's message and the recorded responses to accurately extract the following entities and update the relevant recorded responses.\n        Be strict on the constraints specified for each entity. Return a JSON object with keys exactly as listed below.\n        Include only keys for which you could extract a valid revised value adhering to all constraints.\n\n        Entities to extract:\n        {entities}\n\n        Recorded responses:\n        {responses}\n\n        Return ONLY the JSON object with the revised entities, no delimiters. Do not include any other text or explanation.\n        The JSON must have the following structure (only include keys with valid values):\n        {sample_json}\n        "
    )
    branch_choice_prompt: str = field(
        '\n        Analyze the conversation history above. Detect ONLY explicit signals for confirmation (yes/affirmative),\n        conversation termination (abort/stop), decline-to-answer (no answer/can\'t respond).\n        Follow these rules:\n\n        # Confirmation Detection\n        Set "confirm_response" to true for: "yes", "sure", "confirmed", "yeah", "yep", "absolutely", "okay" + clear context.\n        Set "confirm_response" to false ONLY for explicit negative or revision signals, including:\n            - Direct negatives: "no"\n            - Revision or correction requests: "I\'d like to make an adjustment", "need to make a change", "revision", "change my answer", "not correct", "incorrect", "needs update"\n            - Suggestions to edit or change: phrases like "actually, please change...", "no, can you change...", "can you update...", "please edit...", "I\'d like to change...", "can you correct...", "let\'s fix...", "could you modify...", or similar expressions indicating a desire to alter or correct previous information.\n        Do NOT set "confirm_response" to false for ambiguous, neutral, or indirect responses.\n\n        # Abort Detection\n        Set "abort_response" to true for: "stop", "cancel", "exit", "end chat", "nevermind", "abort", "terminate".\n        Do NOT include "abort_response" if not explicitly stated.\n\n        # Decline Detection\n        Set "decline_response" to true for: "no answer", "I don\'t know", "I have none", "no comment", "can\'t say", "nothing", "n/a", "decline to answer".\n        Do NOT include "decline_response" for partial answers, topic changes, or ambiguous non-responses.\n\n        Return ONLY a JSON structure with a single detected key (confirm_response, abort_response, decline_response) set to true,\n        or "confirm_response" set to false if a negative/revision is detected. If nothing is detected, return an empty JSON object. No delimiters!\n        Never include keys with false values except for "confirm_response" as described. No commentary. Never guess - ambiguous cases = empty JSON.\n        '
    )
    question_index: dict = field(gen=lambda: {})

    def setup(self) -> None:
        if self.auto_intents:
            self.generate_intents()

    def on_register(self) -> None:
        self.setup()

    def post_update(self) -> None:
        self.setup()

    def touch(self, visitor: interact_graph_walker) -> bool:
        has_intent = False
        if self.get_agent().get_action("IntentInteractAction"):
            has_intent = self.label in visitor.interaction_node.intents
        else:
            has_intent = True
        return has_intent and (visitor.utterance or visitor.data)

    def execute(self, visitor: interact_graph_walker) -> None:
        interview_session = self.init_session(visitor)
        self.process_response(interview_session, visitor)
        self.exit_session(interview_session, visitor)

    @abstract
    def process_response(self, visitor: interact_graph_walker) -> None:
        pass

    def init_session(self, visitor: interact_graph_walker) -> InterviewSession:
        interview_session = self.get_session(visitor)
        if not interview_session:
            interview_session = self.create_session(visitor)
        branch_choice_response = self.call_llm(
            self.branch_choice_prompt, visitor, json_only=True
        )
        if interview_session.get_state() in JacList(
            [SessionState.OPEN, SessionState.COMPLETED, SessionState.REVISION]
        ):
            if branch_choice_response.get("abort_response", False):
                interview_session.set_state(SessionState.ABORTED)
                visitor.interaction_node.add_event(
                    "User has chosen to abort the process."
                )
                return interview_session
        if branch_choice_response.get("decline_response", False):
            if interview_session.on_required_field():
                insist_directive = self.insist_response_directive.format(
                    question=self.get_next_question(interview_session)
                )
                visitor.interaction_node.add_directive(directive=insist_directive)
                return interview_session
            else:
                field = interview_session.get_next_field()
                question_response = {field: "n/a"}
                self.update_responses(question_response, interview_session)
                if not interview_session.get_next_field():
                    interview_session.set_state(SessionState.COMPLETED)
        if interview_session.get_state() == SessionState.COMPLETED:
            confirmed = branch_choice_response.get("confirm_response", None)
            if confirmed is True or self.auto_confirm:
                interview_session.set_state(SessionState.CONFIRMED)
                return interview_session
            elif confirmed is False:
                interview_session.set_state(SessionState.REVISION)
        if interview_session.get_state() == SessionState.OPEN:
            question_index = self.filter_question_index(interview_session)
            prompt = self.generate_extraction_prompt(question_index)
            question_responses = self.extract(prompt, question_index, visitor)
            self.update_responses(question_responses, interview_session)
            if not interview_session.get_next_field():
                if self.auto_confirm:
                    interview_session.set_state(SessionState.CONFIRMED)
                else:
                    interview_session.set_state(SessionState.COMPLETED)
        if interview_session.get_state() == SessionState.REVISION:
            prompt = self.generate_revision_extraction_prompt(interview_session)
            question_responses = self.extract(
                prompt=prompt,
                question_index=self.question_index,
                visitor=visitor,
                history=False,
            )
            if question_responses:
                self.update_responses(question_responses, interview_session)
                interview_session.set_state(SessionState.COMPLETED)
        if interview_session.get_state() == SessionState.COMPLETED:
            visitor.interaction_node.add_directive(
                directive=self.get_confirmation_directive(interview_session)
            )
            return interview_session
        if interview_session.get_state() == SessionState.REVISION:
            visitor.interaction_node.add_directive(directive=self.revision_directive)
        return interview_session

    def exit_session(
        self, interview_session: InterviewSession, visitor: interact_graph_walker
    ) -> None:
        self.update_session(interview_session, visitor)
        if interview_session.get_state() in JacList(
            [SessionState.ABORTED, SessionState.CONFIRMED]
        ):
            self.delete_session(visitor)
        if interview_session.get_state() in JacList(
            [SessionState.OPEN, SessionState.COMPLETED, SessionState.REVISION]
        ):
            visitor.set_resume_action(action_label="", action_node=self)

    def healthcheck(self) -> Union[bool, dict]:
        invalid_question_message = ""
        if isinstance(self.question_index, dict):
            for key, question_info in self.question_index.items():
                if (
                    not isinstance(question_info, dict)
                    or "question" not in question_info
                    or "constraints" not in question_info
                ):
                    valid_question_index = False
                    break
                c = question_info["constraints"]
                if not isinstance(c, dict):
                    invalid_question_message = (
                        f"constraints must be a dictionary. Hint: {key}"
                    )
                    break
                if "description" not in c or not isinstance(c["description"], str):
                    invalid_question_message = (
                        f"description must be a string. Hint: {key}"
                    )
                    break
                if "type" not in c or not isinstance(c["type"], str):
                    invalid_question_message = f"type must be a string. Hint: {key}"
                    break
                if "required" not in question_info or not isinstance(
                    question_info["required"], bool
                ):
                    invalid_question_message = (
                        f"required must be a boolean. Hint: {key}"
                    )
                    break
        if invalid_question_message:
            return {
                "status": False,
                "message": f"Malformed question index. Check your configuration and try again. Hint: {invalid_question_message}",
                "severity": "error",
            }
        return True

    def generate_intents(self) -> None:
        if not isinstance(self.question_index, dict):
            return JacList([])
        for field, item in self.question_index.items():
            description = item.get("constraints", {}).get("description", "")
            if not description:
                continue
            intent = f"MESSAGE is {description}"
            if intent not in self.anchors:
                self.anchors.append(intent)

    def create_session(self, visitor: interact_graph_walker) -> InterviewSession:
        all_fields = self.get_question_fields()
        required_fields = JacList(
            [
                key
                for key in all_fields
                if self.question_index[key].get("required", False)
            ]
        )
        interview_session = InterviewSession(
            all_fields=all_fields, required_fields=required_fields
        )
        interview_session.get_next_field()
        visitor.frame_node.variable_set(
            key=f"{self.get_type()}_session", value=interview_session.export()
        )
        return interview_session

    def delete_session(self, visitor: interact_graph_walker) -> None:
        visitor.frame_node.variable_del(key=f"{self.get_type()}_session")

    def update_session(
        self, interview_session: InterviewSession, visitor: interact_graph_walker
    ) -> None:
        visitor.frame_node.variable_set(
            key=f"{self.get_type()}_session", value=interview_session.export()
        )

    def get_question_fields(self) -> dict:
        return list(self.question_index.keys())

    def get_next_question(self, interview_session: InterviewSession) -> str:
        field = interview_session.get_next_field()
        return self.question_index.get(field, {}).get("question", "")

    def get_next_question_directive(self, interview_session: InterviewSession) -> str:
        return (
            self.question_directive.format(
                question=self.get_next_question(interview_session)
            )
            if (next_question := self.get_next_question(interview_session))
            else ""
        )

    def get_confirmation_directive(self, interview_session: InterviewSession) -> str:
        responses = interview_session.export().get("responses", {})
        if responses and isinstance(responses, dict) and (len(responses) > 0):
            summary_lines = JacList([])
            for field, value in responses.items():
                summary_lines.append(f"- **{field}**: {value}")
            responses = "\n".join(summary_lines)
        return self.confirmation_directive.format(
            summary=responses if responses else ""
        )

    def filter_question_index(self, interview_session: InterviewSession) -> list:
        if interview_session.get_state() == SessionState.OPEN:
            filtered_index = {}
            unanswered_fields = interview_session.get_unanswered_fields()
            for field, item in self.question_index.items():
                if field in unanswered_fields:
                    filtered_index[field] = item
            return filtered_index
        return self.question_index

    def get_session(self, visitor: interact_graph_walker) -> InterviewSession:
        interview_session_data = visitor.frame_node.variable_get(
            key=f"{self.get_type()}_session"
        )
        if interview_session_data and isinstance(interview_session_data, dict):
            state = interview_session_data.get("state", "OPEN")
            session_state = SessionState.OPEN
            if state == SessionState.COMPLETED.value:
                session_state = SessionState.COMPLETED
            elif state == SessionState.CONFIRMED.value:
                session_state = SessionState.CONFIRMED
            elif state == SessionState.REVISION.value:
                session_state = SessionState.REVISION
            elif state == SessionState.ABORTED.value:
                session_state = SessionState.ABORTED
            else:
                session_state = SessionState.OPEN
            return InterviewSession(
                state=session_state,
                all_fields=interview_session_data.get("all_fields", JacList([])),
                required_fields=interview_session_data.get(
                    "required_fields", JacList([])
                ),
                active_field=interview_session_data.get("active_field", ""),
                responses=interview_session_data.get("responses", {}),
            )
        return None

    def update_responses(
        self, responses: dict, interview_session: InterviewSession
    ) -> None:
        if type(responses) is not dict:
            return
        for field, response in responses.items():
            if field and response:
                interview_session.set_response(field, response)

    def generate_extraction_prompt(self, question_index: dict) -> str:
        entities_list = JacList([])
        sample_json_lines = JacList([])
        for key, details in question_index.items():
            constraints = details.get("constraints", {})
            if not constraints:
                continue
            desc = constraints.get("description", "")
            other_constraints = {
                k: v for k, v in constraints.items() if k != "description"
            }
            constraint_strs = JacList(
                [f"{k}: {v}" for k, v in other_constraints.items()]
            )
            constraint_part = (
                f" ({', '.join(constraint_strs)})" if constraint_strs else ""
            )
            entities_list.append(f"- {key}: {desc}{constraint_part}")
            sample_json_lines.append(f"  '{key}': '<extracted value>'")
        entities = "\n".join(entities_list)
        sample_json = "{\n" + ",\n".join(sample_json_lines) + "\n}"
        prompt = self.extraction_prompt.format(
            entities=entities, sample_json=sample_json
        )
        prompt = prompt.replace("{", "{{").replace("}", "}}")
        return prompt

    def generate_revision_extraction_prompt(
        self, interview_session: InterviewSession
    ) -> str:
        entities_list = JacList([])
        sample_json_lines = JacList([])
        for key, details in self.question_index.items():
            constraints = details.get("constraints", {})
            if not constraints:
                continue
            desc = constraints.get("description", "")
            other_constraints = {
                k: v for k, v in constraints.items() if k != "description"
            }
            constraint_strs = JacList(
                [f"{k}: {v}" for k, v in other_constraints.items()]
            )
            constraint_part = (
                f" ({', '.join(constraint_strs)})" if constraint_strs else ""
            )
            entities_list.append(f"- {key}: {desc}{constraint_part}")
            sample_json_lines.append(f"  '{key}': '<extracted value>'")
        responses = interview_session.export().get("responses", {})
        if responses and isinstance(responses, dict) and (len(responses) > 0):
            summary_lines = JacList([])
            for field, value in responses.items():
                summary_lines.append(f"- **{field}**: {value}")
            responses = "\n".join(summary_lines)
        entities = "\n".join(entities_list)
        sample_json = "{\n" + ",\n".join(sample_json_lines) + "\n}"
        prompt = self.revision_extraction_prompt.format(
            entities=entities, responses=responses, sample_json=sample_json
        )
        prompt = prompt.replace("{", "{{").replace("}", "}}")
        return prompt

    def extract(
        self,
        prompt: str,
        question_index: list,
        visitor: interact_graph_walker,
        history: Union[bool, None] = None,
    ) -> Union[dict, None]:
        return self.call_llm(prompt, visitor, history, json_only=True)

    def call_llm(
        self,
        prompt: str,
        visitor: interact_graph_walker,
        history: Union[bool, None] = None,
        json_only: bool = False,
    ) -> Union[str, dict, None]:
        prompt_messages = JacList([])
        if not prompt:
            return None
        use_history = self.history
        if history is not None:
            use_history = history
        if use_history:
            prompt_messages = JacList([])
            statements = visitor.frame_node.get_transcript_statements(
                interactions=self.history_size,
                max_statement_length=self.max_statement_length,
                with_events=True,
            )
            if statements:
                prompt_messages.extend(statements)
                self.logger.debug(f"history: {json.dumps(statements)}")
            prompt_messages.extend(JacList([{"system": prompt}]))
        else:
            prompt_messages = JacList(
                [{"system": prompt}, {"human": visitor.utterance}]
            )
        model_action = self.get_agent().get_action(action_label=self.model_action)
        if model_action:
            model_action_result = model_action.call_model(
                prompt_messages=prompt_messages,
                prompt_variables={},
                kwargs={
                    "model_name": self.model_name,
                    "model_temperature": self.model_temperature,
                    "model_max_tokens": self.model_max_tokens,
                },
                interaction_node=visitor.interaction_node,
            )
            if model_action_result:
                if json_only:
                    return model_action_result.get_json_result()
                else:
                    return model_action_result.get_result()
        return None


@unique
class SessionState(Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CONFIRMED = "CONFIRMED"
    REVISION = "REVISION"
    ABORTED = "ABORTED"


class InterviewSession(Obj):
    state: SessionState = field(gen=lambda: SessionState.OPEN)
    all_fields: list = field(gen=lambda: JacList([]))
    required_fields: list = field(gen=lambda: JacList([]))
    active_field: str = field("")
    responses: dict = field(gen=lambda: {})
    data: dict = field(gen=lambda: {})

    def get_state(self) -> SessionState:
        return self.state

    def set_state(self, state: SessionState) -> None:
        self.state = state

    def get_next_field(self) -> str:
        response_fields = self.responses.keys()
        for item in self.all_fields:
            if item not in response_fields:
                self.active_field = item
                return item
        return None

    def on_required_field(self) -> boolean:
        return self.get_next_field() in self.get_required_fields()

    def get_answered_fields(self) -> list:
        return list(self.responses.keys()) or JacList([])

    def get_unanswered_fields(self) -> list:
        return JacList(
            [
                field
                for field in self.all_fields
                if field not in self.get_answered_fields()
            ]
        )

    def get_required_fields(self) -> list:
        return self.required_fields

    def get_response(self, field: str) -> str:
        return self.responses.get(field, "")

    def set_response(self, field: str, response: str) -> None:
        self.responses[field] = response

    def get_data_item(self, label: str) -> any:
        return self.data.get(label, None)

    def set_data_item(self, label: str, value: any) -> None:
        self.data[label] = value

    def export(self) -> dict:
        return {
            "state": self.state.value,
            "all_fields": self.all_fields,
            "required_fields": self.required_fields,
            "active_field": self.active_field,
            "responses": self.responses,
        }
