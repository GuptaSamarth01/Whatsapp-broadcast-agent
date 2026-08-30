"""
WhatsApp Broadcast Agent
------------------------
Sends the same image + caption to every phone number
in contacts.json using WhatsApp Web + Playwright.

Features:
- Campaign logging
- Per-recipient status
- Attempt tracking
- Error tracking
- Persistent campaign state
"""

import json
import os
import re
import time
from datetime import datetime

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

CONTACTS_PATH = "contacts.json"
PROFILE_DIR = "./whatsapp_profile"
LOGS_DIR = "./logs"

DELAY_BETWEEN_SENDS = 25
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10


# ============================================================
# PHONE NUMBER FUNCTIONS
# ============================================================

def normalize_phone(phone: str) -> str:
    """Normalize a phone number into a simple international format."""

    phone = str(phone).strip()

    # Keep only digits and a possible leading +
    phone = re.sub(r"[^\d+]", "", phone)

    # Convert 00XXXXXXXXXX -> +XXXXXXXXXX
    if phone.startswith("00"):
        phone = "+" + phone[2:]

    # Add + if missing
    if not phone.startswith("+"):
        phone = "+" + phone

    return phone


def is_valid_phone(phone: str) -> bool:
    """Basic international phone-number validation."""

    digits = phone[1:] if phone.startswith("+") else phone

    return digits.isdigit() and 8 <= len(digits) <= 15


def load_contacts(path: str = CONTACTS_PATH) -> list[str]:
    """Load phone numbers from contacts.json."""

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Couldn't find {path}.\n"
            f"Create it using contacts.example.json as a template."
        )

    with open(path, "r", encoding="utf-8") as f:
        contacts = json.load(f)

    if not isinstance(contacts, list):
        raise ValueError(
            "contacts.json must contain a JSON list of phone numbers."
        )

    valid_contacts = []
    invalid_contacts = []

    for raw_phone in contacts:

        phone = normalize_phone(raw_phone)

        if is_valid_phone(phone):
            valid_contacts.append(phone)
        else:
            invalid_contacts.append(str(raw_phone))

    # Remove duplicates while preserving order
    valid_contacts = list(dict.fromkeys(valid_contacts))

    if invalid_contacts:

        print("\nInvalid phone numbers:")

        for phone in invalid_contacts:
            print(f"  - {phone}")

    return valid_contacts


# ============================================================
# TIME / LOGGING FUNCTIONS
# ============================================================

def timestamp() -> str:
    """Return current local time in ISO format."""

    return datetime.now().astimezone().isoformat(
        timespec="seconds"
    )


def create_campaign(
    image_path: str,
    message: str,
    contacts: list[str],
) -> dict:
    """Create a new campaign state."""

    os.makedirs(LOGS_DIR, exist_ok=True)

    campaign_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    campaign = {
        "campaign_id": campaign_id,
        "status": "running",
        "created_at": timestamp(),
        "completed_at": None,

        "image": os.path.abspath(image_path),
        "message": message,

        "total_contacts": len(contacts),

        "summary": {
            "pending": len(contacts),
            "sent": 0,
            "failed": 0,
        },

        "contacts": {
            phone: {
                "status": "pending",
                "attempts": 0,
                "last_attempt": None,
                "error": None,
            }
            for phone in contacts
        },
    }

    save_campaign(campaign)

    return campaign


def get_campaign_path(campaign: dict) -> str:
    """Return the log path for a campaign."""

    campaign_id = campaign["campaign_id"]

    return os.path.join(
        LOGS_DIR,
        f"campaign_{campaign_id}.json",
    )


def save_campaign(campaign: dict) -> None:
    """
    Save campaign state safely.

    Writes to a temporary file first and then replaces
    the actual campaign file.
    """

    os.makedirs(LOGS_DIR, exist_ok=True)

    path = get_campaign_path(campaign)
    temp_path = path + ".tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            campaign,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        temp_path,
        path,
    )


