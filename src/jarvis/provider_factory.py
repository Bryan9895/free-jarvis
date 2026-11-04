"""Explicit provider selection shared by both interfaces; no cloud discovery."""
import os

from .fcc import AutoModelClient, FCCClient


def create_provider(config, *, initialize=True, on_switch=None):
    profile = getattr(config, 'profile', 'fcc')
    if profile == 'local':
        from .local_provider import OpenJarvisProvider
        client = OpenJarvisProvider(model=config.local_model, host=config.ollama_host,
                                    python=config.openjarvis_python)
    elif profile == 'fcc':
        client = AutoModelClient(FCCClient(config.url, config.token), preferred=config.model,
            backups=[x.strip() for x in os.getenv('FCC_FALLBACK_MODELS', '').split(',') if x.strip()],
            allow_cross_provider=os.getenv('FCC_ALLOW_CROSS_PROVIDER', '') == '1',
            on_switch=on_switch)
    else:
        raise ValueError('Perfil deve ser fcc ou local')
    if initialize:
        client.initialize()
    return client


def profile_registry(config):
    from .tools import DEFAULT_REGISTRY, offline_tool
    if getattr(config, 'profile', 'fcc') == 'local':
        from .registry import ToolRegistry
        registry = ToolRegistry()
        for spec in DEFAULT_REGISTRY.available_specs(DEFAULT_REGISTRY.capabilities):
            if offline_tool(DEFAULT_REGISTRY, spec['name']):
                entry = DEFAULT_REGISTRY.get(spec['name'])
                registry.register(entry.spec, entry.capability, entry.handler)
        return registry
    from .plugins import load_plugins
    return load_plugins(DEFAULT_REGISTRY, os.getenv('JARVIS_PLUGINS', ''))
