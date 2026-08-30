"""
WhatsApp Broadcast Agent
------------------------
Sends the same image + caption to every phone number
in contacts.json using WhatsApp Web + Playwright.
"""

import json
import os
import re
import time

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

CONTACTS_PATH = "contacts.json"

PROFILE_DIR = "./whatsapp_profile"

DELAY_BETWEEN_SENDS = 25


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

    Workflow:

    Open chat
        ↓
    Attach
        ↓
    Photos & videos
        ↓
    Select image
        ↓
    Enter caption
        ↓
    Send
    """

    print(f"    Opening chat for {phone}...")

    # --------------------------------------------------------
    # Open the WhatsApp chat
    # --------------------------------------------------------

    page.goto(
        f"https://web.whatsapp.com/send?phone={phone}",
        wait_until="domcontentloaded",
    )

    # Wait for the chat composer
    page.locator(
        '[contenteditable="true"][role="textbox"]'
    ).last.wait_for(timeout=30000)

    print("    Chat loaded.")

    # --------------------------------------------------------
    # STEP 1: Open Attach menu
    # --------------------------------------------------------

    print("    Opening attachment menu...")

    attach = page.locator(
        'button[aria-label="Attach"]'
    )

    attach.wait_for(timeout=10000)

    attach.click()

    # --------------------------------------------------------
    # STEP 2: Select Photos & videos
    # --------------------------------------------------------

    print("    Selecting Photos & videos...")

    photos_videos_selector = (
        'button[role="menuitem"]'
        '[aria-label="Photos & videos"]'
    )

    # Wait until WhatsApp creates the menu item
    page.locator(
        photos_videos_selector
    ).wait_for(
        state="visible",
        timeout=10000,
    )

    # WhatsApp can replace the menu element while rendering.
    # JavaScript click avoids Playwright's detached-DOM issue.
    with page.expect_file_chooser(
        timeout=10000
    ) as chooser_info:

        page.locator(
            photos_videos_selector
        ).evaluate(
            "(element) => element.click()"
        )

    chooser = chooser_info.value

    print("    File chooser detected.")

    # --------------------------------------------------------
    # STEP 3: Select image
    # --------------------------------------------------------

    print("    Selecting image...")

    chooser.set_files(image_path)

    print("    Image selected.")

    # --------------------------------------------------------
    # STEP 4: Wait for image editor
    # --------------------------------------------------------

    print("    Waiting for image editor...")

    send_media = page.get_by_role(
        "button",
        name="Send 1 selected",
        exact=True,
    )

    send_media.wait_for(
        state="visible",
        timeout=15000,
    )

    print("    Image editor opened.")

    # --------------------------------------------------------
    # STEP 5: Find caption field
    # --------------------------------------------------------

    print("    Looking for caption field...")

    caption_box = page.locator(
        '[data-testid="media-caption-input-container"]'
    )

    caption_box.wait_for(
        state="visible",
        timeout=10000,
    )

    print("    Caption field found.")

    # --------------------------------------------------------
    # STEP 6: Enter caption
    # --------------------------------------------------------

    print("    Entering caption...")

    caption_box.fill(message)

    print("    Caption entered.")

    # Give WhatsApp time to update the media preview
    page.wait_for_timeout(1000)

    # --------------------------------------------------------
    # STEP 7: Send image + caption
    # --------------------------------------------------------

    print("    Sending image + caption...")

    send_media.click(force=True)

    print("    Send button clicked.")

    # Give WhatsApp time to finish sending
    page.wait_for_timeout(3000)

    # The media editor should disappear after a successful send.
    try:
        send_media.wait_for(
            state="hidden",
            timeout=10000,
        )

        print("    ✓ Media editor closed.")
        print("    ✓ Message sent.")

    except Exception:
        raise RuntimeError(
            "Media editor did not close after sending."
        )


# ============================================================
# BROADCAST
# ============================================================

def broadcast_message(
    message: str,
    image_path: str,
    contacts: list[str],
) -> list[dict]:
    """Send the same image + caption to every contact."""

    results = []

    with sync_playwright() as p:

        print("\nStarting WhatsApp browser...")

        # Use persistent profile so WhatsApp login is remembered
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

        print("WhatsApp browser ready.")

        # ----------------------------------------------------
        # Send to every contact
        # ----------------------------------------------------

        for i, phone in enumerate(
            contacts,
            start=1,
        ):

            print(
                f"\n[{i}/{len(contacts)}] "
                f"Sending to {phone}..."
            )

            try:

                send_whatsapp_message(
                    page=page,
                    phone=phone,
                    message=message,
                    image_path=image_path,
                )

                results.append({
                    "phone": phone,
                    "status": "sent",
                })

            except Exception as e:

                print(f"    ✗ Failed -> {phone}")
                print(f"      Error: {e}")

                results.append({
                    "phone": phone,
                    "status": "failed",
                    "error": str(e),
                })

            # ------------------------------------------------
            # Delay before next recipient
            # ------------------------------------------------

            if i < len(contacts):

                print(
                    f"    Waiting "
                    f"{DELAY_BETWEEN_SENDS} seconds..."
                )

                time.sleep(
                    DELAY_BETWEEN_SENDS
                )

        # ----------------------------------------------------
        # Close browser
        # ----------------------------------------------------

        context.close()

    return results


# ============================================================
# MAIN WORKFLOW
# ============================================================

def run_broadcast() -> None:
    """Run the complete photo + text broadcast workflow."""

    print("\n===================================")
    print("      WhatsApp Broadcast Agent")
    print("===================================\n")

    # --------------------------------------------------------
    # Load contacts
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

    if not os.path.isfile(image_path):

        print(
            f"Image not found: {image_path}"
        )

        return

    print(
        f"Image: {image_path}"
    )

    # --------------------------------------------------------
    # Get message / caption
    # --------------------------------------------------------

    print(
        "\nEnter the message/caption "
        "you want to send."
    )

    print(
        "Type your message and press ENTER.\n"
    )

    message = input("> ").strip()

    if not message:

        print(
            "Message cannot be empty."
        )

        return

    # --------------------------------------------------------
    # Preview
    # --------------------------------------------------------

    print("\n===================================")
    print("        BROADCAST PREVIEW")
    print("===================================\n")

    print(
        f"Image: {image_path}"
    )

    print("\nCaption:")
    print("-----------------------------------")
    print(message)
    print("-----------------------------------")

    print(
        f"\nRecipients: {len(contacts)}"
    )

    print("===================================\n")

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
    # Start broadcast
    # --------------------------------------------------------

    print("\nBroadcast starting...")

    print(
        "Keep WhatsApp Web/browser visible."
    )

    print()

    results = broadcast_message(
        message=message,
        image_path=image_path,
        contacts=contacts,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    sent = sum(
        1
        for result in results
        if result["status"] == "sent"
    )

    failed = sum(
        1
        for result in results
        if result["status"] == "failed"
    )

    print("\n===================================")
    print("         BROADCAST COMPLETE")
    print("===================================")

    print(
        f"Total:   {len(results)}"
    )

    print(
        f"Sent:    {sent}"
    )

    print(
        f"Failed:  {failed}"
    )

    print("===================================\n")

    # Show failures
    if failed:

        print("Failed numbers:")

        for result in results:

            if result["status"] == "failed":

                print(
                    f"  - {result['phone']}"
                )

                print(
                    f"    {result['error']}"
                )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_broadcast()