def update_summary(campaign: dict) -> None:
    """Recalculate campaign summary from recipient states."""

    statuses = [
        data["status"]
        for data in campaign["contacts"].values()
    ]

    campaign["summary"] = {
        "pending": statuses.count("pending"),
        "sent": statuses.count("sent"),
        "failed": statuses.count("failed"),
    }


def update_recipient(
    campaign: dict,
    phone: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update one recipient's campaign state."""

    recipient = campaign["contacts"][phone]

    recipient["status"] = status
    recipient["last_attempt"] = timestamp()
    recipient["error"] = error

    update_summary(campaign)

    save_campaign(campaign)


def finish_campaign(campaign: dict) -> None:
    """Mark campaign as completed."""

    update_summary(campaign)

    if campaign["summary"]["pending"] == 0:

        campaign["status"] = "completed"
        campaign["completed_at"] = timestamp()

    save_campaign(campaign)

def get_incomplete_campaigns() -> list[dict]:
    """Find campaigns that still have pending recipients."""

    if not os.path.exists(LOGS_DIR):
        return []

    campaigns = []

    for filename in os.listdir(LOGS_DIR):

        if not filename.startswith("campaign_"):
            continue

        if not filename.endswith(".json"):
            continue

        path = os.path.join(
            LOGS_DIR,
            filename,
        )

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as f:

                campaign = json.load(f)

            update_summary(campaign)

            if campaign["summary"]["pending"] > 0:
                campaigns.append(campaign)

        except Exception as e:

            print(
                f"Warning: Could not read "
                f"{filename}: {e}"
            )

    campaigns.sort(
        key=lambda campaign: campaign["created_at"],
        reverse=True,
    )

    return campaigns


def show_campaign_summary(
    campaign: dict,
) -> None:
    """Display a campaign's current progress."""

    summary = campaign["summary"]

    print(
        "\n==================================="
    )

    print(
        "       PREVIOUS CAMPAIGN FOUND"
    )

    print(
        "===================================\n"
    )

    print(
        f"Campaign: {campaign['campaign_id']}"
    )

    print(
        f"Created:  {campaign['created_at']}"
    )

    print()

    print(
        f"Total:    {campaign['total_contacts']}"
    )

    print(
        f"Sent:     {summary['sent']}"
    )

    print(
        f"Failed:   {summary['failed']}"
    )

    print(
        f"Pending:  {summary['pending']}"
    )

    print(
        "\nImage:"
    )

    print(
        campaign["image"]
    )

    print(
        "\nCaption:"
    )

    print(
        "-----------------------------------"
    )

    print(
        campaign["message"]
    )

    print(
        "-----------------------------------"
    )


def choose_existing_campaign() -> dict | None:
    """
    Ask the user whether to resume an incomplete campaign.

    Returns:
        Campaign dictionary if resuming.
        None if starting a new campaign.
    """

    campaigns = get_incomplete_campaigns()

    if not campaigns:
        return None

    # For now, use the newest incomplete campaign.
    campaign = campaigns[0]

    show_campaign_summary(
        campaign
    )

    print(
        "\nOptions:"
    )

    print(
        "  [R] Resume this campaign"
    )

    print(
        "  [N] Start a new campaign"
    )

    print()

    choice = input(
        "Choose R or N: "
    ).strip().upper()

    if choice == "R":

        print(
            "\nResuming campaign "
            f"{campaign['campaign_id']}..."
        )

        return campaign

    print(
        "\nStarting a new campaign..."
    )

    return None

# ============================================================
# WHATSAPP SENDER
# ============================================================

def send_whatsapp_message(
    page,
    phone: str,
    message: str,
    image_path: str,
) -> None:
    """
    Send one image + caption through WhatsApp Web.

    This is the same working Playwright workflow
    we tested successfully.
    """

    print(
        f"    Opening chat for {phone}..."
    )

    # --------------------------------------------------------
    # Open chat
    # --------------------------------------------------------

    page.goto(
        f"https://web.whatsapp.com/send?phone={phone}",
        wait_until="domcontentloaded",
    )

    page.locator(
        '[contenteditable="true"][role="textbox"]'
    ).last.wait_for(
        timeout=30000
    )

    print("    Chat loaded.")

    # --------------------------------------------------------
    # STEP 1: Open Attach menu
    # --------------------------------------------------------

    print(
        "    Opening attachment menu..."
    )

    attach = page.locator(
        'button[aria-label="Attach"]'
    )

    attach.wait_for(
        timeout=10000
    )

    attach.click()

    # --------------------------------------------------------
    # STEP 2: Photos & videos
    # --------------------------------------------------------

    print(
        "    Selecting Photos & videos..."
    )

    photos_videos_selector = (
        'button[role="menuitem"]'
        '[aria-label="Photos & videos"]'
    )

    page.locator(
        photos_videos_selector
    ).wait_for(
        state="visible",
        timeout=10000,
    )

    # WhatsApp can replace the menu element while
    # rendering, so use JavaScript click.
    with page.expect_file_chooser(
        timeout=10000
    ) as chooser_info:

        page.locator(
            photos_videos_selector
        ).evaluate(
            "(element) => element.click()"
        )

    chooser = chooser_info.value

    print(
        "    File chooser detected."
    )

    # --------------------------------------------------------
    # STEP 3: Select image
    # --------------------------------------------------------

    print(
        "    Selecting image..."
    )

    chooser.set_files(
        image_path
    )

    print(
        "    Image selected."
    )

    # --------------------------------------------------------
    # STEP 4: Wait for image editor
    # --------------------------------------------------------

    print(
        "    Waiting for image editor..."
    )

    send_media = page.get_by_role(
        "button",
        name="Send 1 selected",
        exact=True,
    )

    send_media.wait_for(
        state="visible",
        timeout=15000,
    )

    print(
        "    Image editor opened."
    )

    # --------------------------------------------------------
    # STEP 5: Caption
    # --------------------------------------------------------

    print(
        "    Looking for caption field..."
    )

    caption_box = page.locator(
        '[data-testid="media-caption-input-container"]'
    )

    caption_box.wait_for(
        state="visible",
        timeout=10000,
    )

    print(
        "    Caption field found."
    )

    # --------------------------------------------------------
    # STEP 6: Enter caption
    # --------------------------------------------------------

    print(
        "    Entering caption..."
    )

    caption_box.fill(
        message
    )

    print(
        "    Caption entered."
    )

    page.wait_for_timeout(
        1000
    )

    # --------------------------------------------------------
    # STEP 7: Send
    # --------------------------------------------------------

    print(
        "    Sending image + caption..."
    )

    send_media.click(
        force=True
    )

    print(
        "    Send button clicked."
    )

    # Give WhatsApp time to process
    page.wait_for_timeout(
        3000
    )

    # --------------------------------------------------------
    # Verify editor disappeared
    # --------------------------------------------------------

    try:

        send_media.wait_for(
            state="hidden",
            timeout=10000,
        )

    except Exception:

        raise RuntimeError(
            "Media editor did not close after "
            "the send action."
        )

    print(
        "    ✓ Message sent."
    )


# ============================================================
# BROADCAST
# ============================================================

def broadcast_message(
    campaign: dict,
) -> dict:
    """Run a campaign with automatic retries."""

    image_path = campaign["image"]
    message = campaign["message"]

    contacts = list(
        campaign["contacts"].keys()
    )

    with sync_playwright() as p:

        print(
            "\nStarting WhatsApp browser..."
        )

        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            slow_mo=100,
        )

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        print(
            "WhatsApp browser ready."
        )

        # ----------------------------------------------------
        # Process contacts
        # ----------------------------------------------------

        for i, phone in enumerate(
            contacts,
            start=1,
        ):

            recipient = campaign[
                "contacts"
            ][phone]

            # -----------------------------------------------
            # Skip recipients already sent
            # -----------------------------------------------

            if recipient["status"] == "sent":

                print(
                    f"\n[{i}/{len(contacts)}] "
                    f"{phone} → already sent, skipping."
                )

                continue

            # -----------------------------------------------
            # Retry loop
            # -----------------------------------------------

            success = False

            for attempt in range(
                recipient["attempts"] + 1,
                MAX_RETRIES + 1,
            ):

                print(
                    f"\n[{i}/{len(contacts)}] "
                    f"Sending to {phone}..."
                )

                print(
                    f"    Attempt "
                    f"{attempt}/{MAX_RETRIES}"
                )

                # -------------------------------------------
                # Record attempt BEFORE sending
                # -------------------------------------------

                recipient["attempts"] = attempt
                recipient["last_attempt"] = timestamp()
                recipient["error"] = None

                save_campaign(
                    campaign
                )

                try:

                    send_whatsapp_message(
                        page=page,
                        phone=phone,
                        message=message,
                        image_path=image_path,
                    )

                    # ---------------------------------------
                    # SUCCESS
                    # ---------------------------------------

                    update_recipient(
                        campaign=campaign,
                        phone=phone,
                        status="sent",
                    )

                    print(
                        f"    ✓ Sent successfully "
                        f"on attempt {attempt}."
                    )

                    success = True

                    break

                except Exception as e:

                    error_message = str(e)

                    print(
                        f"    ✗ Attempt "
                        f"{attempt} failed."
                    )

                    print(
                        f"      Error: "
                        f"{error_message}"
                    )

                    recipient["error"] = (
                        error_message
                    )

                    # ---------------------------------------
                    # More attempts available
                    # ---------------------------------------

                    if attempt < MAX_RETRIES:

                        print(
                            f"    Retrying in "
                            f"{RETRY_DELAY_SECONDS} "
                            f"seconds..."
                        )

                        update_recipient(
                            campaign=campaign,
                            phone=phone,
                            status="pending",
                            error=error_message,
                        )

                        time.sleep(
                            RETRY_DELAY_SECONDS
                        )

                    # ---------------------------------------
                    # No attempts remaining
                    # ---------------------------------------

                    else:

                        update_recipient(
                            campaign=campaign,
                            phone=phone,
                            status="failed",
                            error=error_message,
                        )

                        print(
                            f"    ✗ Permanently failed "
                            f"after {MAX_RETRIES} attempts."
                        )

            # ------------------------------------------------
            # Normal delay before next recipient
            # ------------------------------------------------

            if i < len(contacts):

                if success:

                    print(
                        f"    Waiting "
                        f"{DELAY_BETWEEN_SENDS} "
                        f"seconds before next recipient..."
                    )

                    time.sleep(
                        DELAY_BETWEEN_SENDS
                    )

                else:

                    print(
                        "    Moving to next recipient."
                    )

        context.close()

    finish_campaign(
        campaign
    )

    return campaign

