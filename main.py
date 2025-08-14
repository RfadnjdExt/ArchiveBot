import unicodedata
import sys
import json
import os
import signal
import asyncio
import logging
from datetime import timedelta

import aiohttp
import discord
from discord import Object
from dotenv import load_dotenv
import re

load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN")
SOURCE_CHANNEL  = int(os.getenv("SOURCE_CHANNEL_ID") or 0)
TARGET_CHANNEL  = int(os.getenv("TARGET_CHANNEL_ID") or 0)

if not (BOT_TOKEN and SOURCE_CHANNEL and TARGET_CHANNEL):
    logging.error("Missing env vars")
    sys.exit(1)

DELAY            = 1.5
GROUP_SECONDS    = 300
MAX_FILE_SIZE    = 10 * 1024 * 1024
MAX_CONTENT      = 2000
WEBHOOK_NAME     = "Chat Exporter Bot"
PROGRESS_FILE    = "progress.json"
MAX_LEWD_HOST_SIZE = 512 * 1024 * 1024

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)

def log(msg: str, level: str = "INFO") -> None:
    logging.log(getattr(logging, level), msg)

def _is_single_emoji(txt: str) -> bool:
    """
    Return True if *txt* is a single emoji message.

    The message can be:
      * a “standard” Unicode emoji ( 🤔, 😎…, 👨‍👩‍👧, … )
      * or a Discord‑style custom emoji:  <a:emoji_name:123456789>  or  <:emoji_name:123456789>
    """
    txt = txt.strip()
    if not txt:
        return False

    if re.fullmatch(r"<a?:[^:\s]+:\d+>", txt):
        return True

    return all(
        unicodedata.category(ch)[0] not in ("L", "N", "P", "Z")
        for ch in txt
    )

def _split_text(txt: str, limit: int = MAX_CONTENT) -> list[str]:
    """Return the text split into chunks no longer than *limit*."""
    if len(txt) <= limit:
        return [txt]

    chunks: list[str] = []
    while txt:
        cut = txt.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(txt[:cut])
        txt = txt[cut:]
    return chunks

def _read_progress() -> int | None:
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("last_processed_id", 0)) or None
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None

def _write_progress(msg_id: int) -> None:
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_processed_id": msg_id}, f)

async def _post_json(session: aiohttp.ClientSession, url: str, payload: dict):
    for attempt in range(1, 4):
        try:
            async with session.post(url, json=payload) as r:
                if r.status in (503, 429):
                    backoff = 5 * attempt if r.status == 503 else (await r.json()).get("retry_after", 5)
                    log(f"Rate‑limit {r.status} – retry {backoff}s (attempt {attempt})", "WARN")
                    await asyncio.sleep(backoff)
                    continue
                if not r.ok:
                    err = await r.text()
                    raise RuntimeError(f"Webhook error {r.status}: {err}")
                await asyncio.sleep(DELAY)
                return
        except aiohttp.ClientError as exc:
            if attempt == 3:
                raise RuntimeError(f"JSON POST failed: {exc}") from exc
            await asyncio.sleep(5 * attempt)

async def _post_file(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    file_bytes: bytes,
    filename: str,
):
    form = aiohttp.FormData()
    form.add_field("payload_json", json.dumps(payload))
    form.add_field("file", file_bytes, filename=filename)

    for attempt in range(1, 4):
        try:
            async with session.post(url, data=form) as r:
                if r.status == 429:
                    wait = (await r.json()).get("retry_after", 5)
                    log(f"File rate‑limit – retry {wait}s (attempt {attempt})", "WARN")
                    await asyncio.sleep(wait)
                    continue
                if not r.ok:
                    err = await r.text()
                    raise RuntimeError(f"File webhook error {r.status}: {err}")
                await asyncio.sleep(DELAY)
                return
        except aiohttp.ClientError as exc:
            if attempt == 3:
                raise RuntimeError(f"File POST failed: {exc}") from exc
            await asyncio.sleep(5 * attempt)

