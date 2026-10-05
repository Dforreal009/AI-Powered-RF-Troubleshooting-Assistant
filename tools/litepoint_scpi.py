#!/usr/bin/env python3
"""Safe, dependency-free SCPI probes for the LitePoint IQgig-5G.

The CLI is intentionally conservative. Arbitrary non-query commands are not
accepted. The only write operation is a known-invalid parser probe used to
produce a labeled SCPI command error without changing RF configuration.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HOST = "192.168.100.254"
DEFAULT_PORT = 24000
ERROR_QUERY = "SYST:ERR:ALL?"
PARSER_ERROR_PROBE = "SYST:ML_DATASET_PROBE"
SAFE_CONTEXT_SELECTOR = re.compile(
    r"(?:CHAN(?:NEL)?\d+|5G|VSA\d+|VSG\d+|ROUT\d+|SYS)", re.IGNORECASE
)
FETCH_STATUS_NAMES = {
    14: "RESULTS_CALCULATED_FROM_PARTIAL_DATA",
    13: "RESULT_SIGNAL_ACQUISITION_OFF",
    12: "RESULT_UNRELIABLE",
    11: "RESULT_SIGNAL_INVALID",
    3: "RESULT_CALC_LENGTH_EXCEED_ANA_LIMIT",
    2: "RESULT_LIMIT_NA",
    1: "RESULT_LIMIT_FAIL",
    0: "RESULT_OK",
    -1: "RESULT_CALC_NOT_DEFINED",
    -2: "RESULT_CALC_OUT_OF_RANGE",
    -3: "RESULT_CALC_PENDING",
    -11: "RESULT_CAPTURE_NONE",
    -12: "RESULT_CAPTURE_TIMEOUT",
    -13: "RESULT_CAPTURE_INVALID",
    -21: "RESULT_ANALYSIS_FAILED",
    -22: "RESULT_ACQUISITION_FAILED",
    -31: "RESULT_SIGNAL_DIM_UNAVAILABLE",
    -32: "RESULT_STAT_RESULT_LEN_INCONSISTENT",
    -33: "RESULT_UNAVAILABLE",
    -34: "RESULT_STAT_SIGNAL_INCONSISTENT",
    -41: "RESULT_ANALYSIS_CFG_INVALID",
    -111: "RESULT_ANALYSIS_ERR",
    -225: "RESULT_OUT_OF_MEMORY",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScpiEvent:
    run_id: str
    timestamp_utc: str
    instrument_id: str | None
    host: str
    port: int
    command: str
    operation: str
    response: str | None
    latency_ms: float
    label: str
    scpi_error_code: int | None = None
    scpi_error_message: str | None = None
    scpi_error_detail: str | None = None
    fetch_status_code: int | None = None
    fetch_status_name: str | None = None
    fetch_status_severity: str | None = None
    fetch_values: list[str] | None = None


def parse_scpi_error(response: str) -> dict[str, Any]:
    """Parse LitePoint's CSV-shaped SCPI error response."""
    try:
        fields = next(csv.reader([response], skipinitialspace=True))
        code = int(fields[0])
        message = fields[1] if len(fields) > 1 else ""
    except (csv.Error, ValueError, StopIteration, IndexError):
        return {"code": None, "message": response, "detail": None}

    parts = [part.strip() for part in message.split(";")]
    summary = parts[0] if parts else message
    detail = "; ".join(parts[1:]) or None
    return {"code": code, "message": summary, "detail": detail}


def validate_read_only_query(command: str) -> None:
    """Reject setters hidden before a final query in a SCPI program message."""
    parts = [part.strip() for part in command.rstrip("\r\n").split(";")]
    if not parts or not parts[-1].endswith("?"):
        raise ValueError("query command must end in '?'")
    unsafe_prefixes = [
        part for part in parts[:-1] if not SAFE_CONTEXT_SELECTOR.fullmatch(part)
    ]
    if unsafe_prefixes:
        raise ValueError(
            "query contains non-query commands other than safe context selectors: "
            + ", ".join(unsafe_prefixes)
        )


def parse_fetch_response(response: str) -> dict[str, Any]:
    """Split a LitePoint fetch response into status and raw result fields."""
    try:
        fields = next(csv.reader([response], skipinitialspace=True))
        code = int(fields[0])
    except (csv.Error, ValueError, StopIteration, IndexError):
        return {
            "code": None,
            "name": None,
            "severity": None,
            "values": [response],
        }
    severity = "ok" if code == 0 else "warning" if code > 0 else "error"
    return {
        "code": code,
        "name": FETCH_STATUS_NAMES.get(code, "UNKNOWN_FETCH_STATUS"),
        "severity": severity,
        "values": fields[1:],
    }


