#!/usr/bin/env python3
"""Pressure test Wenjin run lifecycle endpoints.

Examples:
  python scripts/run_pressure.py \
      --base-url http://localhost:2026 \
      --email admin@example.com \
      --password '***' \
      --runs 40 --concurrency 8 --mode wait

  python scripts/run_pressure.py \
      --base-url http://localhost:2026 \
      --token "$WENJIN_ACCESS_TOKEN" \
      --runs 20 --concurrency 4 --mode stream
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ApiError(Exception):
    status_code: int
    detail: str
    body: str

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.detail}"


@dataclass
class RunSample:
    run_index: int
    thread_id: str
    mode: str
    ok: bool
    latency_seconds: float
    ttfb_seconds: float | None = None
    status_code: int | None = None
    outcome: str = ""
    error: str | None = None


@dataclass
class StreamResult:
    ended: bool
    ttfb_seconds: float | None
    events: int
    error_events: int
    last_outcome: str


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _safe_json_load(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _build_headers(token: str | None, accept: str = "application/json") -> dict[str, str]:
    headers = {
        "Accept": accept,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(
    *,
    method: str,
    url: str,
    token: str | None,
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    body = None
    headers = _build_headers(token)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status_code = int(response.getcode())
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
        data = _safe_json_load(raw)
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("detail") or "").strip()
        raise ApiError(
            status_code=status_code,
            detail=detail or f"request to {url} failed",
            body=raw,
        ) from exc

    parsed = _safe_json_load(raw)
    if not isinstance(parsed, dict):
        raise ApiError(
            status_code=status_code,
            detail=f"expected JSON object from {url}",
            body=raw,
        )
    return status_code, parsed


def _post_stream(
    *,
    url: str,
    token: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> StreamResult:
    req = urllib.request.Request(
        url=url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **_build_headers(token, accept="text/event-stream"),
            "Content-Type": "application/json",
        },
    )

    try:
        response = urllib.request.urlopen(req, timeout=timeout_seconds)
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
        data = _safe_json_load(raw)
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("detail") or "").strip()
        raise ApiError(
            status_code=status_code,
            detail=detail or f"stream request to {url} failed",
            body=raw,
        ) from exc

    started_at = time.perf_counter()
    first_event_at: float | None = None
    event_name = ""
    data_lines: list[str] = []
    events = 0
    error_events = 0
    ended = False
    last_outcome = "stream_closed"

    with response:
        while True:
            raw_line = response.readline()
            if raw_line == b"":
                break

            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if not event_name and not data_lines:
                    continue

                events += 1
                if first_event_at is None and event_name != "heartbeat":
                    first_event_at = time.perf_counter()

                data_text = "\n".join(data_lines).strip()
                payload_obj = _safe_json_load(data_text) if data_text else None

                if event_name == "error":
                    error_events += 1
                    last_outcome = "error"
                elif event_name == "end":
                    ended = True
                    last_outcome = "completed"
                    break
                elif isinstance(payload_obj, dict):
                    payload_type = str(payload_obj.get("type") or "").strip()
                    if payload_type:
                        last_outcome = payload_type
                    payload_status = str(payload_obj.get("status") or "").strip()
                    if payload_status:
                        last_outcome = payload_status

                event_name = ""
                data_lines = []
                continue

            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())

    ttfb_seconds = None
    if first_event_at is not None:
        ttfb_seconds = first_event_at - started_at

    return StreamResult(
        ended=ended,
        ttfb_seconds=ttfb_seconds,
        events=events,
        error_events=error_events,
        last_outcome=last_outcome,
    )


def _login(base_url: str, email: str, password: str, timeout_seconds: float) -> str:
    _, payload = _request_json(
        method="POST",
        url=f"{base_url}/api/auth/login",
        token=None,
        payload={"email": email, "password": password},
        timeout_seconds=timeout_seconds,
    )
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("login succeeded but access_token is missing")
    return token


def _create_thread(
    *,
    base_url: str,
    token: str,
    workspace_id: str | None,
    model: str | None,
    skill: str | None,
    timeout_seconds: float,
    title: str,
) -> str:
    payload: dict[str, Any] = {
        "title": title,
    }
    if workspace_id:
        payload["workspace_id"] = workspace_id
    if model:
        payload["model"] = model
    if skill:
        payload["skill"] = skill

    _, thread = _request_json(
        method="POST",
        url=f"{base_url}/api/threads",
        token=token,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    thread_id = str(thread.get("id") or "").strip()
    if not thread_id:
        raise RuntimeError("create thread succeeded but id is missing")
    return thread_id


def _delete_thread(base_url: str, token: str, thread_id: str, timeout_seconds: float) -> None:
    try:
        _request_json(
            method="DELETE",
            url=f"{base_url}/api/threads/{thread_id}",
            token=token,
            payload=None,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        return


def _build_run_payload(args: argparse.Namespace, run_index: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": f"{args.prompt.strip()} [bench#{run_index}]",
        "on_disconnect": "continue",
        "multitask_strategy": "reject",
    }
    if args.workspace_id:
        payload["workspace_id"] = args.workspace_id
    if args.model:
        payload["model"] = args.model
    if args.skill:
        payload["skill"] = args.skill
    return payload


def _run_once(
    *,
    run_index: int,
    args: argparse.Namespace,
    base_url: str,
    token: str,
    thread_id: str,
) -> RunSample:
    started_at = time.perf_counter()

    try:
        payload = _build_run_payload(args, run_index)
        if args.mode == "wait":
            status_code, response_payload = _request_json(
                method="POST",
                url=f"{base_url}/api/threads/{thread_id}/runs/wait",
                token=token,
                payload=payload,
                timeout_seconds=args.timeout,
            )
            run_status = str(response_payload.get("status") or "").strip() or "unknown"
            ok = status_code == 200 and run_status in {"completed", "success"}
            return RunSample(
                run_index=run_index,
                thread_id=thread_id,
                mode=args.mode,
                ok=ok,
                latency_seconds=time.perf_counter() - started_at,
                status_code=status_code,
                outcome=run_status,
                error=None if ok else f"status={run_status}",
            )

        stream_result = _post_stream(
            url=f"{base_url}/api/threads/{thread_id}/runs/stream",
            token=token,
            payload=payload,
            timeout_seconds=args.timeout,
        )
        ok = stream_result.ended and stream_result.error_events == 0
        return RunSample(
            run_index=run_index,
            thread_id=thread_id,
            mode=args.mode,
            ok=ok,
            latency_seconds=time.perf_counter() - started_at,
            ttfb_seconds=stream_result.ttfb_seconds,
            status_code=200,
            outcome=stream_result.last_outcome,
            error=None if ok else f"events={stream_result.events}, errors={stream_result.error_events}",
        )

    except ApiError as exc:
        return RunSample(
            run_index=run_index,
            thread_id=thread_id,
            mode=args.mode,
            ok=False,
            latency_seconds=time.perf_counter() - started_at,
            status_code=exc.status_code,
            outcome=f"http_{exc.status_code}",
            error=exc.detail,
        )
    except Exception as exc:  # pragma: no cover - fallback
        return RunSample(
            run_index=run_index,
            thread_id=thread_id,
            mode=args.mode,
            ok=False,
            latency_seconds=time.perf_counter() - started_at,
            status_code=None,
            outcome="exception",
            error=str(exc),
        )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * percentile
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]

    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _build_summary(
    *,
    samples: list[RunSample],
    wall_seconds: float,
    args: argparse.Namespace,
    thread_ids: list[str],
) -> dict[str, Any]:
    success = [sample for sample in samples if sample.ok]
    failed = [sample for sample in samples if not sample.ok]
    latencies = [sample.latency_seconds for sample in success]
    ttfb = [sample.ttfb_seconds for sample in success if sample.ttfb_seconds is not None]

    outcomes: dict[str, int] = {}
    errors: dict[str, int] = {}
    for sample in samples:
        outcomes[sample.outcome] = outcomes.get(sample.outcome, 0) + 1
        if sample.error:
            errors[sample.error] = errors.get(sample.error, 0) + 1

    failure_samples: list[dict[str, Any]] = []
    for item in failed[: min(8, len(failed))]:
        failure_samples.append(
            {
                "run_index": item.run_index,
                "thread_id": item.thread_id,
                "status_code": item.status_code,
                "outcome": item.outcome,
                "error": item.error,
            }
        )

    return {
        "mode": args.mode,
        "base_url": args.base_url,
        "runs": len(samples),
        "concurrency": args.concurrency,
        "threads_used": len(thread_ids),
        "success": len(success),
        "failed": len(failed),
        "success_rate": (len(success) / len(samples)) if samples else 0.0,
        "throughput_rps": (len(samples) / wall_seconds) if wall_seconds > 0 else 0.0,
        "wall_seconds": wall_seconds,
        "latency_seconds": {
            "min": min(latencies) if latencies else None,
            "mean": statistics.fmean(latencies) if latencies else None,
            "p50": _percentile(latencies, 0.50) if latencies else None,
            "p90": _percentile(latencies, 0.90) if latencies else None,
            "p95": _percentile(latencies, 0.95) if latencies else None,
            "p99": _percentile(latencies, 0.99) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "ttfb_seconds": {
            "p50": _percentile(ttfb, 0.50) if ttfb else None,
            "p95": _percentile(ttfb, 0.95) if ttfb else None,
            "max": max(ttfb) if ttfb else None,
        },
        "outcomes": dict(sorted(outcomes.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top_errors": [
            {"error": error, "count": count}
            for error, count in sorted(errors.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ],
        "failure_examples": failure_samples,
    }


def _print_summary(summary: dict[str, Any]) -> None:
    print("=== Run Pressure Summary ===")
    print(f"mode            : {summary['mode']}")
    print(f"base_url        : {summary['base_url']}")
    print(f"runs            : {summary['runs']}")
    print(f"concurrency     : {summary['concurrency']}")
    print(f"threads_used    : {summary['threads_used']}")
    print(f"success / failed: {summary['success']} / {summary['failed']}")
    print(f"success_rate    : {summary['success_rate'] * 100:.2f}%")
    print(f"throughput_rps  : {summary['throughput_rps']:.2f}")
    print(f"wall_seconds    : {summary['wall_seconds']:.3f}")

    lat = summary["latency_seconds"]
    if lat["p50"] is not None:
        print(
            "latency_seconds : "
            f"p50={lat['p50']:.3f}, p90={lat['p90']:.3f}, "
            f"p95={lat['p95']:.3f}, p99={lat['p99']:.3f}, max={lat['max']:.3f}"
        )
    else:
        print("latency_seconds : n/a (no successful samples)")

    ttfb = summary["ttfb_seconds"]
    if ttfb["p50"] is not None:
        print(
            "ttfb_seconds    : "
            f"p50={ttfb['p50']:.3f}, p95={ttfb['p95']:.3f}, max={ttfb['max']:.3f}"
        )

    print("outcomes:")
    for key, count in summary["outcomes"].items():
        print(f"  - {key}: {count}")

    if summary["top_errors"]:
        print("top_errors:")
        for item in summary["top_errors"]:
            print(f"  - {item['count']}x {item['error']}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pressure test Wenjin run endpoints")
    parser.add_argument("--base-url", default="http://localhost:2026", help="Gateway or Nginx base URL")
    parser.add_argument("--mode", choices=["wait", "stream"], default="wait", help="run endpoint type")
    parser.add_argument("--runs", type=int, default=20, help="total run requests")
    parser.add_argument("--concurrency", type=int, default=4, help="parallel workers")
    parser.add_argument("--timeout", type=float, default=120.0, help="per-run timeout seconds")
    parser.add_argument("--warmup", type=int, default=1, help="warmup runs before measurement")
    parser.add_argument("--prompt", default="Reply in one short sentence: OK.", help="message for each run")

    parser.add_argument("--token", default=os.getenv("WENJIN_ACCESS_TOKEN") or os.getenv("WENJIN_TOKEN"))
    parser.add_argument("--email", default=os.getenv("WENJIN_EMAIL"))
    parser.add_argument("--password", default=os.getenv("WENJIN_PASSWORD"))

    parser.add_argument("--workspace-id", default=None, help="optional workspace_id for each run")
    parser.add_argument("--thread-id", default=None, help="reuse an existing thread_id")
    parser.add_argument("--single-thread", action="store_true", help="force all workers to share one thread")
    parser.add_argument("--cleanup-thread", action="store_true", help="delete auto-created threads after benchmark")

    parser.add_argument("--model", default=None, help="optional model override")
    parser.add_argument("--skill", default=None, help="optional skill override")
    parser.add_argument("--output", default=None, help="optional summary JSON output path")

    args = parser.parse_args()
    if args.runs <= 0:
        parser.error("--runs must be > 0")
    if args.concurrency <= 0:
        parser.error("--concurrency must be > 0")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    return args


def main() -> int:
    args = _parse_args()
    args.base_url = _normalize_base_url(args.base_url)

    token = str(args.token or "").strip()
    if not token:
        if not args.email or not args.password:
            print(
                "error: provide --token, or --email + --password "
                "(or env WENJIN_ACCESS_TOKEN / WENJIN_EMAIL / WENJIN_PASSWORD)",
                file=sys.stderr,
            )
            return 2
        try:
            token = _login(args.base_url, args.email, args.password, args.timeout)
        except Exception as exc:
            print(f"error: login failed: {exc}", file=sys.stderr)
            return 2

    auto_created_thread_ids: list[str] = []
    thread_ids: list[str]

    if args.thread_id:
        thread_ids = [args.thread_id]
    else:
        target_threads = 1 if args.single_thread else min(args.concurrency, args.runs)
        thread_ids = []
        for idx in range(target_threads):
            try:
                thread_id = _create_thread(
                    base_url=args.base_url,
                    token=token,
                    workspace_id=args.workspace_id,
                    model=args.model,
                    skill=args.skill,
                    timeout_seconds=args.timeout,
                    title=f"Pressure Benchmark {idx + 1}",
                )
            except Exception as exc:
                print(f"error: failed to create thread #{idx + 1}: {exc}", file=sys.stderr)
                return 2
            thread_ids.append(thread_id)
            auto_created_thread_ids.append(thread_id)

    print(f"Using {len(thread_ids)} thread(s): {', '.join(thread_ids)}")

    if args.warmup > 0:
        print(f"Running warmup: {args.warmup} request(s)...")
        for warmup_idx in range(args.warmup):
            sample = _run_once(
                run_index=-(warmup_idx + 1),
                args=args,
                base_url=args.base_url,
                token=token,
                thread_id=thread_ids[0],
            )
            state = "ok" if sample.ok else f"failed ({sample.outcome})"
            print(f"  warmup#{warmup_idx + 1}: {state}, latency={sample.latency_seconds:.3f}s")

    print(
        f"Starting benchmark: runs={args.runs}, concurrency={args.concurrency}, mode={args.mode}"
    )

    worker_indexes: list[list[int]] = [[] for _ in range(args.concurrency)]
    for run_index in range(args.runs):
        worker_indexes[run_index % args.concurrency].append(run_index)

    def _worker(worker_id: int) -> list[RunSample]:
        worker_results: list[RunSample] = []
        worker_thread = thread_ids[worker_id % len(thread_ids)]
        for run_index in worker_indexes[worker_id]:
            worker_results.append(
                _run_once(
                    run_index=run_index,
                    args=args,
                    base_url=args.base_url,
                    token=token,
                    thread_id=worker_thread,
                )
            )
        return worker_results

    started_at = time.perf_counter()
    samples: list[RunSample] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(_worker, worker_id) for worker_id in range(args.concurrency)]
        for future in futures:
            samples.extend(future.result())
    wall_seconds = time.perf_counter() - started_at

    samples.sort(key=lambda item: item.run_index)
    summary = _build_summary(
        samples=samples,
        wall_seconds=wall_seconds,
        args=args,
        thread_ids=thread_ids,
    )
    _print_summary(summary)

    if args.output:
        output_payload = {
            "summary": summary,
            "samples": [asdict(sample) for sample in samples],
        }
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(output_payload, handle, ensure_ascii=False, indent=2)
        print(f"summary JSON written to {args.output}")

    if args.cleanup_thread and auto_created_thread_ids:
        for thread_id in auto_created_thread_ids:
            _delete_thread(args.base_url, token, thread_id, args.timeout)
        print(f"cleaned up {len(auto_created_thread_ids)} auto-created thread(s)")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
