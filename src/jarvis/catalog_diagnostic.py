"""Compara projeções do catálogo FCC sem inferência nem refresh de provedores."""
from collections import Counter
from .fcc import FCCError


def inspect_catalog(client):
    catalog = client.models()
    if not isinstance(catalog, dict) or not isinstance(catalog.get('data'), list):
        raise FCCError('Catálogo Responses inválido', category='invalid_response')
    rows = [row for row in catalog['data'] if isinstance(row, dict) and isinstance(row.get('id'), str)]
    ids = [row['id'] for row in rows]
    refs = {row.get('provider_model_ref') or row['id'] for row in rows
            if isinstance(row.get('provider_model_ref') or row['id'], str)}
    report = {
        'fcc_url': client.base_url,
        'responses_count': len(ids),
        'default_model_id': catalog.get('default_model_id'),
        'by_provider': dict(sorted(Counter(ref.split('/', 1)[0] for ref in refs).items())),
        'models': [{'id': row['id'], 'provider_model_ref': row.get('provider_model_ref')}
                   for row in rows],
        'has_more': bool(catalog.get('has_more', False)),
        'notes': ['Listagem não comprova inferência, cota ou suporte a ferramentas.',
                  'GET de catálogo não atualiza a descoberta de provedores no FCC.'],
    }
    if report['has_more']:
        report['notes'].append('Servidor anuncia mais páginas; esta versão consulta apenas a primeira.')
    for label, path in [('default_view', '/v1/models'), ('admin', '/admin/api/models')]:
        try:
            data = client.request('GET', path)
            if label == 'admin':
                if not isinstance(data, dict) or not isinstance(data.get('models'), list):
                    raise FCCError('Catálogo admin inválido', category='invalid_response')
                admin_refs = {ref for ref in data['models'] if isinstance(ref, str)}
                report['admin'] = {
                    'count': len(admin_refs),
                    'missing_in_responses': sorted(admin_refs - refs),
                    'only_in_responses': sorted(refs - admin_refs),
                    'comparison': 'provider_model_ref quando informado; senão ID anunciado',
                }
            else:
                if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                    raise FCCError('Catálogo padrão inválido', category='invalid_response')
                report[label] = {'count': len(data['data']),
                                 'note': 'A visão padrão pode incluir aliases Claude; nomes diferentes não significam modelos extras.'}
        except FCCError as exc:
            report[label] = {'available': False, 'http_status': exc.status, 'category': exc.category}
    return report
