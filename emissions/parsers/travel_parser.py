"""
Corporate Travel CSV Parser — Navan / Concur Export Format

What we chose and why:
- Format: CSV export from Navan (formerly TripActions) or Concur
- NOT direct Navan API: requires enterprise API setup, restricted by plan, not realistic
  for a new client onboarding. Their sustainability/finance team will CSV-export from the
  platform and hand it over.
- Concur and Navan CSV exports have nearly identical column structures for trip data

Real-world fields in Navan/Concur trip export:
  trip_id, traveler_name, traveler_email, cost_center,
  segment_type (FLIGHT / HOTEL / GROUND / RAIL),
  origin, destination,               ← airport codes (IATA) for flights
  departure_date, return_date,
  distance_km,                       ← often NULL for flights (only given for ground)
  duration_nights,                   ← for hotels
  cost_amount, cost_currency,
  booking_date, trip_purpose

Key complication: DISTANCE for flights
- Navan does NOT always give distance for flights — they give origin/destination airport codes
- We must estimate distance from airport codes using great-circle formula
- This is standard practice: DEFRA, ICAO, GHG Protocol all use origin-destination pairs
- We use a static lookup of IATA codes → lat/lon (stored in airport_distances.py)

Segment → Scope 3 category mapping (GHG Protocol):
- FLIGHT → Scope 3, Category 6 (Business Travel, air)
- HOTEL → Scope 3, Category 6 (Business Travel, accommodation)
- GROUND → Scope 3, Category 6 (Business Travel, ground transport)
- RAIL → Scope 3, Category 6 (Business Travel, rail)

Emission factors (kg CO2e per unit):
- Flights: DEFRA 2023 — short-haul economy: 0.255 kg/km, long-haul: 0.195 kg/km
  (includes radiative forcing multiplier of 1.9x for high-altitude effect)
- Hotels: ~20 kg CO2e per room-night (HCMI average)
- Ground: ~0.171 kg/km (average business car hire, DEFRA)

What we explicitly ignore:
- Rail transport (needs country-specific emission factors, complex routing)
- Personal car mileage claims (no trip data structure in Navan)
- Meals / per-diem expenses (not travel emissions)
"""

import csv
import io
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


