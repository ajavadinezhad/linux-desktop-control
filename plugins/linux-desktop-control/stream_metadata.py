"""Sanitized stream metadata diagnostics; these never establish input authority."""
import math


def _pair(value, minimum):
    if type(value) not in (list, tuple) or len(value) != 2:
        return None
    if not all(type(item) in (int, float) and minimum <= item <= 1_000_000
               and math.isfinite(item) for item in value):
        return None
    return list(value)


def diagnostic_stream_metadata(props):
    """Copy only bounded geometry, a known source enum and mapping-id presence.

    Unknown properties, identifiers and malformed values are omitted. Absence of
    a field is not a fallback or capability assertion. Callers must not use this
    diagnostic as validation or authorization for a pointer coordinate adapter.
    """
    if type(props) is not dict:
        return {}
    result = {}
    for name, minimum in (('position', -1_000_000), ('size', 1),
                          ('logical_size', 1)):
        pair = _pair(props.get(name), minimum)
        if pair is not None:
            result[name] = pair
    source_type = props.get('source_type')
    if type(source_type) is int and source_type in (1, 2, 4):
        result['source_type'] = source_type
    result['mapping_id_present'] = 'mapping_id' in props
    return result