async def _upload_to_host(session: aiohttp.ClientSession, data: bytes, name: str) -> str | None:
    """
    Upload *data* to lewd.host.  Returns the public URL or ``None``.
    Files larger than :data:`MAX_LEWD_HOST_SIZE` are skipped with a warning.
    """
    if len(data) > MAX_LEWD_HOST_SIZE:
        log(f"❌ Skipping upload of {name} ({len(data)/2**20:.2f} MiB) – >512 MiB", "WARN")
        return None

    headers = {"albumid": "905", "token": os.getenv("LEWDHOST_TOKEN")}
    form = aiohttp.FormData()
    form.add_field("files[]", data, filename=name, content_type="application/octet-stream")

    try:
        async with session.post("https://lewd.host/api/upload", data=form, headers=headers) as r:
            if r.status != 200:
                txt = await r.text()
                log(f"Upload failed: HTTP {r.status} – {txt}", "ERROR")
                return None
            resp = await r.json()
            if not resp.get("success"):
                log(f"Invalid lewd.host reply: {resp}", "ERROR")
                return None
            files = resp.get("files", [])
            if not files:
                log("lewd.host gave no URLs", "ERROR")
                return None
            return files[0].get("url")
    except aiohttp.ClientError as exc:
        log(f"Connection error to lewd.host: {exc}", "ERROR")
        return None

async def _webhook_url(channel: discord.TextChannel) -> str:
    existing = await channel.webhooks()
    for w in existing:
        if w.name == WEBHOOK_NAME:
            return w.url
    return (await channel.create_webhook(name=WEBHOOK_NAME, reason="Chat export")).url

async def _send_text_batch(session, url, author, messages):
    parts = [m.clean_content for m in messages if m.clean_content.strip()]
    if not parts:
        return

    base = {
        "username": author.display_name,
        "avatar_url": author.display_avatar.url,
        "allowed_mentions": {"parse": []},
    }

    full = "\n".join(parts)

    if _is_single_emoji(full):
        await _post_json(session, url, {**base, "content": full})
        ts = int(messages[-1].created_at.timestamp())
        await _post_json(session, url, {**base, "content": f"> <t:{ts}:R>"})
        return

    ts = int(messages[-1].created_at.timestamp())
    ts_block = f"\n> <t:{ts}:R>"
    chunks = _split_text(full)          
    for i, chunk in enumerate(chunks):
        payload = {**base,
                   "content": chunk + (ts_block if i == len(chunks) - 1 else "")}
        await _post_json(session, url, payload)

async def _send_attachments(session, url, author, attachment_pairs):
    base = {
        "username": author.display_name,
        "avatar_url": author.display_avatar.url,
        "allowed_mentions": {"parse": []},
    }

    for att, msg in attachment_pairs:
        log(f"→ {att.filename} ({att.size/2**20:.2f} MiB)")
        raw = await att.read()

        if att.size <= MAX_FILE_SIZE:
            await _post_file(session, url, {**base, "content": ""}, raw, att.filename)

        else:
            shared = await _upload_to_host(session, raw, att.filename)
            if shared:
                await _post_json(session, url, {**base, "content": shared})
            else:

                log(f"⚠️  Skipped {att.filename} – upload to lewd.host tidak berhasil.", "WARN")
                continue

        ts = int(msg.created_at.timestamp())
        await _post_json(session, url, {**base, "content": f"> <t:{ts}:R>"})

async def main():
    intents = discord.Intents.default()
    intents.messages = True
    bot = discord.Client(intents=intents)

    session = aiohttp.ClientSession()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(
        signal.SIGINT,
        lambda: asyncio.create_task(bot.close())
    )

    @bot.event
    async def on_ready():
        log("Bot connected – starting export")

        src = bot.get_channel(SOURCE_CHANNEL)
        tgt = bot.get_channel(TARGET_CHANNEL)
        webhook = await _webhook_url(tgt)

        last_id = _read_progress()
        log(f"Resume from {last_id or 'first'}")
        gap = timedelta(seconds=GROUP_SECONDS)

        cur_user = None
        cur_msgs = []
        cur_last = None
        after = Object(id=last_id) if last_id else None

        async for msg in src.history(limit=None, after=after, oldest_first=True):
            if cur_user and (
                msg.author != cur_user or (msg.created_at - cur_last.created_at) > gap
            ):
                await _send_text_batch(session, webhook, cur_user, cur_msgs)
                await _send_attachments(
                    session,
                    webhook,
                    cur_user,
                    [(a, m) for m in cur_msgs for a in m.attachments],
                )
                _write_progress(cur_last.id)
                cur_user = None
                cur_msgs = []

            cur_user = msg.author
            cur_msgs.append(msg)
            cur_last = msg

        if cur_user and cur_msgs:
            await _send_text_batch(session, webhook, cur_user, cur_msgs)
            await _send_attachments(
                session,
                webhook,
                cur_user,
                [(a, m) for m in cur_msgs for a in m.attachments],
            )
            _write_progress(cur_last.id)

        log("Export finished")

    try:
        await bot.start(BOT_TOKEN)
    finally:

        await session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:

        sys.exit(0)