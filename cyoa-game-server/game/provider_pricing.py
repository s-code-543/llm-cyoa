"""Read standard direct-provider token rates from official public documentation.

Catalog availability and pricing are independent: a pricing failure must never
make a model unavailable or overwrite a previously checked price.
"""
from decimal import Decimal
import re

import requests
from django.core.cache import cache
from django.utils import timezone

SOURCES = {
    'openai': 'https://developers.openai.com/api/docs/pricing',
    'anthropic': 'https://platform.claude.com/docs/en/about-claude/pricing',
}
CACHE_SECONDS = 3600
NOTE = 'Standard base input/output rates. Long-context, service-tier and feature charges may differ; see the official source.'


class PricingUnavailable(ValueError):
    pass


def plain(value):
    value = re.sub(r'<sup>.*?</sup>', '', value)
    value = re.sub(r'<[^>]+>', '', value)
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    return value.replace('`', '').replace('**', '').strip()


def first_table(section):
    """Only the first table in a specifically identified pricing section."""
    rows = []
    for line in section.splitlines():
        if line.lstrip().startswith('|'):
            rows.append([plain(cell) for cell in line.strip().strip('|').split('|')])
        elif rows:
            break
    if len(rows) < 3:
        raise PricingUnavailable('Official pricing table format was not recognized.')
    return rows[0], rows[2:]


def per_token(cell):
    # Permit only an unambiguous USD number per million tokens, never ranges,
    # tiers, or a different unit. Footnotes are removed before parsing.
    cell = re.sub(r'<sup>.*?</sup>', '', cell)
    text = plain(cell)
    match = re.fullmatch(r'\$([0-9]+(?:\.[0-9]+)?)(?:\s*/\s*MTok)?', text)
    if not match:
        return None
    return format(Decimal(match[1]) / Decimal(1000000), 'f')


def parse_openai(document):
    marker = '### Standard pricing data'
    if marker not in document:
        raise PricingUnavailable('OpenAI standard pricing section was not recognized.')
    headers, rows = first_table(document.split(marker, 1)[1])
    try:
        input_index = headers.index('Short context input')
        output_index = headers.index('Short context output')
        assert headers[0] == 'Model'
    except (ValueError, AssertionError) as exc:
        raise PricingUnavailable('OpenAI standard pricing columns changed.') from exc
    prices = {}
    for row in rows:
        if len(row) != len(headers):
            raise PricingUnavailable('OpenAI pricing row shape changed.')
        model = re.fullmatch(r'([a-z0-9][a-z0-9.-]*)(?:\s*\([^)]*\))?', row[0])
        prompt, completion = per_token(row[input_index]), per_token(row[output_index])
        if model and prompt is not None and completion is not None:
            if model[1] in prices:
                raise PricingUnavailable('Duplicate OpenAI standard pricing row.')
            prices[model[1]] = {'prompt': prompt, 'completion': completion}
    if not prices:
        raise PricingUnavailable('No OpenAI token rates were recognized.')
    return prices


def claude_name(name):
    # Public display names identify an edition even when its API ID is dated.
    name = plain(name).split(' (', 1)[0].strip().lower()
    match = re.fullmatch(r'claude (opus|sonnet|haiku|fable|mythos) ([0-9]+(?:\.[0-9]+)?)', name)
    if match:
        return f'claude-{match[1]}-{match[2].replace(".", "-")}'
    match = re.fullmatch(r'claude ([0-9]+(?:\.[0-9]+)?) (opus|sonnet|haiku)', name)
    if match:
        return f'claude-{match[2]}-{match[1].replace(".", "-")}'
    return None


def parse_anthropic(document):
    marker = '## Model pricing'
    if marker not in document:
        raise PricingUnavailable('Anthropic model pricing section was not recognized.')
    headers, rows = first_table(document.split(marker, 1)[1])
    try:
        input_index = headers.index('Base input tokens')
        output_index = headers.index('Output tokens')
        assert headers[0] == 'Model'
    except (ValueError, AssertionError) as exc:
        raise PricingUnavailable('Anthropic pricing columns changed.') from exc
    prices = {}
    for row in rows:
        if len(row) != len(headers):
            raise PricingUnavailable('Anthropic pricing row shape changed.')
        # The base table can include a second, explicitly long-context row.
        # Keep the named short-context base; never let the later tier replace it.
        if re.search(r'for prompts over [0-9,]+ tokens', row[0], re.I):
            continue
        model = claude_name(row[0])
        prompt, completion = per_token(row[input_index]), per_token(row[output_index])
        if model and prompt is not None and completion is not None:
            if model in prices:
                raise PricingUnavailable('Duplicate Anthropic base pricing row.')
            prices[model] = {'prompt': prompt, 'completion': completion}
    if not prices:
        raise PricingUnavailable('No Anthropic token rates were recognized.')
    return prices


def fetch_rates(provider_type, *, force=False):
    key = f'official-model-pricing:v1:{provider_type}'
    if not force:
        saved = cache.get(key)
        if saved is not None:
            return saved
    source = SOURCES[provider_type]
    response = requests.get(source + '.md', timeout=10)
    response.raise_for_status()
    if len(response.content) > 2 * 1024 * 1024:
        raise PricingUnavailable('Pricing document is too large.')
    parser = parse_openai if provider_type == 'openai' else parse_anthropic
    result = {'rates': parser(response.text), 'source': source,
              'checked_at': timezone.now().isoformat()}
    cache.set(key, result, CACHE_SECONDS)
    return result


def enrich_models(provider_type, models, *, force=False):
    if not models or provider_type not in SOURCES:
        return models
    try:
        result = fetch_rates(provider_type, force=force)
    except (requests.RequestException, PricingUnavailable):
        warning = f'Could not read official {provider_type} pricing; saved prices were kept.'
        return [{**model, 'pricing_warning': warning} for model in models]
    enriched = []
    for model in models:
        key = model['id']
        if provider_type == 'anthropic':
            key = claude_name(model.get('name', '')) or key
        pricing = result['rates'].get(key)
        if pricing is None:
            enriched.append({**model, 'pricing_warning': f'Some models have no exact official {provider_type} price; their saved prices were kept.'})
        else:
            enriched.append({**model, 'pricing': pricing, 'pricing_source': result['source'],
                             'pricing_checked_at': result['checked_at'], 'pricing_note': NOTE})
    return enriched
