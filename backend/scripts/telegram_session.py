#!/usr/bin/env python3
"""Одноразова авторизація Telethon → TELEGRAM_SESSION_STRING у кореневому .env

У корені репозиторію (.env):
  TELEGRAM_API_ID, TELEGRAM_API_HASH — обовʼязково

Інтерактивно (термінал запитає телефон і код):
  cd backend && pip install -r requirements.txt && python scripts/telegram_session.py

З TELEGRAM_PHONE у .env:
  Рекомендовано — один запуск у звичайному терміналі: SMS → введіть код у консолі в тому ж запуску.
  Альтернатива — два запуски з TELEGRAM_LOGIN_CODE у .env (код швидко прострочується).
  Назва змінної коду лише: TELEGRAM_LOGIN_CODE (регістр важливий).
  Після успіху TELEGRAM_SESSION_STRING записується в .env. За 2FA: TELEGRAM_2FA_PASSWORD.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _ROOT / ".env"
_TMP_SESSION = _ROOT / ".telegram_login_tmp.session"
_PHONE_HASH_PATH = _ROOT / ".telegram_login_phone_hash"

load_dotenv(_ENV_PATH)

import os

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


def _write_session_string_to_env(session_string: str) -> None:
    if not _ENV_PATH.is_file():
        print(f"Помилка: немає файлу {_ENV_PATH}", file=sys.stderr)
        raise SystemExit(1)
    raw = _ENV_PATH.read_text(encoding="utf-8")
    key = "TELEGRAM_SESSION_STRING="
    lines = raw.splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(key):
            out.append(f"{key}{session_string}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}{session_string}")
    _ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nЗаписано у {_ENV_PATH}: TELEGRAM_SESSION_STRING\n")


async def _export_session(client: TelegramClient) -> str:
    return StringSession.save(client.session)


async def _login_with_phone(
    api_id: str,
    api_hash: str,
    phone: str,
    code: str,
    password: str,
) -> None:
    # Між двома запусками процесу SQLite-сесія не завжди зберігає phone_code_hash;
    # тому hash зберігаємо окремо після send_code_request (див. Telethon sign_in).
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    try:
        await client.connect()
        if await client.is_user_authorized():
            sess = await _export_session(client)
            _write_session_string_to_env(sess)
            _PHONE_HASH_PATH.unlink(missing_ok=True)
            _TMP_SESSION.unlink(missing_ok=True)
            return

        if code:
            if not _PHONE_HASH_PATH.is_file():
                print(
                    "Немає збереженого кроку входу. Приберіть TELEGRAM_LOGIN_CODE з .env "
                    "і запустіть скрипт один раз (надішлемо SMS знову).",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            phone_code_hash = _PHONE_HASH_PATH.read_text(encoding="utf-8").strip()
            try:
                await client.sign_in(
                    phone, code, phone_code_hash=phone_code_hash
                )
            except SessionPasswordNeededError:
                if not password:
                    print(
                        "Потрібен пароль двофакторної автентифікації. "
                        "Додайте TELEGRAM_2FA_PASSWORD у .env і запустіть знову.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from None
                await client.sign_in(password=password)
            sess = await _export_session(client)
            _write_session_string_to_env(sess)
            _PHONE_HASH_PATH.unlink(missing_ok=True)
            _TMP_SESSION.unlink(missing_ok=True)
        else:
            sent = await client.send_code_request(phone)
            phone_code_hash = sent.phone_code_hash
            _PHONE_HASH_PATH.write_text(phone_code_hash, encoding="utf-8")
            if sys.stdin.isatty():
                print(
                    "\nSMS надіслано. Введіть код із Telegram і натисніть Enter "
                    "(той самий запуск, код не встигне прострочитися):\n",
                    flush=True,
                )
                loop = asyncio.get_event_loop()
                inline = await loop.run_in_executor(
                    None, lambda: input("Код: ").strip()
                )
                try:
                    await client.sign_in(
                        phone, inline, phone_code_hash=phone_code_hash
                    )
                except SessionPasswordNeededError:
                    pwd_use = password
                    if not pwd_use:
                        pwd_use = await loop.run_in_executor(
                            None,
                            lambda: input(
                                "Пароль 2FA (або додайте TELEGRAM_2FA_PASSWORD у .env): "
                            ).strip(),
                        )
                    if not pwd_use:
                        print(
                            "Додайте TELEGRAM_2FA_PASSWORD у .env і запустіть знову.",
                            file=sys.stderr,
                        )
                        raise SystemExit(1) from None
                    await client.sign_in(password=pwd_use)
                sess = await _export_session(client)
                _write_session_string_to_env(sess)
                _PHONE_HASH_PATH.unlink(missing_ok=True)
                _TMP_SESSION.unlink(missing_ok=True)
            else:
                print(
                    "\nSMS надіслано. Додайте в .env рядок "
                    "TELEGRAM_LOGIN_CODE=код і запустіть цей скрипт ще раз "
                    "(швидко — код прострочується).\n",
                    file=sys.stderr,
                )
    finally:
        await client.disconnect()


async def main() -> None:
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print(
            "Помилка: задайте TELEGRAM_API_ID та TELEGRAM_API_HASH "
            f"у файлі {_ENV_PATH} (my.telegram.org).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    phone = os.environ.get("TELEGRAM_PHONE", "").strip()
    code = os.environ.get("TELEGRAM_LOGIN_CODE", "").strip()
    if not code:
        code = os.environ.get("Telegram_Login_Code", "").strip()
    password = os.environ.get("TELEGRAM_2FA_PASSWORD", "").strip()

    if phone:
        if not re.match(r"^\+\d{10,15}$", phone):
            print(
                "Підказка: TELEGRAM_PHONE має бути у форматі +380XXXXXXXXX (код країни з +).",
                file=sys.stderr,
            )
        await _login_with_phone(api_id, api_hash, phone, code, password)
        return

    if not sys.stdin.isatty():
        print(
            "Немає інтерактивного вводу. Додайте у .env TELEGRAM_PHONE=+380... "
            "і двічі запустіть скрипт (другий раз — з TELEGRAM_LOGIN_CODE після SMS). "
            "Або запустіть цей скрипт у звичайному терміналі без перенаправлення stdin.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.start()
        sess = client.session.save()
        _write_session_string_to_env(sess)
        print("Готово. Перезапустіть collector: docker compose up -d --build collector\n")


if __name__ == "__main__":
    asyncio.run(main())
