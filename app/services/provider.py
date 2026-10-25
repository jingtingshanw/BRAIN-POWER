"""模型抽象层（PRD §6.2）：换模型 = 改 .env，不动代码。
chat_with_tools / chat_stream 是唯一接口；支持跨厂商降级链（主 DeepSeek → 兜底 DashScope）。
"""
import json

from openai import OpenAI

from app.config import (
    FALLBACK_PROVIDER,
    MODEL_FALLBACK,
    MODEL_PRIMARY,
    MODEL_PROVIDER,
    provider_endpoint,
)


class Provider:
    def __init__(self):
        self.clients = {}
        self.chain = [
            (MODEL_PROVIDER, MODEL_PRIMARY),
            (FALLBACK_PROVIDER, MODEL_FALLBACK),
        ]
        self.model_used = ""

    def _client(self, provider_name: str) -> OpenAI:
        if provider_name not in self.clients:
            base_url, key = provider_endpoint(provider_name)
            self.clients[provider_name] = OpenAI(api_key=key, base_url=base_url)
        return self.clients[provider_name]

    def _call(self, messages, tools, stream: bool):
        """主模型失败自动降级（PRD E4），降级链支持跨厂商。"""
        last_err = None
        for provider_name, model in self.chain:
            try:
                kwargs = dict(model=model, messages=messages, stream=stream)
                if stream:
                    kwargs["stream_options"] = {"include_usage": True}
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                resp = self._client(provider_name).chat.completions.create(**kwargs)
                self.model_used = model
                return resp
            except Exception as e:  # noqa: BLE001 降级链
                last_err = e
                continue
        raise last_err  # type: ignore[misc]

    def chat_with_tools(self, messages, tools=None):
        resp = self._call(messages, tools, stream=False)
        usage = resp.usage
        return resp, {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }

    def parse_tool_calls(self, resp) -> list[dict]:
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            calls.append({"id": tc.id, "name": tc.function.name, "arguments": json.loads(tc.function.arguments or "{}")})
        return calls

    def chat_stream(self, messages, tools=None):
        """流式。返回 (token生成器, 最终结果dict含content/tool_calls/usage)。"""
        resp = self._call(messages, tools, stream=True)
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        def gen():
            for chunk in resp:
                if getattr(chunk, "usage", None):
                    usage["prompt_tokens"] = chunk.usage.prompt_tokens
                    usage["completion_tokens"] = chunk.usage.completion_tokens
                    usage["total_tokens"] = chunk.usage.total_tokens
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    content_parts.append(delta.content)
                    yield delta.content
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            slot["args"] += tc.function.arguments

        result = {"content": "", "tool_calls": [], "usage": usage}

        def finalize():
            result["content"] = "".join(content_parts)
            result["tool_calls"] = [
                {"id": s["id"] or f"call_{i}", "name": s["name"], "arguments": json.loads(s["args"] or "{}")}
                for i, s in sorted(tool_calls.items())
            ]
            return result

        return gen(), finalize
