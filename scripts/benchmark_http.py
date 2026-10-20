"""Small staging-only HTTP benchmark; no production requests are made by default."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import math
import statistics
import time
from urllib.parse import urlsplit


def sample(url, timeout):
    parsed = urlsplit(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    start = time.perf_counter()
    try:
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        connection.request('GET', path, headers={'User-Agent': 'LMS-staging-benchmark/1.0'})
        response = connection.getresponse()
        headers_elapsed = time.perf_counter() - start
        # Includes transfer in total/RPS without keeping the full response in RAM.
        while response.read(64 * 1024):
            pass
        return {'status': response.status, 'headers_seconds': headers_elapsed,
                'total_seconds': time.perf_counter() - start,
                'cache': response.getheader('X-Cache-Status', 'unknown')}
    except Exception:
        return {'status': 'transport_error', 'total_seconds': time.perf_counter() - start,
                'cache': 'unknown'}
    finally:
        connection.close()


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--requests', type=int, default=50)
    parser.add_argument('--concurrency', type=int, default=5)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        parser.error('Use an http(s) URL without credentials.')
    if not (1 <= args.requests <= 1000 and 1 <= args.concurrency <= 50 and
            0 <= args.warmup <= 20 and 0 < args.timeout <= 120):
        parser.error('requests 1..1000, concurrency 1..50, warmup 0..20, timeout (0,120].')
    for _ in range(args.warmup):
        sample(args.url, args.timeout)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: sample(args.url, args.timeout), range(args.requests)))
    elapsed = time.perf_counter() - started
    successes = [row for row in results if isinstance(row['status'], int) and 200 <= row['status'] < 300]
    times = [row['headers_seconds'] * 1000 for row in successes]
    print(json.dumps({
        'requests': args.requests, 'concurrency': args.concurrency, 'elapsed_seconds': round(elapsed, 3),
        'successful_requests': len(successes), 'successful_rps': round(len(successes) / elapsed, 2),
        'statuses': dict(Counter(str(row['status']) for row in results)),
        'cache_statuses': dict(Counter(row['cache'] for row in results)),
        # Header time includes DNS/TCP/TLS and full headers, not server compute alone.
        'headers_p50_ms': round(statistics.median(times), 2) if times else None,
        'headers_p95_ms': round(percentile(times, .95), 2) if times else None,
    }, indent=2))
    return 0 if len(successes) == args.requests else 1


if __name__ == '__main__':
    raise SystemExit(main())
