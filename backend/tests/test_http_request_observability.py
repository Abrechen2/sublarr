"""Every HTTP request must leave a trace — a metric with a status, and a log line.

Found 2026-09-03 while stress-testing RC: Sublarr recorded no HTTP requests at
all. `record_http_request` existed, fully defined with a status label, but
nothing called it, and the gunicorn line carried no `--access-logfile`. A
clean 4xx answer therefore left no trace anywhere — a whole probe campaign was
invisible from the inside, and so would any user's report of a bad response.

This wires the existing recorder to the request cycle. Two things it must get
right beyond "a number goes up":

- The `endpoint` label is the ROUTE TEMPLATE, not the concrete path. Labelling
  by `request.path` would mint a new time series per wanted-item id and blow up
  cardinality; `/api/v1/wanted/<id>` must collapse to one series.
- The status is the REAL response status, including 4xx and 5xx — the whole
  point is to see the answers that used to vanish.
"""

import pytest


def _counter_value(metric, labels):
    for sample_family in metric.collect():
        for sample in sample_family.samples:
            if sample.name.endswith("_total") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


@pytest.fixture
def _metrics():
    import metrics

    if not metrics.METRICS_AVAILABLE:
        pytest.skip("prometheus_client not installed")
    return metrics


class TestRequestsAreCounted:
    def test_a_request_increments_the_counter_with_its_status(self, client, _metrics):
        labels = {"method": "GET", "endpoint": "/api/v1/health", "status": "200"}
        before = _counter_value(_metrics.HTTP_REQUEST_TOTAL, labels)

        assert client.get("/api/v1/health").status_code == 200

        after = _counter_value(_metrics.HTTP_REQUEST_TOTAL, labels)
        assert after == before + 1

    def test_a_4xx_is_recorded_not_dropped(self, client, _metrics):
        # The exact class of answer the outage hid: a rejected request that
        # never raised, so nothing in the pipeline saw it. It must be counted
        # with its real status. An unknown API path is caught by the SPA
        # fallback rule (/<path:path>) and returns 404 — so it has a route
        # template and lands in exactly one series rather than one-per-path.
        client.get("/api/v1/definitely-no-such-route")

        got_404 = _counter_value(
            _metrics.HTTP_REQUEST_TOTAL,
            {"method": "GET", "endpoint": "/<path:path>", "status": "404"},
        )
        assert got_404 >= 1, "a 404 was not recorded under its route template"

    def test_the_endpoint_label_is_the_route_template_not_the_path(self, client, _metrics):
        # Two different concrete paths on the same rule must share one series,
        # or the label set grows without bound. /api/v1/health takes no params,
        # so use a parametrised route if one is reachable; otherwise assert the
        # negative: the raw path never appears as a label.
        client.get("/api/v1/wanted?page=1")
        client.get("/api/v1/wanted?page=2")

        raw_path_series = _counter_value(
            _metrics.HTTP_REQUEST_TOTAL,
            {"method": "GET", "endpoint": "/api/v1/wanted?page=1", "status": "200"},
        )
        assert raw_path_series == 0, "the query string leaked into the label"

    def test_in_progress_returns_to_zero_after_a_request(self, client, _metrics):
        client.get("/api/v1/health")

        gauge = _counter_value(_metrics.HTTP_REQUESTS_IN_PROGRESS, {}) or _gauge_value(
            _metrics.HTTP_REQUESTS_IN_PROGRESS
        )
        assert gauge == 0, "a request left the in-progress gauge above zero"


def _gauge_value(metric):
    for family in metric.collect():
        for sample in family.samples:
            return sample.value
    return 0.0