# ============================================================
# MAIN WORKFLOW
# ============================================================

def run_broadcast() -> None:
    """Run the complete photo + text broadcast workflow."""

    print(
        "\n==================================="
    )

    print(
        "      WhatsApp Broadcast Agent"
    )

    print(
        "===================================\n"
    )

    # --------------------------------------------------------
    # Check for an incomplete campaign
    # --------------------------------------------------------

    existing_campaign = choose_existing_campaign()

    if existing_campaign is not None:

        campaign = existing_campaign

        print(
            "\nResuming existing campaign."
        )

        print(
            f"Campaign ID: "
            f"{campaign['campaign_id']}"
        )

        print(
            f"Remaining recipients: "
            f"{campaign['summary']['pending']}"
        )

        print(
            "\nBroadcast resuming..."
        )

        print(
            "Keep WhatsApp Web/browser visible.\n"
        )

        campaign = broadcast_message(
            campaign
        )

        summary = campaign[
            "summary"
        ]

        print(
            "\n==================================="
        )

        print(
            "       CAMPAIGN RESUME COMPLETE"
        )

        print(
            "==================================="
        )

        print(
            f"Total:     "
            f"{campaign['total_contacts']}"
        )

        print(
            f"Sent:      "
            f"{summary['sent']}"
        )

        print(
            f"Failed:    "
            f"{summary['failed']}"
        )

        print(
            f"Pending:   "
            f"{summary['pending']}"
        )

        print(
            "==================================="
        )

        print(
            f"\nLog: "
            f"{get_campaign_path(campaign)}"
        )

        return

    # --------------------------------------------------------
    # New campaign
    # --------------------------------------------------------

    try:

        contacts = load_contacts()

    except Exception as e:

        print(
            f"Error loading contacts: {e}"
        )

        return

    if not contacts:

        print(
            "No valid contacts found."
        )

        return

    print(
        f"Contacts loaded: {len(contacts)}"
    )

    # --------------------------------------------------------
    # Get image
    # --------------------------------------------------------

    image_path = input(
        "\nEnter the path to the image "
        "you want to send: "
    ).strip()

    if not os.path.isfile(
        image_path
    ):

        print(
            f"Image not found: {image_path}"
        )

        return

    print(
        f"Image: {image_path}"
    )

    # --------------------------------------------------------
    # Get message
    # --------------------------------------------------------

    print(
        "\nEnter the message/caption "
        "you want to send."
    )

    print(
        "Type your message and press ENTER.\n"
    )

    message = input(
        "> "
    ).strip()

    if not message:

        print(
            "Message cannot be empty."
        )

        return

    # --------------------------------------------------------
    # Preview
    # --------------------------------------------------------

    print(
        "\n==================================="
    )

    print(
        "        BROADCAST PREVIEW"
    )

    print(
        "===================================\n"
    )

    print(
        f"Image: {image_path}"
    )

    print(
        "\nCaption:"
    )

    print(
        "-----------------------------------"
    )

    print(
        message
    )

    print(
        "-----------------------------------"
    )

    print(
        f"\nRecipients: {len(contacts)}"
    )

    print(
        "===================================\n"
    )

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    confirmation = input(
        "Send this photo + message to everyone? "
        "Type 'YES' to continue: "
    ).strip()

    if confirmation != "YES":

        print(
            "\nBroadcast cancelled."
        )

        return

    # --------------------------------------------------------
    # Create campaign
    # --------------------------------------------------------

    campaign = create_campaign(
        image_path=image_path,
        message=message,
        contacts=contacts,
    )

    print(
        "\nCampaign created:"
    )

    print(
        f"  ID: "
        f"{campaign['campaign_id']}"
    )

    print(
        f"  Log: "
        f"{get_campaign_path(campaign)}"
    )

    print(
        "\nBroadcast starting..."
    )

    print(
        "Keep WhatsApp Web/browser visible.\n"
    )

    # --------------------------------------------------------
    # Run campaign
    # --------------------------------------------------------

    campaign = broadcast_message(
        campaign
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = campaign[
        "summary"
    ]

    print(
        "\n==================================="
    )

    print(
        "         BROADCAST COMPLETE"
    )

    print(
        "==================================="
    )

    print(
        f"Total:     "
        f"{campaign['total_contacts']}"
    )

    print(
        f"Sent:      "
        f"{summary['sent']}"
    )

    print(
        f"Failed:    "
        f"{summary['failed']}"
    )

    print(
        f"Pending:   "
        f"{summary['pending']}"
    )

    print(
        "==================================="
    )

    print(
        f"\nLog saved to:"
    )

    print(
        get_campaign_path(campaign)
    )

    print()

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_broadcast()