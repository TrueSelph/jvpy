from __future__ import annotations
from jaclang import *
import io
import zipfile
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agent import Agent
from jivas.agent.modules.agentlib.utils import Utils

class export_daf(agent_graph_walker, Walker):
    clean: bool = field(False)
    with_knowledge: bool = field(True)
    with_memory: bool = field(False)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        daf_contents = {}
        daf_name = here.meta.get("namespace", "agent_daf")
        daf_info_yaml = Utils.yaml_dumps(here.get_daf_info())
        daf_descriptor_yaml = here.get_descriptor(as_yaml=True, clean=self.clean)
        if daf_info_yaml and daf_descriptor_yaml:
            daf_contents = {
                "info.yaml": daf_info_yaml,
                "descriptor.yaml": daf_descriptor_yaml,
            }
        else:
            Jac.get_context().status = 503
            Jac.report(
                "no valid daf info or descriptor generated, unable to complete export"
            )
            return self.disengage()
        if self.with_memory:
            daf_memory_data = here.get_memory().export_memory()
            if daf_memory_yaml := Utils.yaml_dumps(daf_memory_data):
                daf_contents["memory.yaml"] = daf_memory_yaml
            else:
                self.logger.error(
                    "Unable to export memory. It may be blank or there may be a YAML conversion issue."
                )
        if self.with_knowledge:
            daf_knowledge = JacList([])
            try:
                if vector_store_action := here.get_action(
                    action_label=here.get_vector_store_action()
                ):
                    if daf_knowledge_yaml := vector_store_action.export_knodes():
                        daf_contents["knowledge.yaml"] = daf_knowledge_yaml
                    else:
                        self.logger.error(
                            "Unable to export knowledge. It may be blank or there may be a YAML conversion issue."
                        )
            except Exception as e:
                Jac.get_context().status = 503
                error_message = f"Unable to export knowledge : {e}"
                self.logger.error(error_message)
                Jac.report(error_message)
                return self.disengage()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for fname, content in daf_contents.items():
                zipf.writestr(fname, content)
        daf_bytes = buffer.getvalue()
        daf_output_filename = f"dafs/{daf_name.replace('/', '_')}.daf.zip"
        if here.save_file(daf_output_filename, daf_bytes):
            Jac.get_context().status = 200
            Jac.report(here.get_file_url(daf_output_filename))
        else:
            Jac.get_context().status = 503
            error_message = "There was a problem generating the DAF"
            self.logger.error(error_message)
            Jac.report(error_message)
