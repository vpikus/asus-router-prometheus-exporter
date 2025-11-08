from typing import Iterable, Mapping

from prometheus_client import Gauge

def set_onehot_enum(
    gauge: Gauge,
    base_labels: Mapping[str, str],
    enum_values: Iterable,
    current_value,
    extra_label_name: str,
    get_label_value=lambda e: getattr(e, "value", getattr(e, "name", str(e))),
):
    for e in enum_values:
        labels = dict(base_labels)
        labels[extra_label_name] = get_label_value(e)
        gauge.labels(**labels).set(1 if e == current_value else 0)

def zero_onehot_enum(
    gauge: Gauge,
    base_labels: Mapping[str, str],
    enum_values: Iterable,
    extra_label_name: str,
    get_label_value=lambda e: getattr(e, "value", getattr(e, "name", str(e))),
):
    for e in enum_values:
        labels = dict(base_labels)
        labels[extra_label_name] = get_label_value(e)
        gauge.labels(**labels).set(0)