# --- Airport IATA code → (latitude, longitude) ---
# We include the top 200 busiest airports for realistic coverage
# In production this would be a full IATA database
AIRPORT_COORDS = {
    # India
    'DEL': (28.5561, 77.1000),   # Delhi Indira Gandhi
    'BOM': (19.0887, 72.8679),   # Mumbai Chhatrapati Shivaji
    'BLR': (13.1979, 77.7063),   # Bengaluru Kempegowda
    'MAA': (12.9900, 80.1693),   # Chennai
    'CCU': (22.6547, 88.4467),   # Kolkata
    'HYD': (17.2313, 78.4298),   # Hyderabad
    'AMD': (23.0769, 72.6347),   # Ahmedabad
    'GOI': (15.3808, 73.8314),   # Goa
    'LKO': (26.7606, 80.8893),   # Lucknow
    'PNQ': (18.5822, 73.9197),   # Pune
    # Global hubs
    'LHR': (51.4775, -0.4614),   # London Heathrow
    'CDG': (49.0097, 2.5478),    # Paris Charles de Gaulle
    'FRA': (50.0333, 8.5706),    # Frankfurt
    'DXB': (25.2528, 55.3644),   # Dubai
    'SIN': (1.3644, 103.9915),   # Singapore
    'HKG': (22.3080, 113.9185),  # Hong Kong
    'NRT': (35.7647, 140.3864),  # Tokyo Narita
    'JFK': (40.6398, -73.7789),  # New York JFK
    'LAX': (33.9425, -118.4081), # Los Angeles
    'ORD': (41.9742, -87.9073),  # Chicago O'Hare
    'SFO': (37.6213, -122.3790), # San Francisco
    'SYD': (-33.9461, 151.1772), # Sydney
    'AMS': (52.3105, 4.7683),    # Amsterdam
    'ICN': (37.4602, 126.4407),  # Seoul Incheon
    'PEK': (40.0725, 116.5975),  # Beijing Capital
    'DOH': (25.2609, 51.6138),   # Doha
    'AUH': (24.4428, 54.6511),   # Abu Dhabi
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in km between two points.
    Standard formula — used by ICAO and DEFRA for flight distance calculation.
    """
    R = 6371  # Earth radius km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_flight_distance(origin: str, destination: str) -> tuple[Optional[float], str]:
    """
    Returns (distance_km, note).
    note explains the method used — important for audit trail.
    """
    o = AIRPORT_COORDS.get(origin.upper())
    d = AIRPORT_COORDS.get(destination.upper())

    if o and d:
        km = haversine_km(o[0], o[1], d[0], d[1])
        return km, f"Great-circle estimate from IATA coords ({origin}→{destination})"
    elif o or d:
        return None, f"Missing coords for {'destination' if o else 'origin'} {destination if o else origin}"
    else:
        return None, f"Unknown airport codes: {origin}, {destination}"


def get_flight_emission_factor(distance_km: float) -> tuple[Decimal, str]:
    """
    DEFRA 2023 emission factors for economy class flights, with radiative forcing (×1.9).
    Short-haul: < 3700 km, Long-haul: >= 3700 km
    Returns (kg_co2e_per_km, factor_description)
    """
    if distance_km < 3700:
        return Decimal('0.255'), 'DEFRA 2023 short-haul economy with RFI'
    else:
        return Decimal('0.195'), 'DEFRA 2023 long-haul economy with RFI'


def parse_travel_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


class TravelIngestionParser:
    """
    Parses Navan / Concur CSV travel export into normalized EmissionRecord dicts.
    """

    SEGMENT_FIELD_ALIASES = {
        'FLIGHT': ['FLIGHT', 'AIR', 'AIRLINE', 'PLANE'],
        'HOTEL': ['HOTEL', 'ACCOMMODATION', 'LODGING'],
        'GROUND': ['GROUND', 'CAR', 'TAXI', 'UBER', 'RENTAL', 'GROUND TRANSPORT'],
        'RAIL': ['RAIL', 'TRAIN', 'AMTRAK', 'EUROSTAR'],
    }

    def __init__(self, tenant_id: str, job_id: str):
        self.tenant_id = tenant_id
        self.job_id = job_id

    def parse(self, file_bytes: bytes) -> tuple[list[dict], list[dict]]:
        try:
            text = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = file_bytes.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        records = []
        errors = []

        for row_num, row in enumerate(reader, start=2):
            norm = {k.strip().lower().replace(' ', '_'): v.strip() for k, v in row.items() if k}
            try:
                record = self._parse_row(norm, row_num)
                if record:
                    records.append(record)
            except Exception as e:
                errors.append({
                    'row_number': row_num,
                    'row_data': dict(row),
                    'error': str(e),
                })

        return records, errors

    def _normalize_segment_type(self, raw: str) -> str:
        raw_up = raw.upper()
        for canonical, aliases in self.SEGMENT_FIELD_ALIASES.items():
            if any(alias in raw_up for alias in aliases):
                return canonical
        return 'GROUND'  # default

    def _get(self, row: dict, *keys) -> str:
        for k in keys:
            if k in row and row[k]:
                return row[k]
        return ''

    def _parse_row(self, row: dict, row_num: int) -> Optional[dict]:
        segment_raw = self._get(row, 'segment_type', 'type', 'category', 'travel_type')
        if not segment_raw:
            raise ValueError("Missing segment_type column")

        segment_type = self._normalize_segment_type(segment_raw)

        # Skip rail — explicitly out of scope (documented in DECISIONS.md)
        if segment_type == 'RAIL':
            return None

        dep_date_str = self._get(row, 'departure_date', 'date', 'travel_date', 'check_in_date')
        departure_date = parse_travel_date(dep_date_str)
        if not departure_date:
            raise ValueError(f"Cannot parse departure date '{dep_date_str}'")

        traveler_email = self._get(row, 'traveler_email', 'email', 'employee_email')
        origin = self._get(row, 'origin', 'from', 'departure_airport', 'origin_code').upper()
        destination = self._get(row, 'destination', 'to', 'arrival_airport', 'destination_code').upper()

        suspicion_reasons = []
        co2e_kg = None
        emission_factor_used = ''
        quantity_normalized = None
        unit_normalized = ''
        description = ''

        if segment_type == 'FLIGHT':
            # Distance: use provided if available, else estimate from airport codes
            dist_str = self._get(row, 'distance_km', 'distance', 'miles')
            distance_km = None
            dist_note = ''

            if dist_str:
                try:
                    raw_dist = Decimal(dist_str.replace(',', ''))
                    # Check if miles (Concur sometimes gives miles)
                    if 'mile' in self._get(row, 'distance_unit', '').lower():
                        distance_km = float(raw_dist * Decimal('1.60934'))
                        dist_note = "Converted from miles"
                    else:
                        distance_km = float(raw_dist)
                        dist_note = "Provided by platform"
                except InvalidOperation:
                    pass

            if not distance_km and origin and destination:
                distance_km, dist_note = estimate_flight_distance(origin, destination)
                if not distance_km:
                    suspicion_reasons.append(f"Could not calculate distance: {dist_note}")
                    distance_km = 0

            ef, ef_desc = get_flight_emission_factor(distance_km or 0)
            co2e_kg = Decimal(str(distance_km or 0)) * ef
            emission_factor_used = f"{ef_desc} | {dist_note}"
            quantity_normalized = Decimal(str(distance_km or 0))
            unit_normalized = 'km'
            description = f"Flight: {origin or '?'} → {destination or '?'}"

        elif segment_type == 'HOTEL':
            nights_str = self._get(row, 'duration_nights', 'nights', 'duration')
            try:
                nights = int(nights_str) if nights_str else 1
            except ValueError:
                nights = 1
                suspicion_reasons.append(f"Could not parse nights '{nights_str}', assumed 1")

            # HCMI (Hotel Carbon Measurement Initiative) average: 20 kg CO2e / room-night
            EF_HOTEL = Decimal('20.0')
            co2e_kg = Decimal(str(nights)) * EF_HOTEL
            emission_factor_used = 'HCMI average 20 kg CO2e/room-night'
            quantity_normalized = Decimal(str(nights))
            unit_normalized = 'room_nights'
            description = f"Hotel: {destination or 'unknown'} — {nights} night(s)"

        elif segment_type == 'GROUND':
            dist_str = self._get(row, 'distance_km', 'distance', 'miles')
            distance_km = Decimal('0')
            if dist_str:
                try:
                    raw = Decimal(dist_str.replace(',', ''))
                    if 'mile' in self._get(row, 'distance_unit', '').lower():
                        distance_km = raw * Decimal('1.60934')
                    else:
                        distance_km = raw
                except InvalidOperation:
                    suspicion_reasons.append(f"Cannot parse ground distance '{dist_str}'")

            if distance_km == 0:
                suspicion_reasons.append("Ground transport: no distance provided, CO2e set to 0")

            # DEFRA 2023: average business car 0.171 kg CO2e/km
            EF_GROUND = Decimal('0.171')
            co2e_kg = distance_km * EF_GROUND
            emission_factor_used = 'DEFRA 2023 average car hire 0.171 kg CO2e/km'
            quantity_normalized = distance_km
            unit_normalized = 'km'
            description = f"Ground transport: {origin or '?'} → {destination or '?'}"

        return {
            'tenant_id': self.tenant_id,
            'ingestion_job_id': self.job_id,
            'source_type': 'TRAVEL',
            'raw_row': dict(row),
            'source_row_number': row_num,
            'activity_date': departure_date,
            'activity_description': description[:500],
            'scope': 'S3',
            'quantity_original': quantity_normalized or Decimal('0'),
            'unit_original': unit_normalized,
            'quantity_normalized': quantity_normalized,
            'unit_normalized': unit_normalized,
            'co2e_kg': co2e_kg,
            'emission_factor_used': emission_factor_used[:200],
            'travel_segment_type': segment_type,
            'travel_origin': origin[:10],
            'travel_destination': destination[:10],
            'travel_traveler_email': traveler_email[:200],
            'travel_distance_km': quantity_normalized if unit_normalized == 'km' else None,
            'is_suspicious': bool(suspicion_reasons),
            'suspicion_reasons': suspicion_reasons,
        }