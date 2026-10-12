"""Typed, bounded access to Frankfurter's public single-pair exchange-rate API."""
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ROOT = 'https://api.frankfurter.dev/v2/rate'
CURRENCIES = frozenset({'USD', 'EUR', 'GBP', 'INR'})
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_BODY_BYTES = 8192


class ExternalAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExchangeRate:
    date: date
    base: str
    quote: str
    rate: Decimal
    source_url: str

    def as_dict(self):
        return dict(date=self.date.isoformat(), base=self.base, quote=self.quote,
                    rate=str(self.rate), source_url=self.source_url)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _fetch(url, timeout_s):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'NexusIQ-local/0.1'})
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout_s) as response:
            body = response.read(MAX_BODY_BYTES + 1)
            return response.status, response.headers.get('Content-Type', ''), body
    except HTTPError as exc:
        return exc.code, exc.headers.get('Content-Type', ''), exc.read(MAX_BODY_BYTES + 1)


class ExchangeRateTool:
    def __init__(self, transport=_fetch, sleep=time.sleep, timeout_s=3.0, attempts=2):
        if not 0 < timeout_s <= 5 or type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError('Invalid API timeout or attempt limit')
        self.transport, self.sleep = transport, sleep
        self.timeout_s, self.attempts = timeout_s, attempts

    def rate(self, base, quote, on_date=None):
        if not isinstance(base, str) or not isinstance(quote, str) or base not in CURRENCIES or quote not in CURRENCIES or base == quote:
            raise ValueError('Unsupported or identical currency pair')
        requested = None
        if on_date is not None:
            if not isinstance(on_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', on_date):
                raise ValueError('Date must be YYYY-MM-DD')
            try:
                requested = date.fromisoformat(on_date)
            except ValueError as exc:
                raise ValueError('Invalid calendar date') from exc
            if requested > date.today():
                raise ValueError('Future rates are unavailable')
        url = f'{API_ROOT}/{base.lower()}/{quote.lower()}'
        if requested:
            url += '?' + urlencode({'date': requested.isoformat()})
        started = time.perf_counter()
        for attempt in range(self.attempts):
            try:
                status, content_type, body = self.transport(url, self.timeout_s)
            except (URLError, TimeoutError, OSError) as exc:
                if attempt + 1 == self.attempts:
                    raise ExternalAPIError('Exchange-rate provider unavailable') from exc
                self.sleep(.2 * (2 ** attempt))
                continue
            if status in RETRY_STATUS:
                if attempt + 1 == self.attempts:
                    raise ExternalAPIError(f'Exchange-rate provider returned {status}')
                self.sleep(.2 * (2 ** attempt))
                continue
            if status != 200:
                raise ExternalAPIError(f'Exchange-rate provider returned {status}')
            if len(body) > MAX_BODY_BYTES or 'application/json' not in content_type.lower():
                raise ExternalAPIError('Exchange-rate response is too large or not JSON')
            try:
                payload = json.loads(body, parse_float=Decimal)
                if not isinstance(payload, dict) or not {'date', 'base', 'quote', 'rate'} <= set(payload):
                    raise ValueError('Missing exchange-rate fields')
                observed = date.fromisoformat(payload['date'])
                if payload['base'] != base or payload['quote'] != quote or observed > date.today():
                    raise ValueError('Mismatched exchange-rate pair or date')
                if requested and observed > requested:
                    raise ValueError('Rate date is later than requested')
                if type(payload['rate']) not in (int, Decimal, str):
                    raise ValueError('Invalid rate type')
                value = Decimal(str(payload['rate']))
                if not value.is_finite() or not 0 < value < Decimal('1000000000'):
                    raise ValueError('Invalid rate value')
            except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
                raise ExternalAPIError('Invalid exchange-rate response') from exc
            return ExchangeRate(observed, base, quote, value, url).as_dict() | {
                'latency_ms': round((time.perf_counter()-started)*1000, 2), 'attempts': attempt + 1}
        raise ExternalAPIError('Exchange-rate provider unavailable')
