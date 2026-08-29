"""Canonical safe evidence querying over frozen datasets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from numbers import Number
from typing import Any

from spire.core import ScopeMismatchError
from spire.interfaces import DATASET_SCHEMAS, DatasetSchema, EvidenceQueryRequest

from .resolver import DatasetResolver
from .snapshot import AccountSnapshotService

DERIVED_METRICS = frozenset({"ctr", "cpc_micros", "cpa_micros"})
SHARE_METRICS = frozenset(
    {
        "search_impression_share",
        "search_top_impression_share",
        "search_absolute_top_impression_share",
        "search_rank_lost_impression_share",
        "search_budget_lost_impression_share",
    }
)
SUM_METRICS = frozenset({"impressions", "clicks", "cost_micros", "conversions", "conversions_value"})


class EvidenceQueryService:
    """Resolve, validate, filter, aggregate, and provenance-stamp evidence."""

    def __init__(self, workspace, *, snapshots: AccountSnapshotService | None = None) -> None:
        self.workspace = workspace
        self.snapshots = snapshots or AccountSnapshotService(workspace)

    def query(self, request: EvidenceQueryRequest | Mapping[str, Any]) -> dict[str, Any]:
        request = _request(request)
        schema = _validate_request(request)
        snapshot = self.snapshots.current(request.customer_id, campaign_ids=request.campaign_ids)
        limitations: list[str] = []
        if request.date_range is not None:
            declared_range = snapshot.scope.get("date_range")
            if declared_range is None:
                raise ScopeMismatchError("EVIDENCE_DATE_RANGE_NOT_CERTIFIED")
            if (
                request.date_range.start < str(declared_range.get("start"))
                or request.date_range.end > str(declared_range.get("end"))
            ):
                raise ScopeMismatchError("EVIDENCE_DATE_RANGE_NOT_CERTIFIED")

        resolver = DatasetResolver(self.workspace, request.customer_id)
        try:
            resolved = resolver.resolve_dataset(
                snapshot.extraction_id,
                request.dataset,
                campaign_ids=request.campaign_ids,
            )
        except ScopeMismatchError as exc:
            limitations.append(str(exc))
            return _response(request, snapshot, schema, (), (), limitations)

        rows = [row for row in resolved.rows if _row_in_scope(row, request)]
        rows = [row for row in rows if _matches_filters(row, request.filters)]
        selected_metrics = _selected_metrics(request, schema)
        selected_dimensions = tuple(request.dimensions)
        projected = [_project(row, selected_dimensions, selected_metrics) for row in rows]
        projected = _ordered(projected, request.order_by)
        aggregates = _aggregate(rows, selected_dimensions, selected_metrics)
        aggregates = _ordered(aggregates, request.order_by)[: request.limit]
        if len(projected) > request.limit:
            limitations.append(f"row limit applied: {request.limit}")
        if resolved.state.value == "EMPTY":
            limitations.append("dataset is EMPTY in the finalized extraction")
        return _response(
            request,
            snapshot,
            schema,
            tuple(projected[: request.limit]),
            tuple(aggregates),
            limitations,
            dataset_hash=resolved.content_hash,
        )


def evidence_query(
    service: EvidenceQueryService, request: EvidenceQueryRequest | Mapping[str, Any]
) -> dict[str, Any]:
    """Canonical capability entry point for external adapters."""

    return service.query(request)


def _request(value: EvidenceQueryRequest | Mapping[str, Any]) -> EvidenceQueryRequest:
    if isinstance(value, EvidenceQueryRequest):
        return value
    payload = dict(value)
    date_range = payload.get("date_range")
    if date_range is not None and not hasattr(date_range, "start"):
        from spire.interfaces import DateRange

        date_range = DateRange(**date_range) if isinstance(date_range, Mapping) else DateRange(*date_range)
        payload["date_range"] = date_range
    return EvidenceQueryRequest(**payload)


def _validate_request(request: EvidenceQueryRequest) -> DatasetSchema:
    schema = DATASET_SCHEMAS.get(request.dataset)
    if schema is None:
        raise ValueError(f"UNKNOWN_EVIDENCE_DATASET:{request.dataset}")
    invalid_dimensions = set(request.dimensions) - set(schema.dimensions)
    invalid_metrics = set(request.metrics) - set(schema.metrics) - DERIVED_METRICS
    invalid_filters = set(request.filters) - set(schema.dimensions) - set(schema.metrics)
    if invalid_dimensions:
        raise ValueError(f"UNKNOWN_EVIDENCE_DIMENSIONS:{sorted(invalid_dimensions)}")
    if invalid_metrics:
        raise ValueError(f"UNKNOWN_EVIDENCE_METRICS:{sorted(invalid_metrics)}")
    if invalid_filters:
        raise ValueError(f"UNKNOWN_EVIDENCE_FILTERS:{sorted(invalid_filters)}")
    for field, value in request.filters.items():
        if isinstance(value, Mapping):
            raise TypeError(f"COMPLEX_FILTER_NOT_ALLOWED:{field}")
    if request.order_by:
        allowed_order = set(request.dimensions) | set(request.metrics) | set(schema.metrics)
        invalid_order = {
            field.removeprefix("-")
            for field in request.order_by
        } - allowed_order - DERIVED_METRICS
        if invalid_order:
            raise ValueError(f"UNKNOWN_EVIDENCE_ORDER_FIELDS:{sorted(invalid_order)}")
    return schema


def _selected_metrics(request: EvidenceQueryRequest, schema: DatasetSchema) -> tuple[str, ...]:
    return request.metrics or schema.metrics


def _row_in_scope(row: Mapping[str, Any], request: EvidenceQueryRequest) -> bool:
    if str(row.get("campaign_id")) not in request.campaign_ids:
        return False
    if request.date_range is None or "date" not in row or row.get("date") is None:
        return True
    return request.date_range.start <= str(row["date"]) <= request.date_range.end


def _matches_filters(row: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for field, wanted in filters.items():
        actual = row.get(field)
        if isinstance(wanted, (list, tuple, set, frozenset)):
            if actual not in wanted:
                return False
        elif actual != wanted and str(actual) != str(wanted):
            return False
    return True


def _project(row: Mapping[str, Any], dimensions: Iterable[str], metrics: Iterable[str]) -> dict[str, Any]:
    result = {field: row.get(field) for field in dimensions}
    result.update({field: _metric_value(row, field) for field in metrics})
    return result


def _aggregate(
    rows: list[Mapping[str, Any]], dimensions: tuple[str, ...], metrics: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in dimensions)
        groups.setdefault(key, []).append(row)
    result: list[dict[str, Any]] = []
    for key, members in groups.items():
        item = dict(zip(dimensions, key))
        for metric in metrics:
            item[metric] = _aggregate_metric(members, metric)
        result.append(item)
    return result


def _aggregate_metric(rows: list[Mapping[str, Any]], metric: str) -> Any:
    if metric in DERIVED_METRICS:
        totals = {name: _aggregate_metric(rows, name) for name in SUM_METRICS}
        if metric == "ctr":
            return _ratio(totals["clicks"], totals["impressions"])
        if metric == "cpc_micros":
            return _ratio(totals["cost_micros"], totals["clicks"])
        return _ratio(totals["cost_micros"], totals["conversions"])
    values = [_numeric(row.get(metric)) for row in rows if _numeric(row.get(metric)) is not None]
    if not values:
        return None
    if metric in SHARE_METRICS:
        return sum(values) / len(values)
    if metric == "conversions":
        return sum(values)
    return int(sum(values)) if metric in SUM_METRICS or metric.endswith("_micros") else sum(values)


def _metric_value(row: Mapping[str, Any], metric: str) -> Any:
    if metric in DERIVED_METRICS:
        return _aggregate_metric([row], metric)
    return row.get(metric)


def _ordered(rows: list[dict[str, Any]], order_by: str | tuple[str, ...] | None) -> list[dict[str, Any]]:
    if not order_by:
        return rows
    fields = (order_by,) if isinstance(order_by, str) else order_by
    result = list(rows)
    for raw_field in reversed(fields):
        descending = raw_field.startswith("-")
        field = raw_field[1:] if descending else raw_field
        result.sort(key=lambda row: _sort_key(row.get(field)), reverse=descending)
    return result


def _sort_key(value: Any) -> tuple[int, Any]:
    return (value is None, value if value is not None else "")


def _numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Number):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("NON_NUMERIC_EVIDENCE_METRIC")


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _response(
    request: EvidenceQueryRequest,
    snapshot,
    schema: DatasetSchema,
    rows: tuple[dict[str, Any], ...],
    aggregates: tuple[dict[str, Any], ...],
    limitations: list[str],
    *,
    dataset_hash: str | None = None,
) -> dict[str, Any]:
    selected_metrics = _selected_metrics(request, schema)
    selected_dimensions = tuple(request.dimensions)
    evidence_ref = f"{snapshot.extraction_id}:{request.dataset}:{dataset_hash or 'unavailable'}"
    return {
        "rows": list(rows),
        "aggregates": list(aggregates),
        "schema": {
            "dataset": request.dataset,
            "dimensions": list(selected_dimensions),
            "metrics": list(selected_metrics),
            "available_dimensions": list(schema.dimensions),
            "available_metrics": list(schema.metrics) + sorted(DERIVED_METRICS),
        },
        "scope": {
            "customer_id": request.customer_id,
            "campaign_ids": list(request.campaign_ids),
            "extraction_id": snapshot.extraction_id,
            "scope_fingerprint": snapshot.scope.get("scope_fingerprint"),
            "date_range": {
                "start": request.date_range.start,
                "end": request.date_range.end,
            }
            if request.date_range
            else None,
        },
        "freshness": dict(snapshot.freshness),
        "evidence_ref": evidence_ref,
        "limitations": limitations,
    }