class LitePointScpi:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._reader = None

    def __enter__(self) -> "LitePointScpi":
        self._socket = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )
        self._socket.settimeout(self.timeout)
        self._reader = self._socket.makefile("rb")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._reader is not None:
            self._reader.close()
        if self._socket is not None:
            self._socket.close()

    def write(self, command: str) -> None:
        if self._socket is None:
            raise RuntimeError("SCPI connection is not open")
        command = command.rstrip("\r\n")
        self._socket.sendall((command + "\n").encode("ascii"))

    def read_line(self) -> str:
        if self._reader is None:
            raise RuntimeError("SCPI connection is not open")
        response = self._reader.readline()
        if not response:
            raise ConnectionError("Tester closed the SCPI connection")
        return response.decode("ascii", errors="replace").rstrip("\r\n")

    def query(self, command: str) -> tuple[str, float]:
        validate_read_only_query(command)
        started = time.perf_counter()
        self.write(command)
        response = self.read_line()
        return response, (time.perf_counter() - started) * 1000


def append_event(path: Path | None, event: ScpiEvent) -> None:
    payload = asdict(event)
    print(json.dumps(payload, sort_keys=True))
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")


def make_event(
    *,
    run_id: str,
    instrument_id: str | None,
    args: argparse.Namespace,
    command: str,
    operation: str,
    response: str | None,
    latency_ms: float,
    label: str,
    error: dict[str, Any] | None = None,
    fetch: dict[str, Any] | None = None,
) -> ScpiEvent:
    error = error or {}
    fetch = fetch or {}
    return ScpiEvent(
        run_id=run_id,
        timestamp_utc=utc_now(),
        instrument_id=instrument_id,
        host=args.host,
        port=args.port,
        command=command,
        operation=operation,
        response=response,
        latency_ms=round(latency_ms, 3),
        label=label,
        scpi_error_code=error.get("code"),
        scpi_error_message=error.get("message"),
        scpi_error_detail=error.get("detail"),
        fetch_status_code=fetch.get("code"),
        fetch_status_name=fetch.get("name"),
        fetch_status_severity=fetch.get("severity"),
        fetch_values=fetch.get("values"),
    )


def identify(client: LitePointScpi, args: argparse.Namespace, run_id: str) -> str:
    response, latency = client.query("*IDN?")
    append_event(
        args.output,
        make_event(
            run_id=run_id,
            instrument_id=response,
            args=args,
            command="*IDN?",
            operation="query",
            response=response,
            latency_ms=latency,
            label="instrument_identity",
        ),
    )
    return response


def run(args: argparse.Namespace) -> None:
    run_id = str(uuid.uuid4())
    with LitePointScpi(args.host, args.port, args.timeout) as client:
        instrument_id = identify(client, args, run_id)

        if args.action == "identify":
            return

        if args.action == "query":
            response, latency = client.query(args.command)
            fetch = (
                parse_fetch_response(response)
                if "FETC" in args.command.upper().split(";")[-1]
                else None
            )
            append_event(
                args.output,
                make_event(
                    run_id=run_id,
                    instrument_id=instrument_id,
                    args=args,
                    command=args.command,
                    operation="query",
                    response=response,
                    latency_ms=latency,
                    label=args.label,
                    fetch=fetch,
                ),
            )
            return

        if args.action == "reproduce-command-error":
            started = time.perf_counter()
            client.write(PARSER_ERROR_PROBE)
            append_event(
                args.output,
                make_event(
                    run_id=run_id,
                    instrument_id=instrument_id,
                    args=args,
                    command=PARSER_ERROR_PROBE,
                    operation="write",
                    response=None,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    label="injected_undefined_header",
                ),
            )
            response, latency = client.query(ERROR_QUERY)
            parsed = parse_scpi_error(response)
            append_event(
                args.output,
                make_event(
                    run_id=run_id,
                    instrument_id=instrument_id,
                    args=args,
                    command=ERROR_QUERY,
                    operation="query",
                    response=response,
                    latency_ms=latency,
                    label="scpi_command_error",
                    error=parsed,
                ),
            )
            return

        raise ValueError(f"Unknown action: {args.action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--output",
        type=Path,
        help="Append one JSON object per event to this JSONL file.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("identify", help="Run only the read-only *IDN? query.")

    query_parser = subparsers.add_parser(
        "query", help="Run one read-only SCPI query ending in '?'."
    )
    query_parser.add_argument("command")
    query_parser.add_argument("--label", default="unlabeled_query")

    subparsers.add_parser(
        "reproduce-command-error",
        help=(
            "Send a known-invalid non-RF command, then read and label the SCPI "
            "error queue. This consumes the returned error queue entry."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.action == "query":
        try:
            validate_read_only_query(args.command)
        except ValueError as error:
            parser.error(str(error))
    run(args)


if __name__ == "__main__":
    main()
