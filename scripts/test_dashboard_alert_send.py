import argparse
import asyncio
import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.seatalk.system_account_client import SeaTalkSystemAccountClient
from app.time_utils import now_local
from app.workflows.stuckup.service import StuckupService


def _build_default_text(settings: Settings) -> str:
    template = settings.stuckup_dashboard_alert_text_template or "Outbound Stuck at SOC_Staging Stuckup Validation Report {date}"
    date_format = settings.stuckup_dashboard_alert_date_format or "%Y-%m-%d"
    date_text = now_local(settings).strftime(date_format)
    return template.replace("{date}", date_text).strip()


def _read_image_file_base64(image_path: Path) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"image file not found: {image_path}")
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


async def _run(args: argparse.Namespace) -> None:
    settings = Settings()
    client = SeaTalkSystemAccountClient(settings.stuckup_dashboard_alert_system_webhook_url)
    if not client.enabled:
        raise RuntimeError("STUCKUP_DASHBOARD_ALERT_SYSTEM_WEBHOOK_URL is not configured")

    send_text = not args.skip_text
    send_image = not args.skip_image
    if not send_text and not send_image:
        raise ValueError("nothing to send: remove at least one of --skip-text / --skip-image")

    if send_text:
        content = args.text.strip() if args.text else _build_default_text(settings)
        at_all = settings.stuckup_dashboard_alert_at_all and not args.no_at_all
        text_result = await client.send_text_message(content=content, at_all=at_all)
        print(f"text sent: at_all={at_all} response={text_result}")

    if send_image:
        if args.image_path:
            image_base64 = _read_image_file_base64(Path(args.image_path))
            image_source = f"file:{args.image_path}"
        else:
            service = StuckupService(settings)
            image_base64 = service.capture_dashboard_range_png_base64()
            image_source = (
                f"sheet:{settings.stuckup_dashboard_capture_worksheet_name}!"
                f"{settings.stuckup_dashboard_capture_range}"
            )

        image_result = await client.send_image_message(image_base64=image_base64)
        print(f"image sent: source={image_source} response={image_result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a dashboard-alert sample message to SeaTalk system account webhook.")
    parser.add_argument("--text", default="", help="Override text content. Default uses STUCKUP_DASHBOARD_ALERT_TEXT_TEMPLATE.")
    parser.add_argument("--image-path", default="", help="Optional local image path; if omitted, capture from configured sheet range.")
    parser.add_argument("--skip-text", action="store_true", help="Send only image.")
    parser.add_argument("--skip-image", action="store_true", help="Send only text.")
    parser.add_argument("--no-at-all", action="store_true", help="Disable @all for this test run.")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
