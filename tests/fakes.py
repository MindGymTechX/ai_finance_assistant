"""Scripted fake chat model: no network, no API key."""
from langchain_core.messages import AIMessage


class FakeLLM:
    def __init__(self, responses=None, structured=None):
        self.responses = list(responses or [])      # AIMessages for .invoke
        self.structured = structured or {}          # schema name -> list of instances
        self.calls = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0) if self.responses else AIMessage(content="(fake answer)")

    def with_structured_output(self, schema, **kwargs):
        llm = self

        class _S:
            def invoke(self, messages):
                q = llm.structured.get(schema.__name__, [])
                if not q:
                    raise ValueError(f"no scripted {schema.__name__}")
                item = q.pop(0)
                return item if not isinstance(item, dict) else schema.model_validate(item)
        return _S()


def tool_call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])
