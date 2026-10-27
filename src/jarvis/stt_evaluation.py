"""Avaliação de áudio consentido externo; nenhum texto privado no relatório."""
import re
import unicodedata


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


def critical_match(reference, hypothesis):
    def values(text):
        normalized = tokens(text)
        return ([word for word in normalized if re.search(r'\d', word)],
                [word for word in normalized if word in ('não', 'nunca', 'sem', 'jamais')])
    return values(reference) == values(hypothesis)
