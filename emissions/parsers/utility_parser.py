"""
Utility Electricity CSV Parser — Green Button Format

What we chose and why:
- Format: Green Button "Download My Data" CSV export
- This is the de-facto standard for utility data export in the US and increasingly in India/EU
- Oracle CC&B, SAP ISU, Itron, Landis+Gyr — all support Green Button export
- Alternative (PDF bills): would need OCR — too brittle for a prototype
- Alternative (utility API): each utility has its own API — no standard, too much integration work

Green Button CSV columns (from Oracle CC&B documentation):
  TYPE, DATE, START TIME, END TIME, USAGE, UNITS, COST, NOTES

Key real-world complications we handle:
1. Billing periods don't align with calendar months
   (e.g., Nov 9 – Dec 10 is a 31-day billing cycle, not a month)
   We store billing_start and billing_end explicitly, don't assume monthly
2. UNITS can be kWh, Wh, MWh, kW (demand vs. consumption confusion)
   We normalize all to kWh
3. Multi-meter files: a facilities team might export one CSV with rows for
   10 different meters — we use the meter_id header row if present
4. Cost column: useful for anomaly detection (cost/kWh ratio check)
5. Some utilities add a "NOTES" column with tariff schedule name — we capture it

Scope: Always Scope 2 (purchased electricity, market-based or location-based)
We use location-based by default (grid emission factor) since we don't have
supplier-specific certificates at ingest time.

What we explicitly ignore:
- Gas/water rows in the same file (TYPE != 'Electric') — out of scope for this prototype
- Reactive power (kVAR) and demand (kW) columns — not needed for Scope 2 calculation
- Sub-daily interval data — we aggregate to billing period level
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


# Unit normalization to kWh
UTILITY_UNIT_MAP = {
    'KWH': Decimal('1'),
    'WH': Decimal('0.001'),           # Watt-hours → kWh
    'MWH': Decimal('1000'),           # MWh → kWh
    'KW': None,                        # demand, not energy — skip
    'THERM': None,                     # gas — skip (different scope)
    'CCF': None,                       # gas — skip
}


def parse_green_button_date(date_str: str) -> Optional[date]:
    """
    Green Button dates appear in several formats:
    - YYYY-MM-DD (ISO)
    - MM/DD/YYYY (US)
    - DD/MM/YYYY (UK/India)
    """
    date_str = date_str.strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def extract_meter_id_from_header(lines: list[str]) -> Optional[str]:
    """
    Green Button files sometimes embed meter ID in a header line above the CSV data.
    Example header lines:
      "Meter ID: 1234567890"
      "Service Point ID: SP-89012"
    We scan the first 10 lines for this pattern.
    """
    for line in lines[:10]:
        m = re.search(r'(?:Meter ID|Service Point ID|Meter Number)[:\s]+([A-Z0-9\-]+)', line, re.I)
        if m:
            return m.group(1).strip()
    return None


def extract_tariff_from_header(lines: list[str]) -> Optional[str]:
    """
    Same idea — some files embed the tariff schedule name in a comment line.
    Example: "Rate Schedule: E-19 Medium General Demand-Metered TOU Service"
    """
    for line in lines[:10]:
        m = re.search(r'(?:Rate Schedule|Tariff|Rate Plan)[:\s]+(.+)', line, re.I)
        if m:
            return m.group(1).strip()[:100]
    return None


class UtilityIngestionParser:
    """
    Parses Green Button CSV utility export into normalized EmissionRecord dicts.
    """

    def __init__(self, tenant_id: str, job_id: str):
        self.tenant_id = tenant_id
        self.job_id = job_id

    def parse(self, file_bytes: bytes) -> tuple[list[dict], list[dict]]:
        try:
            text = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = file_bytes.decode('latin-1')

        lines = text.splitlines()
        meter_id = extract_meter_id_from_header(lines)
        tariff = extract_tariff_from_header(lines)

        # Find the actual CSV data start (skip metadata comment lines)
        csv_start = 0
        for i, line in enumerate(lines):
            # Green Button CSV header row starts with TYPE or DATE
            if re.match(r'^\s*(TYPE|DATE|START DATE)', line, re.I):
                csv_start = i
                break

        csv_text = '\n'.join(lines[csv_start:])
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = [h.strip().upper() for h in (reader.fieldnames or [])]

        records = []
        errors = []

        for row_num, row in enumerate(reader, start=csv_start + 2):
            # Normalize header keys
            normalized_row = {k.strip().upper(): v.strip() for k, v in row.items() if k}
            try:
                record = self._parse_row(normalized_row, row_num, meter_id, tariff)
                if record:
                    records.append(record)
            except Exception as e:
                errors.append({
                    'row_number': row_num,
                    'row_data': dict(row),
                    'error': str(e),
                })

        return records, errors

    def _parse_row(
        self, row: dict, row_num: int, meter_id: Optional[str], tariff: Optional[str]
    ) -> Optional[dict]:
        # Filter to electricity only — skip gas, water
        row_type = row.get('TYPE', 'Electric')
        if row_type and 'electric' not in row_type.lower() and 'kwh' not in row_type.lower():
            return None  # Gas or water row — different scope, skip

        # Parse dates
        # Green Button uses START DATE / END DATE for billing periods
        start_date_str = row.get('START DATE') or row.get('DATE') or ''
        end_date_str = row.get('END DATE') or ''

        billing_start = parse_green_button_date(start_date_str)
        if not billing_start:
            raise ValueError(f"Cannot parse start date '{start_date_str}'")

        billing_end = parse_green_button_date(end_date_str) if end_date_str else billing_start
        activity_date = billing_start  # we use billing start as the activity date

        # Usage quantity
        usage_str = row.get('USAGE') or row.get('CONSUMPTION') or ''
        if not usage_str:
            raise ValueError("Missing USAGE column")
        try:
            quantity_original = Decimal(usage_str.replace(',', ''))
        except InvalidOperation:
            raise ValueError(f"Cannot parse usage value '{usage_str}'")

        # Unit
        unit_str = (row.get('UNITS') or row.get('UNIT') or 'kWh').strip().upper()
        conversion = UTILITY_UNIT_MAP.get(unit_str)
        if conversion is None:
            if unit_str in ('THERM', 'CCF'):
                return None  # Gas — skip
            raise ValueError(f"Unknown utility unit '{unit_str}'")

        quantity_normalized = quantity_original * conversion

        # Cost — for anomaly detection only
        cost_str = row.get('COST', '').replace('$', '').replace(',', '').strip()
        cost = None
        try:
            if cost_str:
                cost = Decimal(cost_str)
        except InvalidOperation:
            pass

        # Billing period length in days — sanity check
        billing_days = (billing_end - billing_start).days if billing_end else 30
        if billing_days < 1:
            raise ValueError(f"Billing end {billing_end} is before start {billing_start}")

        # Suspicion checks
        suspicion_reasons = []
        if quantity_normalized > 500000:
            suspicion_reasons.append(f"Very high consumption: {quantity_normalized} kWh")
        if quantity_normalized < 1:
            suspicion_reasons.append(f"Suspiciously low: {quantity_normalized} kWh")
        if billing_days > 45:
            suspicion_reasons.append(f"Long billing period: {billing_days} days (expected ~30)")
        if billing_days < 20:
            suspicion_reasons.append(f"Short billing period: {billing_days} days (expected ~30)")
        if cost and quantity_normalized > 0:
            cost_per_kwh = cost / quantity_normalized
            if cost_per_kwh > 1:
                suspicion_reasons.append(
                    f"High cost/kWh: ${cost_per_kwh:.3f} (typical: $0.10-$0.30)"
                )

        notes = row.get('NOTES', '')
        tariff_final = tariff or notes[:100] if notes else ''

        return {
            'tenant_id': self.tenant_id,
            'ingestion_job_id': self.job_id,
            'source_type': 'UTILITY',
            'raw_row': dict(row),
            'source_row_number': row_num,
            'activity_date': activity_date,
            'activity_description': f"Electricity — Meter {meter_id or 'unknown'} — {billing_days}d period",
            'scope': 'S2',
            'quantity_original': quantity_original,
            'unit_original': unit_str,
            'quantity_normalized': quantity_normalized,
            'unit_normalized': 'kWh',
            'utility_meter_id': meter_id or '',
            'utility_tariff': tariff_final,
            'utility_billing_start': billing_start,
            'utility_billing_end': billing_end,
            'is_suspicious': bool(suspicion_reasons),
            'suspicion_reasons': suspicion_reasons,
        }