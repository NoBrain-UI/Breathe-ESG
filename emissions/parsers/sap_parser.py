"""
SAP Fuel & Procurement CSV Parser

What we chose and why:
- Format: SAP MM flat-file CSV export (from transaction ME2N for POs, MB51 for goods movements)
- NOT IDoc: IDoc is for system-to-system EDI, not analyst-driven file uploads
- NOT OData: requires live SAP connectivity — not realistic for a prototype ingest
- CSV is what sustainability teams actually email around / drop in SharePoint

Real SAP CSV quirks we handle:
1. Date format: YYYYMMDD (SAP internal) or DD.MM.YYYY (German locale output)
2. Decimal separator: sometimes comma (German: "1.234,56") instead of dot
3. Column headers: may be in German (Werk = Plant, Menge = Quantity, Maßeinheit = UoM)
4. WERKS (plant code) is a 4-char opaque code — needs PlantLookup table
5. MEINS (unit of measure) uses SAP internal codes: L=litres, KG=kg, ST=pieces, M3=cubic metres
6. MATKL (material group) tells us if it's fuel vs. other procurement

Scope assignment logic:
- Material group 001-009 (fuels: diesel, petrol, LPG, natural gas) → Scope 1
- All other procurement → Scope 3

What we explicitly ignore:
- Multi-currency POs (WAERS): we store cost but don't normalize it — not needed for emission calc
- Delivery schedules (ETENR): only care about actual goods receipt (BUDAT), not planned dates
- Subcontracting POs (PSTYP=3): complex BOM explosion, out of scope
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
import hashlib

# SAP unit of measure → normalized unit mapping
# These are the SAP internal UoM codes (MEINS field)
SAP_UNIT_MAP = {
    'L': 'L',
    'LT': 'L',      # alternate SAP code for litres
    'KG': 'kg',
    'G': 'kg',       # grams → convert ÷ 1000
    'T': 'kg',       # metric tonnes → convert × 1000
    'M3': 'L',       # cubic metres → convert × 1000
    'GAL': 'L',      # US gallons → convert × 3.785
    'ST': None,      # pieces — no emission factor, skip
    'EA': None,      # each — same
}

# Conversion to normalized unit
SAP_UNIT_CONVERSION = {
    'L': 1,
    'LT': 1,
    'KG': 1,
    'G': Decimal('0.001'),
    'T': Decimal('1000'),
    'M3': Decimal('1000'),
    'GAL': Decimal('3.785411784'),
}

# Material group ranges that indicate fuel (Scope 1 direct combustion)
# In a real client, these groups would come from their SAP material master
FUEL_MATERIAL_GROUPS = {
    '001',  # Diesel / HSD
    '002',  # Petrol / Gasoline
    '003',  # LPG
    '004',  # Natural Gas
    '005',  # Furnace Oil
    '006',  # Aviation Fuel (ATF)
    'FUEL', # Some clients use text codes
    'ENRG', # Energy materials
}

# German → English column header mapping
# SAP installs in Germany often export German headers
GERMAN_TO_ENGLISH = {
    'Werk': 'WERKS',
    'Bestellnummer': 'EBELN',
    'Bestellposition': 'EBELP',
    'Material': 'MATNR',
    'Materialgruppe': 'MATKL',
    'Menge': 'MENGE',
    'Maßeinheit': 'MEINS',
    'Buchungsdatum': 'BUDAT',
    'Lieferant': 'LIFNR',
    'Kurztext': 'TXZ01',
    'Betrag': 'DMBTR',
    'Waehrung': 'WAERS',
}

# Typical English column names we expect (ME2N / MB51 report)
EXPECTED_COLUMNS = {
    'WERKS': ['WERKS', 'Plant', 'Werk', 'Plant Code'],
    'EBELN': ['EBELN', 'PO Number', 'Purchase Order', 'Bestellnummer'],
    'MATNR': ['MATNR', 'Material', 'Material Number'],
    'MATKL': ['MATKL', 'Material Group', 'Mat. Group', 'Materialgruppe'],
    'MENGE': ['MENGE', 'Quantity', 'Menge', 'Qty'],
    'MEINS': ['MEINS', 'UoM', 'Unit', 'Base Unit', 'Maßeinheit'],
    'BUDAT': ['BUDAT', 'Posting Date', 'Buchungsdatum', 'Document Date'],
    'LIFNR': ['LIFNR', 'Vendor', 'Supplier', 'Lieferant'],
    'TXZ01': ['TXZ01', 'Short Text', 'Description', 'Kurztext'],
}


def parse_sap_date(date_str: str) -> Optional[date]:
    """
    SAP dates come in two formats depending on system locale:
    - YYYYMMDD (SAP internal standard)
    - DD.MM.YYYY (German locale display format)
    We try both.
    """
    date_str = date_str.strip()
    for fmt in ('%Y%m%d', '%d.%m.%Y', '%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_sap_decimal(value_str: str) -> Optional[Decimal]:
    """
    SAP German locale uses comma as decimal separator and dot as thousands:
    "1.234,56" = 1234.56 in Python Decimal
    We detect and handle both formats.
    """
    if not value_str or value_str.strip() == '':
        return None
    s = value_str.strip()
    # German format: 1.234,56
    if re.match(r'^\d{1,3}(\.\d{3})*(,\d+)?$', s):
        s = s.replace('.', '').replace(',', '.')
    else:
        # English format or already clean
        s = s.replace(',', '')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def normalize_headers(headers: list[str]) -> dict[str, str]:
    """
    Maps whatever column names the file has → our canonical names.
    Returns a dict: canonical_name → actual_column_index_in_file
    """
    mapping = {}
    header_lower = {h.strip().lower(): h.strip() for h in headers}

    for canonical, aliases in EXPECTED_COLUMNS.items():
        for alias in aliases:
            if alias.lower() in header_lower:
                mapping[canonical] = header_lower[alias.lower()]
                break

    return mapping


class SAPIngestionParser:
    """
    Parses SAP MM CSV export into normalized EmissionRecord dicts.
    Call parse() with file bytes, get back (records, errors).
    """

    def __init__(self, tenant_id: str, job_id: str, plant_lookup: dict = None):
        self.tenant_id = tenant_id
        self.job_id = job_id
        # plant_lookup: {plant_code: {name, country}} — loaded from PlantLookup table
        self.plant_lookup = plant_lookup or {}

    def parse(self, file_bytes: bytes) -> tuple[list[dict], list[dict]]:
        """
        Returns:
          records: list of dicts ready to bulk-create as EmissionRecord
          errors: list of {row_number, row_data, error_message}
        """
        try:
            text = file_bytes.decode('utf-8-sig')  # utf-8-sig strips BOM from Windows exports
        except UnicodeDecodeError:
            text = file_bytes.decode('latin-1')  # SAP German systems often export latin-1

        reader = csv.DictReader(io.StringIO(text), delimiter=self._detect_delimiter(text))
        headers = reader.fieldnames or []

        col_map = normalize_headers(headers)
        missing = [c for c in ['WERKS', 'MENGE', 'MEINS', 'BUDAT'] if c not in col_map]
        if missing:
            raise ValueError(
                f"SAP CSV missing required columns: {missing}. "
                f"Got headers: {headers[:10]}. "
                f"Export using ME2N or MB51 with standard layout."
            )

        records = []
        errors = []

        for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
            try:
                record = self._parse_row(row, col_map, row_num)
                if record:
                    records.append(record)
            except Exception as e:
                errors.append({
                    'row_number': row_num,
                    'row_data': dict(row),
                    'error': str(e),
                })

        return records, errors

    def _detect_delimiter(self, text: str) -> str:
        """SAP exports can be semicolon-delimited (German) or comma-delimited."""
        first_line = text.split('\n')[0]
        if first_line.count(';') > first_line.count(','):
            return ';'
        return ','

    def _parse_row(self, row: dict, col_map: dict, row_num: int) -> Optional[dict]:
        def get(canonical):
            col = col_map.get(canonical)
            return row.get(col, '').strip() if col else ''

        # Required fields
        raw_date = get('BUDAT')
        activity_date = parse_sap_date(raw_date)
        if not activity_date:
            raise ValueError(f"Cannot parse date '{raw_date}' — expected YYYYMMDD or DD.MM.YYYY")

        raw_qty = get('MENGE')
        quantity = parse_sap_decimal(raw_qty)
        if quantity is None or quantity <= 0:
            raise ValueError(f"Invalid quantity '{raw_qty}'")

        unit_raw = get('MEINS').upper()
        if unit_raw not in SAP_UNIT_MAP:
            raise ValueError(f"Unknown SAP UoM '{unit_raw}' — not in our unit map")

        if SAP_UNIT_MAP[unit_raw] is None:
            # Unit is pieces/each — no emission factor possible, skip silently
            return None

        # Normalize quantity
        conversion = SAP_UNIT_CONVERSION.get(unit_raw, Decimal('1'))
        quantity_normalized = quantity * conversion
        unit_normalized = SAP_UNIT_MAP[unit_raw]

        # Scope assignment
        matkl = get('MATKL')
        scope = 'S1' if matkl in FUEL_MATERIAL_GROUPS else 'S3'

        # Suspicion checks
        suspicion_reasons = []
        if quantity_normalized > 100000:
            suspicion_reasons.append(f"Very large quantity: {quantity_normalized} {unit_normalized}")
        if activity_date.year < 2020:
            suspicion_reasons.append(f"Old date: {activity_date} — possible date format error")

        plant_code = get('WERKS')
        plant_info = self.plant_lookup.get(plant_code, {})

        description = get('TXZ01') or f"{matkl} — {plant_code}"

        return {
            'tenant_id': self.tenant_id,
            'ingestion_job_id': self.job_id,
            'source_type': 'SAP',
            'raw_row': dict(row),
            'source_row_number': row_num,
            'activity_date': activity_date,
            'activity_description': description[:500],
            'scope': scope,
            'quantity_original': quantity,
            'unit_original': unit_raw,
            'quantity_normalized': quantity_normalized,
            'unit_normalized': unit_normalized,
            'sap_plant_code': plant_code,
            'sap_material_group': matkl,
            'sap_vendor': get('LIFNR'),
            'sap_po_number': get('EBELN'),
            'is_suspicious': bool(suspicion_reasons),
            'suspicion_reasons': suspicion_reasons,
        }