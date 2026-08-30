# WhatsApp Broadcast Agent

Give it a plain-English instruction, and it sends that message to every
contact in your list over WhatsApp.

## How it works
1. You type something like: `Tell everyone the trip is postponed to Sunday`
2. An LLM (gpt-4o-mini) reads that and extracts the exact message to send —
   this is the "agent" step
3. It loops through `contacts.json` and sends the message to each person via
   your own WhatsApp account (WhatsApp Web automation, using `pywhatkit`)
4. A short pause is added between sends so it doesn't fire off a burst of
   messages back-to-back

## Why this approach (and not Twilio / Meta's official API)
The official WhatsApp Business APIs (Twilio, Meta Cloud API) are the more
"correct" way to send programmatically, but they come with a real catch for
this use case: you can only send free-form text to someone **after they've
messaged you first** (or you use a pre-approved template). For Twilio's free
sandbox specifically, every recipient has to text a join code once before
they can receive anything from you — which defeats the point of quietly
broadcasting to a personal contact list.

`pywhatkit` instead just automates your own WhatsApp Web session, so it can
message anyone the way you'd message them by hand — no opt-in step. The
trade-off is that it's unofficial automation, not an approved API, so:
- Keep it to small, personal-scale lists, not bulk/commercial messaging
- Don't run it at high frequency — WhatsApp can flag accounts that message
  in an obviously bot-like pattern
- If this ever needs to scale to strangers or a business use case, switch to
  Twilio's WhatsApp API or Meta's Cloud API instead (see below)

## Setup
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Open web.whatsapp.com in your **default browser** and stay logged in —
   pywhatkit drives that session
3. Copy `.env.example` to `.env` and add your OpenAI API key
4. Copy `contacts.example.json` to `contacts.json` and fill in your list.
   Phone numbers need the full international format: `+<country code><number>`
5. Run it:
   ```
   python whatsapp_agent.py
   ```
6. When prompted, describe what to send, e.g.:
   `Send everyone a reminder that the meetup starts at 6 PM tomorrow`

## Caveats worth knowing before you run it
- A browser tab opens briefly for each contact — keep the window visible;
  pywhatkit works by simulating keystrokes into the page
- Needs an actual display — it won't run headless or on a remote server
- Test on your own number first before pointing it at the full list
- If a send fails partway through, everyone before it has already received
  the message — there's no "undo"

## If you outgrow this
Swap `send_whatsapp_message()` for a Twilio or Meta Cloud API call. The rest
of the agent (instruction → LLM → `broadcast_message`) stays the same —
only the sending function changes. That's the point of keeping sending as
its own function: the transport is a one-line swap later.
