"""Avaliação de áudio consentido externo; nenhum texto privado no relatório."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def tokens(text):
    return re.findall(r'\w+(?:[.,]\d+)?', unicodedata.normalize('NFC', text.casefold()))


def word_errors(reference, hypothesis):
    expected, actual = tokens(reference), tokens(hypothesis)
    row = list(range(len(actual) + 1))
    for index, word in enumerate(expected, 1):
        next_row = [index]
        for column, predicted in enumerate(actual, 1):
            next_row.append(min(row[column] + 1, next_row[-1] + 1,
                                row[column - 1] + (word != predicted)))
        row = next_row
    return row[-1], len(expected)


_VALUES = {word: value for value, words in (
    (0, 'zero'), (1, 'um uma'), (2, 'dois duas'), (3, 'tres'), (4, 'quatro'),
    (5, 'cinco'), (6, 'seis'), (7, 'sete'), (8, 'oito'), (9, 'nove'),
    (10, 'dez'), (11, 'onze'), (12, 'doze'), (13, 'treze'), (14, 'catorze quatorze'),
    (15, 'quinze'), (16, 'dezesseis'), (17, 'dezessete'), (18, 'dezoito'), (19, 'dezenove'),
    (20, 'vinte'), (30, 'trinta'), (40, 'quarenta'), (50, 'cinquenta'), (60, 'sessenta'),
    (70, 'setenta'), (80, 'oitenta'), (90, 'noventa'), (100, 'cem cento'),
    (200, 'duzentos duzentas'), (300, 'trezentos trezentas'), (400, 'quatrocentos quatrocentas'),
    (500, 'quinhentos quinhentas'), (600, 'seiscentos seiscentas'),
    (700, 'setecentos setecentas'), (800, 'oitocentos oitocentas'), (900, 'novecentos novecentas'))
    for word in words.split()}
_ORDINALS = {word: value for value, stem in enumerate(
    ('primeir', 'segund', 'terceir', 'quart', 'quint', 'sext', 'setim', 'oitav', 'non', 'decim'), 1)
    for word in (stem + 'o', stem + 'a')}
_SCALES = {'milhao': 1000000, 'milhoes': 1000000, 'bilhao': 1000000000, 'bilhoes': 1000000000}
_NEGATIONS = {'nao', 'nunca', 'sem', 'jamais', 'nem', 'nenhum', 'nenhuma', 'nenhuns', 'nenhumas'}


def _word_number(parts, index):
    start, total, group, limit, scaled = index, 0, 0, 1000, False
    while index < len(parts):
        word = parts[index]
        if word == 'e' and index > start:
            if index + 1 >= len(parts) or _VALUES.get(parts[index + 1], 1000) >= limit:
                break
            index += 1
            word = parts[index]
        if word == 'mil' and not scaled:
            total, group, limit, scaled = max(group, 1) * 1000, 0, 1000, True
        elif word in _VALUES and _VALUES[word] < limit:
            value = _VALUES[word]
            group += value
            limit = 100 if value >= 100 else 10 if value >= 20 else 0
        else:
            break
        index += 1
    return (str(total + group), index) if index > start else (None, start)


def _decimal(value):
    result = format(Decimal(value), 'f')
    result = result.rstrip('0').rstrip('.') if '.' in result else result
    return '0' if result in ('-0', '+0') else result


def _quantity(parts, index):
    value = parts[index]
    if value in _ORDINALS:
        return 'ordinal:' + str(_ORDINALS[value]), index + 1
    if re.fullmatch(r'\d+[oa]', value):
        return 'ordinal:' + str(int(value[:-1])), index + 1
    if value in _SCALES:
        return 'scale:' + str(_SCALES[value]), index + 1
    if value in ('meio', 'meia'):
        return '0.5', index + 1
    if re.fullmatch(r'[+-]?\d+(?:[.,]\d+)*', value):
        if len(value) > 1 and value.startswith('0') and ',' not in value and '.' not in value:
            return 'digits:' + value, index + 1
        if ',' in value:
            value = value.replace('.', '').replace(',', '.')
        elif '.' in value and all(len(group) == 3 for group in value.split('.')[1:]):
            value = value.replace('.', '')
        try:
            return _decimal(value), index + 1
        except InvalidOperation:
            return 'literal:' + parts[index], index + 1
    return _word_number(parts, index)


def critical_values(text):
    """Conservative pt-BR quantities, not a general semantic equivalence judge."""
    folded = ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                     if not unicodedata.combining(char))
    parts = re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:[oa]\b)?|[^\W\d_]+', folded)
    numbers, events, index = [], [], 0
    while index < len(parts):
        if parts[index] in _NEGATIONS:
            events.append(('negation', parts[index]))
            index += 1
            continue
        negative = parts[index] == 'menos'
        start = index + 1 if negative else index
        if start >= len(parts):
            events.append(('word', parts[index]))
            break
        value, end = _quantity(parts, start)
        if value is None:
            events.append(('word', parts[index]))
            index += 1
            continue
        if end < len(parts) and parts[end] in ('virgula', 'ponto') and re.fullmatch(r'-?\d+', value):
            fraction, cursor = [], end + 1
            while cursor < len(parts):
                tail, following = _quantity(parts, cursor)
                if tail is None or not tail.isdigit(): break
                fraction.append(tail)
                cursor = following
            if fraction:
                value = _decimal(value + '.' + ''.join(fraction))
                end = cursor
        value = '-' + value if negative and value != '0' else value
        numbers.append(value)
        events.append(('quantity', value))
        index = end
    return {'numbers': tuple(numbers),
            'negations': tuple(word for word in parts if word in _NEGATIONS),
            'sequence': tuple(event for event in events if event[0] != 'word'),
            'negation_context': tuple((event[1], tuple(events[i + 1:i + 4]))
                                      for i, event in enumerate(events) if event[0] == 'negation')}


def critical_match(reference, hypothesis):
    return all(critical_assessment(reference, hypothesis).values())


def critical_assessment(reference, hypothesis):
    expected, actual = critical_values(reference), critical_values(hypothesis)
    return {'numbers_match': expected['numbers'] == actual['numbers'],
            'negations_match': expected['negations'] == actual['negations'],
            'critical_order_match': expected['sequence'] == actual['sequence'],
            'negation_context_match': expected['negation_context'] == actual['negation_context']}
