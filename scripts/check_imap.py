#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import imaplib
import socket
import ssl
from dataclasses import dataclass


@dataclass(slots=True)
class ProbeResult:
    mode: str
    ok: bool
    detail: str


class Imap4SslWithServername(imaplib.IMAP4_SSL):
    def __init__(self, tls_servername: str, *args, **kwargs) -> None:
        self._tls_servername = tls_servername
        super().__init__(*args, **kwargs)

    def _create_socket(self, timeout):
        sock = imaplib.IMAP4._create_socket(self, timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self._tls_servername)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Hanbiro IMAP connectivity for 993/SSL and 143/plain."
    )
    parser.add_argument("--host", required=True, help="IMAP host, e.g. mail.ubisam.com")
    parser.add_argument(
        "--tls-servername",
        help="TLS certificate hostname override, e.g. groupware38.hanbiro.net",
    )
    parser.add_argument("--username", required=True, help="IMAP username, usually full email address")
    parser.add_argument("--password", help="IMAP password. If omitted, prompt securely.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Socket timeout in seconds. Default: 15",
    )
    parser.add_argument(
        "--mode",
        choices=["both", "plain", "ssl"],
        default="both",
        help='Probe mode. "plain" tests only 143, "ssl" tests only 993. Default: both',
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("IMAP password: ")
    socket.setdefaulttimeout(args.timeout)

    results: list[ProbeResult] = []
    if args.mode in {"both", "ssl"}:
        results.append(
            probe_ssl(
                args.host,
                args.tls_servername or args.host,
                args.username,
                password,
                timeout=args.timeout,
            )
        )
    if args.mode in {"both", "plain"}:
        results.append(probe_plain(args.host, args.username, password))

    print("")
    print("Probe results")
    print("-------------")
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"{status:4} {result.mode:10} {result.detail}")

    print("")
    successful = [item for item in results if item.ok]
    if successful:
        best = successful[0]
        if best.mode == "993/SSL":
            print('Use these env vars:')
            print('export UBISAM_IMAP_PORT="993"')
            print('export UBISAM_IMAP_USE_TLS="true"')
        else:
            print('Use these env vars:')
            print('export UBISAM_IMAP_PORT="143"')
            print('export UBISAM_IMAP_USE_TLS="false"')
        return 0

    print("No IMAP mode succeeded. Check host, username/password, OTP/app-password policy, or company network restrictions.")
    return 1


def probe_ssl(host: str, tls_servername: str, username: str, password: str, *, timeout: float) -> ProbeResult:
    try:
        context = ssl.create_default_context()
        with Imap4SslWithServername(
            tls_servername,
            host,
            993,
            ssl_context=context,
            timeout=timeout,
        ) as client:
            client.login(username, password)
        return ProbeResult("993/SSL", True, "login succeeded")
    except imaplib.IMAP4.error as exc:
        return ProbeResult("993/SSL", False, f"imap failed: {exc}")
    except (socket.timeout, TimeoutError) as exc:
        return ProbeResult("993/SSL", False, f"timeout: {exc}")
    except OSError as exc:
        return ProbeResult("993/SSL", False, f"os error: {exc}")


def probe_plain(host: str, username: str, password: str) -> ProbeResult:
    try:
        with imaplib.IMAP4(host, 143) as client:
            client.login(username, password)
        return ProbeResult("143/plain", True, "login succeeded")
    except imaplib.IMAP4.error as exc:
        return ProbeResult("143/plain", False, f"imap failed: {exc}")
    except (socket.timeout, TimeoutError) as exc:
        return ProbeResult("143/plain", False, f"timeout: {exc}")
    except OSError as exc:
        return ProbeResult("143/plain", False, f"os error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
