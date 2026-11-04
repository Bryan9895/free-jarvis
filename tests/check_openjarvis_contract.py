"""Opt-in upstream contract check, with pinned source and controlled HTTP (no model)."""
import asyncio
import importlib.util
import json
import sys
import argparse
import subprocess
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
revision = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
assert revision == "324c9c3ac61bff07a0d99b715a7511dcd78600c4"
from unittest.mock import patch

sys.path.insert(0, str(args.source / "src"))
import httpx
import openjarvis.engine.ollama as upstream
assert Path(upstream.__file__).is_relative_to(args.source.resolve())
spec = importlib.util.spec_from_file_location('worker', str(Path(__file__).resolve().parents[1] / "src/jarvis/openjarvis_worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
requests, events = [], []
def handler(request):
    requests.append((request.url.path, json.loads(request.content) if request.content else None))
    if request.url.path == '/api/show':
        return httpx.Response(200, json={'capabilities': ['completion', 'tools']})
    return httpx.Response(200, text='\n'.join(map(json.dumps, [
        {'message': {'content': 'Texto completo sem ponto'}},
        {'message': {'tool_calls': [{'id': 'original-id', 'function': {'name': 'write_file',
            'arguments': {'path': 'proof.txt', 'content': 'ok'}}}]}},
        {'done': True, 'eval_count': 5, 'prompt_eval_count': 10}])))
transport = httpx.MockTransport(handler)
real_sync, real_async = httpx.Client, httpx.AsyncClient
def sync(**kwargs):
    return real_sync(**kwargs, transport=transport)
def async_client(**kwargs):
    return real_async(**kwargs, transport=transport)
with patch.object(httpx, 'Client', side_effect=sync), patch.object(httpx, 'AsyncClient', side_effect=async_client):
    engine = worker.create_engine('http://127.0.0.1:11434')
    with patch.object(worker, 'emit', side_effect=events.append):
        asyncio.run(worker.generate(engine, {'model': 'qwen3:1.7b', 'payload': {
            'instructions': 'pt-BR', 'input': [{'role': 'user', 'content': 'teste'}],
            'tools': [{'type': 'function', 'name': 'write_file', 'parameters': {'type': 'object'}}]}}))
    engine.close()
assert events[0]['delta'] == 'Texto completo sem ponto'
assert events[-1]['result']['output'][-1]['call_id'] == 'original-id'
assert json.loads(events[-1]['result']['output'][-1]['arguments'])['path'] == 'proof.txt'
assert requests[1][1]['tools'][0]['function']['name'] == 'write_file'
assert requests[1][1]['think'] is False
# Replay preserves the original structured ID on assistant and tool messages.
messages = worker.messages_from_payload({'input': [events[-1]['result']['output'][-1],
    {'type': 'function_call_output', 'call_id': 'original-id', 'output': '{"status":"verified"}'}]})
from openjarvis.engine._base import messages_to_dicts
converted = messages_to_dicts(messages)
assert converted[0]['tool_calls'][0]['id'] == converted[1]['tool_call_id'] == 'original-id'
# Upstream's default retry-without-tools is disabled by the pinned adapter.
failed_requests = []
def reject(request):
    failed_requests.append(request.url.path)
    if request.url.path == '/api/show':
        return httpx.Response(200, json={'capabilities': ['tools']})
    return httpx.Response(400, text='tools unsupported')
transport = httpx.MockTransport(reject)
with patch.object(httpx, 'Client', side_effect=sync), patch.object(httpx, 'AsyncClient', side_effect=async_client):
    engine = worker.create_engine('http://127.0.0.1:11434')
    try:
        with patch.object(worker, 'emit') as emit:
            try:
                asyncio.run(worker.generate(engine, {'model': 'qwen3:1.7b', 'payload': {
                    'input': 'teste', 'tools': [{'type': 'function', 'name': 'write_file',
                                               'parameters': {'type': 'object'}}]}}))
            except Exception as error:
                assert type(error).__name__ == 'EngineConnectionError'
            else:
                raise AssertionError('400 must remain a visible error')
            assert not emit.called
    finally:
        engine.close()
assert failed_requests == ['/api/show', '/api/chat']
print(json.dumps({'state': 'passed', 'revision': '324c9c3ac61bff07a0d99b715a7511dcd78600c4',
    'engine': upstream.__file__, 'requests': len(requests), 'structured_id_preserved': True,
    'inference': 'controlled HTTP transport, no real model'}))
