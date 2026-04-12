#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Sample a ListenBrainz .listens shard and estimate row size plus parse/hash throughput.'
    )
    parser.add_argument('path', help='Path to a .listens shard file')
    parser.add_argument(
        '--sample-rows',
        type=int,
        default=100_000,
        help='Number of non-empty rows to sample (default: 100000)',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f'File not found: {path}')

    sample_rows = max(1, int(args.sample_rows))
    bytes_read = 0
    rows = 0
    start = time.perf_counter()

    with path.open('rb') as handle:
        for raw in handle:
            if not raw.strip():
                continue

            bytes_read += len(raw)
            record = json.loads(raw)

            # Approximate the current ingest hot path by exercising the same broad
            # JSON decode + hash generation shape without touching Django/ORM.
            user_name = str(record.get('user_name') or record.get('user_id') or '')
            listened_at = record.get('listened_at') or record.get('timestamp') or 0
            track_metadata = record.get('track_metadata') or {}
            additional_info = track_metadata.get('additional_info') or {}
            mbid_mapping = track_metadata.get('mbid_mapping') or {}

            source_user_id = hashlib.sha256(f'listenbrainz:{user_name}'.encode('utf-8')).hexdigest()
            event_parts = [
                'listenbrainz',
                source_user_id,
                str(int(listened_at)),
                str(mbid_mapping.get('recording_mbid') or additional_info.get('recording_mbid') or ''),
                str(track_metadata.get('recording_msid') or additional_info.get('recording_msid') or ''),
                str(additional_info.get('spotify_id') or additional_info.get('spotify_track_id') or ''),
                str(track_metadata.get('track_name') or '').casefold().strip(),
                str(track_metadata.get('artist_name') or '').casefold().strip(),
            ]
            hashlib.sha256('\x1f'.join(event_parts).encode('utf-8')).digest()

            rows += 1
            if rows >= sample_rows:
                break

    elapsed = max(time.perf_counter() - start, 1e-9)
    avg_bytes_per_row = bytes_read / rows
    estimated_rows = int(path.stat().st_size / avg_bytes_per_row)

    print(f'path={path}')
    print(f'sampled_rows={rows}')
    print(f'file_size_bytes={path.stat().st_size}')
    print(f'bytes_read={bytes_read}')
    print(f'avg_bytes_per_row={avg_bytes_per_row:.2f}')
    print(f'estimated_total_rows={estimated_rows}')
    print(f'rows_per_second={rows / elapsed:.2f}')
    print(f'mib_per_second={bytes_read / elapsed / (1024 * 1024):.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
