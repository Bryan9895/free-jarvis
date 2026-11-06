"""Prepare a provider before replacing the idle GUI session."""
from dataclasses import replace
import os


def switch_profile(backend, changes):
    from contextlib import nullcontext
    with getattr(backend, '_settings_lock', nullcontext()):
        return _switch_profile(backend, changes)


def _switch_profile(backend, changes):
    from .registry import CapabilityPolicy
    if not isinstance(changes, dict) or changes.keys() - {'profile', 'model'}:
        raise ValueError('Seleção de perfil inválida')
    profile = changes.get('profile')
    if profile not in ('local', 'fcc'):
        raise ValueError('Escolha Local ou Engenharia FCC')
    if os.getenv('JARVIS_PROFILE', profile) != profile:
        raise ValueError('JARVIS_PROFILE explícito prevalece; ajuste o ambiente antes de trocar o perfil')
    old = backend.service
    if old is not None and old._lock.locked():
        raise RuntimeError('Pare o turno atual antes de trocar o perfil')
    saved = backend.preference_store.load()
    if backend.preference_store.error:
        raise ValueError('Corrija as preferências antes de trocar o perfil')
    key = 'local_model' if profile == 'local' else 'conversation_model'
    supplied = changes.get('model', '')
    if not isinstance(supplied, str):
        raise ValueError('Modelo inválido')
    model = supplied.strip() or getattr(saved, key)
    variable = 'JARVIS_LOCAL_MODEL' if profile == 'local' else 'FCC_MODEL'
    if variable in os.environ and os.environ[variable] != model:
        raise ValueError(variable + ' explícito prevalece sobre a seleção')
    preferences = replace(saved, inference_profile=profile, **{key: model}).validate()
    config = replace(backend.config, profile=profile,
                     **{'local_model' if profile == 'local' else 'model': model})
    if profile == 'local':
        from .local_setup import managed_python
        config = replace(config, openjarvis_python=os.getenv('JARVIS_OPENJARVIS_PYTHON')
                         or managed_python() or config.openjarvis_python)
    candidate = backend.service_factory(config, auto=backend.auto, manual_callback=backend._approve,
        report=lambda text: backend.events.put(('progress', text)))
    try:
        cancelled = getattr(backend, '_cancel_queued', None)
        if cancelled is not None and cancelled.is_set():
            from .cancellation import CancelledError
            raise CancelledError('Troca de perfil cancelada; sessão anterior preservada')
        candidate.approval.authorizations = backend.authorization_store
        if old is not None:
            candidate.approval = old.approval
            candidate.toolkit.approve = old.approval
            candidate.tasks.approve = old.approval
        cached = getattr(backend, '_profile_caps', {})
        if old is not None and profile == backend.config.profile:
            candidate.toolkit.capabilities = CapabilityPolicy(candidate.toolkit.registry,
                set(old.toolkit.capabilities.enabled) & candidate.toolkit.registry.capabilities)
        elif profile in cached:
            candidate.toolkit.capabilities = CapabilityPolicy(candidate.toolkit.registry,
                set(cached[profile]) & candidate.toolkit.registry.capabilities)
        backend.preference_store.save(preferences)
        if old is not None:
            cached[backend.config.profile] = set(old.toolkit.capabilities.enabled)
            try:
                old.close()
            except BaseException:
                backend.preference_store.save(saved)
                raise
    except BaseException:
        candidate.close()
        raise
    backend._profile_caps = cached
    backend.service, backend.config, backend.preferences = candidate, config, preferences
    backend._conversation = None
    backend.events.put(('profile', profile))
    backend.events.put(('connected', {'profile': profile, 'model': candidate.client.active_model,
        'approval': candidate.approval.mode, 'capabilities': sorted(candidate.toolkit.capabilities.enabled)}))
    return profile
