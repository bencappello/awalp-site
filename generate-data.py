#!/usr/bin/env python3
"""Parse AWALP well CSVs and generate wells-data.js for the map prototype."""
import csv, re, json

def parse_coord(s, is_lon=False):
    """Parse DMS coordinate string to decimal degrees. Returns None if unparseable."""
    if not s or not s.strip() or s.strip() in ('?', '-', '0'):
        return None
    s = s.strip()

    # Extract hemisphere (N/S/E/W) from end
    m = re.search(r'([NSEWnsew])\s*$', s)
    if not m:
        return None
    hem = m.group(1).upper()
    s = s[:m.start()].strip()

    # Normalize separators — handle curly quotes, primes, and other variants
    s = s.replace('\u02b9', "'").replace('\u02ba', '"')  # ʹ ʺ (modifier primes)
    s = s.replace('\u2018', "'").replace('\u2019', "'")  # ' ' (curly single quotes)
    s = s.replace('\u201c', '"').replace('\u201d', '"')  # " " (curly double quotes)
    s = s.replace("''", '"')   # double single-quote = seconds
    s = s.replace(',', '.')    # comma decimal

    deg = mins = secs = 0.0

    if '\u00b0' in s:  # ° present
        parts = s.split('\u00b0', 1)
        try:
            deg = float(parts[0].strip())
        except ValueError:
            return None
        rest = parts[1].strip().lstrip('.')  # handle °. artifact
        if "'" in rest:
            p2 = rest.split("'", 1)
            try:
                mins = float(p2[0].strip()) if p2[0].strip() else 0
            except ValueError:
                return None
            sec_s = p2[1].strip().rstrip('"\'').strip()
            if sec_s:
                try:
                    secs = float(sec_s)
                except ValueError:
                    pass
        else:
            val = rest.rstrip('"\'').strip()
            if val:
                try:
                    mins = float(val)
                except ValueError:
                    pass
    elif "'" in s:
        # No degree symbol — 0 likely replaces °
        idx = s.index("'")
        before = s[:idx].replace(' ', '').replace('.', '')
        after = s[idx+1:].strip().rstrip('"\'').strip()

        if is_lon:
            if len(before) < 2:
                return None
            try:
                deg = float(before[:2])
            except ValueError:
                return None
            mr = before[2:]
            if mr.startswith('0'):
                mr = mr[1:]
            if mr:
                try:
                    mins = float(mr)
                except ValueError:
                    return None
        else:
            if not before:
                return None
            if before.startswith('00') and len(before) > 2:
                deg = 0.0
                mr = before[2:]
                if mr.startswith('0'):
                    mr = mr[1:]
            else:
                try:
                    deg = float(before[0])
                except ValueError:
                    return None
                mr = before[1:]
                if mr.startswith('0'):
                    mr = mr[1:]
            if mr:
                try:
                    mins = float(mr)
                except ValueError:
                    return None
        if after:
            try:
                secs = float(after)
            except ValueError:
                pass
    else:
        return None

    # Validate
    if mins >= 60 or secs >= 60 or deg < 0:
        return None
    if not is_lon and deg > 90:
        return None
    if is_lon and deg > 180:
        return None

    decimal = deg + mins / 60.0 + secs / 3600.0
    if hem in ('S', 'W'):
        decimal = -decimal

    # Sanity: East Africa region
    if not is_lon and not (-5 < decimal < 2):
        return None
    if is_lon and not (28 < decimal < 36):
        return None

    return round(decimal, 6)


def clean_num(s):
    s = str(s).strip().replace(',', '').replace(' ', '')
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0

def clean_str(s):
    return str(s).strip() if s else ''

def col(row, i):
    return clean_str(row[i]) if i < len(row) else ''


def parse_new_wells(filepath):
    wells = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    for row in rows[3:]:
        if len(row) < 10:
            continue
        wn = col(row, 0)
        if not wn or not wn.startswith('N'):
            continue

        village = re.sub(r'\s*\*+\s*$', '', col(row, 1))
        lat = parse_coord(col(row, 5), is_lon=False)
        lng = parse_coord(col(row, 6), is_lon=True)
        active = col(row, 2).upper() == 'YES'
        served = clean_num(col(row, 4))

        depth_ft = col(row, 13)
        depth_m = col(row, 14)
        dp = []
        if depth_ft and depth_ft not in ('?', '-', '0'):
            dp.append(f"{depth_ft} ft")
        if depth_m and depth_m not in ('?', '-', '0'):
            try:
                mv = float(depth_m)
                dp.append(f"{mv:.0f} m" if mv == int(mv) else f"{mv:.1f} m")
            except ValueError:
                dp.append(f"{depth_m} m")

        wells.append({
            'w': wn, 'v': village, 'a': active, 's': served,
            'lt': lat, 'ln': lng,
            'di': col(row, 7), 're': col(row, 8),
            'dt': col(row, 10), 'pt': col(row, 12),
            'dp': ' / '.join(dp),
            'dTo': col(row, 27), 'dBy': col(row, 28),
            'c': col(row, 29),
        })
    return wells


def parse_repaired_wells(filepath):
    wells = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    for row in rows[4:]:
        if len(row) < 10:
            continue
        wn = col(row, 0)
        village = col(row, 1)
        active_s = col(row, 2).upper()
        if not village or active_s != 'YES':
            continue

        village = re.sub(r'\s*-+\s*NO DATA SHEET.*$', '', village, flags=re.IGNORECASE).strip()
        lat = parse_coord(col(row, 6), is_lon=False)
        lng = parse_coord(col(row, 7), is_lon=True)
        served = clean_num(col(row, 5))
        depth_ft = col(row, 15)
        dp = f"{depth_ft} ft" if depth_ft and depth_ft not in ('?', '-', '') else ''

        wells.append({
            'w': wn if wn != 'xxxxx' else '', 'v': village, 'a': True, 's': served,
            'lt': lat, 'ln': lng,
            'di': col(row, 8), 're': col(row, 9),
            'dt': col(row, 11), 'pt': col(row, 14) or col(row, 12),
            'dp': dp, 'rd': col(row, 16),
            'dTo': col(row, 19), 'dBy': col(row, 20),
            'c': col(row, 29),
        })
    return wells


base = '/Users/Ben/engineering_projects/awalp-site/'
new = parse_new_wells(base + 'Well Database 2025-03-06.xlsx - New Wells.csv')
rep = parse_repaired_wells(base + 'Well Database 2025-03-06.xlsx - Repaired Wells.csv')

nc = sum(1 for w in new if w['lt'] is not None)
rc = sum(1 for w in rep if w['lt'] is not None)
print(f"New wells: {len(new)} total, {nc} with coords")
print(f"Repaired wells: {len(rep)} total, {rc} with coords")

with open(base + 'wells-data.js', 'w', encoding='utf-8') as f:
    f.write('// AWALP Well Data — auto-generated by generate-data.py\n')
    f.write('// Fields: w=wellNum, v=village, a=active, s=served, lt=lat, ln=lng,\n')
    f.write('//   di=district, re=region, dt=date, pt=pumpType, dp=depth,\n')
    f.write('//   dTo=dedicatedTo, dBy=dedicatedBy, c=comments, rd=repairDesc\n\n')
    f.write('const NEW_WELLS = ')
    json.dump(new, f, ensure_ascii=False)
    f.write(';\n\nconst REPAIRED_WELLS = ')
    json.dump(rep, f, ensure_ascii=False)
    f.write(';\n')

print(f"Wrote wells-data.js ({len(new)} new, {len(rep)} repaired)")
