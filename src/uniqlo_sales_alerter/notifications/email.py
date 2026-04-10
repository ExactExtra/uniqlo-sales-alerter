"""Email notification channel using async SMTP."""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import SaleItem

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import EmailChannelConfig

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 30


def _build_html(deals: list[SaleItem]) -> str:
    rows: list[str] = []
    for deal in deals:
        watched_badge = ' <span style="color:gold;">⭐ Watched</span>' if deal.is_watched else ""
        img_tag = (
            f'<img src="{deal.image_url}" alt="{deal.name}" '
            f'style="max-width:120px;max-height:160px;border-radius:4px;" />'
            if deal.image_url
            else ""
        )
        size_links = " &middot; ".join(
            f'<a href="{url}">{sz}</a>'
            for sz, url in zip(deal.available_sizes, deal.product_urls)
        ) or ", ".join(deal.available_sizes)
        rows.append(
            f"""
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:12px;">{img_tag}</td>
                <td style="padding:12px;">
                    <strong>{deal.name}</strong>{watched_badge}<br/>
                    <span style="text-decoration:line-through;color:#999;">
                        {deal.currency_symbol}{deal.original_price:.2f}
                    </span>
                    &rarr;
                    <span style="color:#c0392b;font-weight:bold;">
                        {deal.currency_symbol}{deal.sale_price:.2f}
                    </span>
                    <span style="color:#27ae60;">(-{deal.discount_percentage:.0f}%)</span><br/>
                    <small>Sizes: {size_links}</small>
                </td>
            </tr>"""
        )

    return f"""
    <html><body>
    <h2>Uniqlo Sale Alert — {len(deals)} deal(s) found</h2>
    <table style="border-collapse:collapse;width:100%;max-width:600px;">
        {"".join(rows)}
    </table>
    <p style="color:#999;font-size:12px;">
        Sent by <a href="https://github.com/kequach/uniqlo-sales-alerter"
        style="color:#999;">Uniqlo Sales Alerter</a>
    </p>
    </body></html>
    """


class EmailNotifier:
    """Sends deal notifications via SMTP email."""

    def __init__(self, config: EmailChannelConfig) -> None:
        self._config = config

    def is_enabled(self) -> bool:
        return (
            self._config.enabled
            and bool(self._config.smtp_host)
            and bool(self._config.from_address)
            and bool(self._config.to_addresses)
        )

    async def send(self, deals: list[SaleItem]) -> None:
        if not deals:
            return

        try:
            import aiosmtplib
        except ImportError:
            msg = "aiosmtplib is not installed — run: pip install aiosmtplib"
            logger.error(msg)
            raise RuntimeError(msg)

        cfg = self._config

        implicit_tls = cfg.use_tls and cfg.smtp_port == 465
        starttls = cfg.use_tls and not implicit_tls
        tls_mode = (
            "implicit TLS" if implicit_tls
            else "STARTTLS" if starttls
            else "plaintext"
        )

        logger.info(
            "Sending %d deal(s) via %s:%d (%s) to %s",
            len(deals), cfg.smtp_host, cfg.smtp_port, tls_mode,
            ", ".join(cfg.to_addresses),
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Uniqlo Sale Alert — {len(deals)} deal(s)"
        msg["From"] = cfg.from_address
        msg["To"] = ", ".join(cfg.to_addresses)
        msg.attach(MIMEText(_build_html(deals), "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=cfg.smtp_host,
                port=cfg.smtp_port,
                use_tls=implicit_tls,
                start_tls=starttls,
                username=cfg.smtp_user or None,
                password=cfg.smtp_password or None,
                timeout=_SMTP_TIMEOUT,
            )
            logger.info("Email sent to %s", cfg.to_addresses)
        except aiosmtplib.SMTPAuthenticationError as exc:
            logger.error(
                "SMTP authentication failed for %s@%s:%d — %s",
                cfg.smtp_user, cfg.smtp_host, cfg.smtp_port, exc,
            )
            raise
        except aiosmtplib.SMTPRecipientsRefused as exc:
            logger.error(
                "All recipients refused by %s:%d — %s",
                cfg.smtp_host, cfg.smtp_port, exc,
            )
            raise
        except aiosmtplib.SMTPResponseException as exc:
            logger.error(
                "SMTP server %s:%d returned error %d: %s",
                cfg.smtp_host, cfg.smtp_port, exc.code, exc.message,
            )
            raise
        except aiosmtplib.SMTPConnectError as exc:
            logger.error(
                "Cannot connect to SMTP server %s:%d — %s",
                cfg.smtp_host, cfg.smtp_port, exc,
            )
            raise
        except (TimeoutError, aiosmtplib.SMTPTimeoutError) as exc:
            logger.error(
                "SMTP connection to %s:%d timed out after %ds — %s",
                cfg.smtp_host, cfg.smtp_port, _SMTP_TIMEOUT, exc,
            )
            raise
        except Exception:
            logger.exception(
                "Unexpected error sending email via %s:%d",
                cfg.smtp_host, cfg.smtp_port,
            )
            raise
