"""Level 2: a real ClickHouse in a container (testcontainers). Never in `gate-fast` (RULES §3.10): 10-40 s
of startup, and on macOS the first place things break. It runs in `make test-int` and in `make done`.

The image is pinned by DIGEST (R18): a tag moves, a digest does not. 26.4 is STACK.md §3's recommendation.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import clickhouse_connect
import pytest
from testcontainers.community.clickhouse import ClickHouseContainer

from evalgate.telemetry.exporters import StoreClient
from evalgate.telemetry.migrations import apply

CLICKHOUSE_IMAGE = (
    "clickhouse/clickhouse-server@sha256:c7796a1335d14385c052f10061cf719f4a368a908432ec25980860b1333e9ccd"
)


@dataclass
class Store:
    container: ClickHouseContainer
    dsn: str

    def connect(self) -> StoreClient:
        client: StoreClient = clickhouse_connect.get_client(
            dsn=self.dsn, connect_timeout=2, send_receive_timeout=5
        )
        return client

    def count(self, service: str) -> int:
        client: Any = self.connect()
        try:
            rows = client.query(
                "SELECT count() FROM otel_traces WHERE ServiceName = {service:String}",
                parameters={"service": service},
            ).result_rows
        finally:
            client.close()
        return int(rows[0][0])

    def kill(self) -> None:
        """Not `stop()`: a stop is a graceful shutdown. A store that dies does not say goodbye."""
        self.container.get_wrapped_container().kill()


@pytest.fixture(scope="module")
def store() -> Iterator[Store]:
    """One container per test module: the degradation test kills its own, and nobody else may share it."""
    with ClickHouseContainer(CLICKHOUSE_IMAGE) as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(8123)
        found = Store(container, f"http://{container.username}:{container.password}@{host}:{port}/default")
        migrator = found.connect()
        try:
            apply(migrator)
        finally:
            migrator.close()
        yield found
