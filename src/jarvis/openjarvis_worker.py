"""Private JSON-lines worker, launched with the provisioned Python 3.10–3.13.

Uses OpenJarvis under Apache-2.0 as an installed dependency, without copying its
implementation. Never instantiates its agents/tools or uses engine discovery
or cloud fallback. The Ollama engine class is selected directly.
"""
import asyncio
import importlib.metadata
import json
import sys
import uuid


def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def verify_revision(revision):
    try:
        origin = json.loads(importlib.metadata.distribution('openjarvis').read_text('direct_url.json') or '{}')
    except (importlib.metadata.PackageNotFoundError, ValueError):
        origin = {}
    if (origin.get('vcs_info', {}).get('commit_id') != revision
            or origin.get('url') != 'https://github.com/open-jarvis/OpenJarvis.git'):
        raise ValueError('Instale OpenJarvis na revisão fixada em um Python 3.10–3.13 isolado; veja README')


def check_model(engine, model, *, tools=False):
    if ':cloud' in model.lower() or '/' in model:
        raise ValueError('Modelo remoto bloqueado no perfil Local')
    response = engine._client.post('/api/show', json={'model': model})
    response.raise_for_status()
    data = response.json()
    if (data.get('remote_host') or data.get('remote_model')
            or ':cloud' in str(data.get('modelfile', '')).lower()):
        raise ValueError('O Ollama informou roteamento remoto; bloqueado no perfil Local')
    if tools and 'tools' not in data.get('capabilities', []):
        raise ValueError('O modelo local não anuncia suporte a ferramentas estruturadas')


def messages_from_payload(payload):
    from openjarvis.core.types import Message, Role, ToolCall
    messages = []
    if payload.get('instructions'):
        messages.append(Message(role=Role.SYSTEM, content=payload['instructions']))
    items = payload.get('input', [])
    if isinstance(items, str):
        items = [{'role': 'user', 'content': items}]
    for item in items:
        kind = item.get('type')
        if kind == 'function_call':
            messages.append(Message(role=Role.ASSISTANT, tool_calls=[ToolCall(
                id=item['call_id'], name=item['name'], arguments=item['arguments'])]))
        elif kind == 'function_call_output':
            messages.append(Message(role=Role.TOOL, content=item['output'], tool_call_id=item['call_id']))
        else:
            content = item.get('content', '')
            if isinstance(content, list):
                if any(p.get('type') not in ('input_text', 'output_text', 'text') for p in content):
                    raise ValueError('Visão ainda não foi validada no perfil Local')
                content = '\n'.join(p.get('text', '') for p in content)
            messages.append(Message(role=Role(item.get('role', 'user')), content=content))
    return messages


async def generate(engine, request):
    payload, model = request['payload'], request['model']
    tools = [{'type': 'function', 'function': {k: t[k] for k in
              ('name', 'description', 'parameters') if k in t}} for t in payload.get('tools', [])]
    check_model(engine, model, tools=bool(tools))
    messages = messages_from_payload(payload)
    text, calls, usage, finish = [], [], {}, None
    async for chunk in engine.stream_full(messages, model=model, tools=tools,
            max_tokens=payload.get('max_output_tokens', 1536), num_ctx=4096, num_gpu=0, think=False):
        if chunk.content:
            text.append(chunk.content)
            emit({'delta': chunk.content})
        for call in chunk.tool_calls or []:
            function = call['function']
            # Ollama's stream_full surface emits complete calls, not JSON fragments.
            arguments = function['arguments']
            if not isinstance(json.loads(arguments), dict):
                raise ValueError('Argumentos de ferramenta devem ser um objeto JSON completo')
            calls.append({'type': 'function_call', 'call_id': call.get('id') or uuid.uuid4().hex,
                          'name': function['name'], 'arguments': arguments})
        if chunk.usage:
            usage = chunk.usage
        if chunk.finish_reason:
            finish = chunk.finish_reason
    if finish not in ('stop', 'tool_calls'):
        raise ValueError('Resposta local incompleta; nenhuma chamada desta rodada foi executada')
    output = []
    if text:
        output.append({'type': 'message', 'role': 'assistant',
                       'content': [{'type': 'output_text', 'text': ''.join(text)}]})
    output.extend(calls)
    emit({'result': {'output': output, 'usage': usage, 'model': model}})


def create_engine(host):
    import httpx
    from openjarvis.engine.ollama import OllamaEngine

    class LocalEngine(OllamaEngine):
        def _make_async_client(self):
            return httpx.AsyncClient(base_url=self._host, timeout=self._timeout,
                                     trust_env=False, follow_redirects=False)

        async def _run_stream(self, payload, messages, *, retry_without_tools):
            # A tool failure must remain visible; disable upstream's 400 retry.
            async for chunk in super()._run_stream(payload, messages, retry_without_tools=False):
                yield chunk

    engine = LocalEngine(host=host, timeout=120)
    engine._client.close()
    engine._client = httpx.Client(base_url=host, timeout=10,
                                  trust_env=False, follow_redirects=False)
    return engine


def main():
    request = json.loads(sys.stdin.readline())
    verify_revision(request['revision'])
    if request['operation'] == 'inspect':
        from openjarvis.engine.ollama import OllamaEngine
        emit({'result': {'revision': request['revision'], 'engine': OllamaEngine.engine_id,
            'python_version': list(sys.version_info[:3]),
            'package_version': importlib.metadata.version('openjarvis'), 'inference': 'Não testado'}})
        return
    engine = create_engine(request['host'])
    try:
        operation = request['operation']
        emit({'ready': True})
        if operation == 'models':
            if not engine.health():
                raise ValueError('Ollama local indisponível; instale/inicie o servidor antes de selecionar pesos')
            emit({'result': engine.list_models()})
        elif operation == 'check':
            check_model(engine, request['model'])
            emit({'result': True})
        elif operation == 'identity':
            check_model(engine, request['model'])
            response = engine._client.get('/api/tags')
            response.raise_for_status()
            model = request['model']
            canonical = model if ':' in model else model + ':latest'
            entry = next(item for item in response.json()['models']
                         if item.get('name') == canonical or item.get('model') == canonical)
            import re
            if not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', entry.get('digest', '')):
                raise ValueError('Digest do modelo ausente ou inválido')
            emit({'result': {'model': canonical, 'digest': entry['digest'], 'size': entry.get('size')}})
        elif operation == 'unload':
            check_model(engine, request['model'])
            response = engine._client.post('/api/generate', json={'model': request['model'], 'keep_alive': 0})
            response.raise_for_status()
            response = engine._client.get('/api/ps')
            response.raise_for_status()
            canonical = request['model'] if ':' in request['model'] else request['model'] + ':latest'
            if any(item.get('name') == canonical for item in response.json()['models']):
                raise ValueError('Modelo ainda residente após descarga; carga fria não comprovada')
            emit({'result': True})
        elif operation == 'generate':
            asyncio.run(generate(engine, request))
        else:
            raise ValueError('Operação local desconhecida')
    finally:
        engine.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No upstream response bodies, prompts, credentials or private tool outputs.
        message = str(exc) if isinstance(exc, ValueError) else 'Motor local indisponível: ' + type(exc).__name__
        emit({'error': message})
