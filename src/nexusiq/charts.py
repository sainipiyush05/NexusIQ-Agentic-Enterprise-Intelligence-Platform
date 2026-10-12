"""Render an SVG only after validating the read-only SQL result contract."""
import re
from html import escape
from pathlib import Path

from .config import REPORTS
from .sqltool import ReadOnlySQLTool

REGION_SQL = 'SELECT region, COUNT(*) AS customer_count FROM customers GROUP BY region ORDER BY region'
REGIONS = ('AMER', 'APAC', 'EMEA')


class ChartValidationError(ValueError):
    pass


def validate_customer_regions(result):
    if not isinstance(result, dict) or result.get('table') != 'customers' or result.get('tenant_id') != 'atlascloud':
        raise ChartValidationError('Expected the authorized customer aggregate')
    if result.get('truncated') is not False or not isinstance(result.get('rows'), list):
        raise ChartValidationError('Truncated or missing chart rows')
    rows = result['rows']
    if not 1 <= len(rows) <= len(REGIONS) or result.get('row_count') != len(rows):
        raise ChartValidationError('Unexpected row count')
    policy = result.get('policy')
    if not isinstance(policy, dict) or policy.get('read_only_transaction') is not True or policy.get('single_table') is not True:
        raise ChartValidationError('Missing read-only provenance')
    if not isinstance(result.get('query_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', result['query_sha256']):
        raise ChartValidationError('Missing query fingerprint')
    counts = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'region', 'customer_count'}:
            raise ChartValidationError('Unexpected chart columns')
        region, count = row['region'], row['customer_count']
        if not isinstance(region, str) or region not in REGIONS or region in counts or type(count) is not int or not 0 <= count <= 1_000_000:
            raise ChartValidationError('Invalid region or count')
        counts[region] = count
    return [(region, counts[region]) for region in REGIONS if region in counts]


def render_customer_regions(result):
    rows = validate_customer_regions(result)
    total = sum(count for _, count in rows)
    scale = max(count for _, count in rows) or 1
    bars = []
    for index, (region, count) in enumerate(rows):
        y = 116 + index * 70
        length = round(540 * count / scale)
        bars.append(f'<text x="76" y="{y+27}" class="region">{escape(region)}</text>'
                    f'<rect x="175" y="{y}" width="{length}" height="38" rx="7" fill="#146b88"/>'
                    f'<text x="{190+length}" y="{y+27}" class="value">{count:,}</text>')
    height = 160 + len(rows) * 70
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc" '
            f'viewBox="0 0 880 {height}">\n'
            '<title id="title">Customers by region</title>\n'
            f'<desc id="desc">Validated tenant-scoped SQL aggregate. {total} synthetic customers across {len(rows)} regions.</desc>\n'
            '<style>text{font-family:Arial,sans-serif;fill:#143348}.title{font-size:25px;font-weight:700}.sub{font-size:13px;fill:#496476}.region{font-size:18px;font-weight:600}.value{font-size:17px;font-weight:700}</style>\n'
            '<rect width="100%" height="100%" fill="#f5fafc"/>\n'
            '<text x="76" y="54" class="title">Customers by region</text>\n'
            f'<text x="76" y="78" class="sub">AtlasCloud synthetic data · {total:,} customers · SQL aggregate</text>\n'
            + '\n'.join(bars) + '\n</svg>\n')


def export_customer_regions(tool=None, destination=None):
    tool = tool or ReadOnlySQLTool()
    result = tool.run(REGION_SQL, tenant_id='atlascloud', max_rows=10)
    svg = render_customer_regions(result)
    destination = Path(destination) if destination else REPORTS/'customer_regions_dev.svg'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(svg)
    return dict(path=str(destination), rows=validate_customer_regions(result), total=sum(row['customer_count'] for row in result['rows']),
                query_sha256=result['query_sha256'], latency_ms=result['latency_ms'])
