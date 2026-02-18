from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.models import ManualLeadCreateRequest, SourceChannel
from backend.app.store import InMemoryStore


def test_manual_lead_write_and_read_concurrent() -> None:
    store = InMemoryStore()
    read_errors: list[Exception] = []

    def writer(index: int) -> None:
        request = ManualLeadCreateRequest(
            source_channel=SourceChannel.walk_in,
            name=f"Candidate {index}",
            phone=f"90000{index:05d}"[-10:],
            notes="concurrency-test",
        )
        store.create_manual_lead(request)

    def reader() -> None:
        for _ in range(300):
            try:
                store.list_manual_leads(limit=100)
            except Exception as exc:  # pragma: no cover - regression trap
                read_errors.append(exc)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(writer, i) for i in range(300)]
        futures.extend(executor.submit(reader) for _ in range(4))
        for future in futures:
            future.result()

    assert not read_errors

