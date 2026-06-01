#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import smtplib
import socket
import ssl
from dataclasses import dataclass


@dataclass(slots=True)
class ProbeResult:
    mode: str
    ok: bool
    detail: str


class SmtpSslWithServername(smtplib.SMTP_SSL):
    def __init__(self, tls_servername: str, *args, **kwargs) -> None:
        self._tls_servername = tls_servername
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        if self.debuglevel > 0:
            self._print_debug("connect:", (host, port))
        new_socket = super(smtplib.SMTP_SSL, self)._get_socket(host, port, timeout)
        return self.context.wrap_socket(new_socket, server_hostname=self._tls_servername)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Hanbiro SMTP connectivity for 587/STARTTLS and 465/SSL."
    )
    parser.add_argument("--host", required=True, help="SMTP host, e.g. yourdomain.hanbiro.net")
    parser.add_argument(
        "--tls-servername",
        help="TLS certificate hostname override, e.g. groupware38.hanbiro.net",
    )
    parser.add_argument("--username", required=True, help="SMTP username, usually full email address")
    parser.add_argument(
        "--password",
        help="SMTP password. If omitted, prompt securely.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Socket timeout in seconds. Default: 15",
    )
    parser.add_argument(
        "--mode",
        choices=["both", "starttls", "ssl"],
        default="both",
        help='Probe mode. "starttls" tests only 587, "ssl" tests only 465. Default: both',
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("SMTP password: ")
    results: list[ProbeResult] = []
    if args.mode in {"both", "starttls"}:
        results.append(
            probe_starttls(
                args.host,
                args.tls_servername or args.host,
                args.username,
                password,
                timeout=args.timeout,
            )
        )
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

    print("")
    print("Probe results")
    print("-------------")
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"{status:4} {result.mode:14} {result.detail}")

    print("")
    successful = [item for item in results if item.ok]
    if successful:
        best = successful[0]
        if best.mode == "587/STARTTLS":
            print('Use these env vars:')
            print('export HANBIRO_SMTP_PORT="587"')
            print('export HANBIRO_SMTP_USE_STARTTLS="true"')
            print('export HANBIRO_SMTP_USE_TLS="false"')
        else:
            print('Use these env vars:')
            print('export HANBIRO_SMTP_PORT="465"')
            print('export HANBIRO_SMTP_USE_STARTTLS="false"')
            print('export HANBIRO_SMTP_USE_TLS="true"')
        return 0

    print("No SMTP mode succeeded. Check host, username/password, OTP/app-password policy, or company network restrictions.")
    return 1


def probe_starttls(host: str, tls_servername: str, username: str, password: str, *, timeout: float) -> ProbeResult:
    try:
        smtp = smtplib.SMTP(host, 587, timeout=timeout)
        try:
            smtp.ehlo()
            smtp._host = tls_servername
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp_login(smtp, username, password)
        finally:
            close_smtp_session(smtp)
        return ProbeResult("587/STARTTLS", True, "login succeeded")
    except smtplib.SMTPAuthenticationError as exc:
        return ProbeResult("587/STARTTLS", False, f"auth failed: {smtp_error(exc)}")
    except smtplib.SMTPException as exc:
        return ProbeResult("587/STARTTLS", False, f"smtp failed: {smtp_error(exc)}")
    except (socket.timeout, TimeoutError) as exc:
        return ProbeResult("587/STARTTLS", False, f"timeout: {exc}")
    except OSError as exc:
        return ProbeResult("587/STARTTLS", False, f"os error: {exc}")


def probe_ssl(host: str, tls_servername: str, username: str, password: str, *, timeout: float) -> ProbeResult:
    try:
        smtp = SmtpSslWithServername(
            tls_servername,
            host,
            465,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        try:
            smtp.ehlo()
            smtp_login(smtp, username, password)
        finally:
            close_smtp_session(smtp)
        return ProbeResult("465/SSL", True, "login succeeded")
    except smtplib.SMTPAuthenticationError as exc:
        return ProbeResult("465/SSL", False, f"auth failed: {smtp_error(exc)}")
    except smtplib.SMTPException as exc:
        return ProbeResult("465/SSL", False, f"smtp failed: {smtp_error(exc)}")
    except (socket.timeout, TimeoutError) as exc:
        return ProbeResult("465/SSL", False, f"timeout: {exc}")
    except OSError as exc:
        return ProbeResult("465/SSL", False, f"os error: {exc}")


def smtp_error(exc: smtplib.SMTPException) -> str:
    code = getattr(exc, "smtp_code", None)
    error = getattr(exc, "smtp_error", None)
    if isinstance(error, bytes):
        error = error.decode("utf-8", errors="replace")
    if code is not None and error is not None:
        return f"{code} {error}"
    return str(exc)


def smtp_login(smtp: smtplib.SMTP, username: str, password: str) -> tuple[int, bytes]:
    smtp.ehlo_or_helo_if_needed()
    if not smtp.has_extn("auth"):
        raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")

    plain_token = base64.b64encode(f"\0{username}\0{password}".encode("utf-8")).decode("ascii")
    try:
        return smtp.docmd("AUTH", f"PLAIN {plain_token}")
    except smtplib.SMTPAuthenticationError as exc:
        plain_error = exc
    except smtplib.SMTPResponseException as exc:
        if exc.smtp_code in (235, 503):
            return exc.smtp_code, exc.smtp_error
        plain_error = smtplib.SMTPAuthenticationError(exc.smtp_code, exc.smtp_error)
    else:
        return 235, b"ok"

    username_token = base64.b64encode(username.encode("utf-8")).decode("ascii")
    password_token = base64.b64encode(password.encode("utf-8")).decode("ascii")
    try:
        code, response = smtp.docmd("AUTH", "LOGIN")
        if code != 334:
            raise smtplib.SMTPAuthenticationError(code, response)
        code, response = smtp.docmd(username_token)
        if code != 334:
            raise smtplib.SMTPAuthenticationError(code, response)
        code, response = smtp.docmd(password_token)
        if code not in (235, 503):
            raise smtplib.SMTPAuthenticationError(code, response)
        return code, response
    except smtplib.SMTPAuthenticationError:
        raise plain_error


def close_smtp_session(smtp: smtplib.SMTP) -> None:
    try:
        smtp.docmd("QUIT")
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException, smtplib.SMTPException):
        pass
    finally:
        smtp.close()


if __name__ == "__main__":
    raise SystemExit(main())
