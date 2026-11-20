#!/usr/bin/env python3
"""
Ayudante de Telegram.

  python telegram.py configurar        -> busca tu chat_id (después de escribirle "hola" a tu bot) y lo guarda
  python telegram.py probar            -> te manda un mensaje de prueba
  python telegram.py enviar "texto"    -> manda un texto (lo usan los resúmenes de Claude)
  python telegram.py enviar-archivo r  -> manda el contenido de un archivo de texto
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONFIG = Path(__file__).resolve().parent / "config.json"
SECRETO = Path(__file__).resolve().parent / "secreto.json"


def credenciales():
    """Token y chat_id: primero variables de entorno (nube), luego secreto.json (PC)."""
    import os
    try:
        d = json.loads(SECRETO.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or d.get("bot_token", ""),
            str(os.environ.get("TELEGRAM_CHAT_ID") or d.get("chat_id", "")))


def guardar_credenciales(token=None, chat_id=None):
    t, c = credenciales()
    SECRETO.write_text(json.dumps({"bot_token": token if token is not None else t,
                                   "chat_id": str(chat_id if chat_id is not None else c)}, indent=2),
                       encoding="utf-8")


def cfg():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def token():
    t = credenciales()[0]
    if not t or "PEGA_AQUI" in t:
        sys.exit("Falta el token del bot. Corre: python telegram.py facil")
    return t


def api(metodo, datos=None):
    return llamar_telegram(token(), metodo, datos)


def llamar_telegram(tok, metodo, datos=None):
    """En esta PC Python no puede conectar con Telegram, pero curl.exe de Windows sí.
    El token va por la entrada estándar (no queda visible en la lista de procesos)."""
    import os
    import subprocess
    curl = "curl.exe" if os.name == "nt" else "curl"
    lineas = [f'url = "https://api.telegram.org/bot{tok}/{metodo}"']
    for k, v in (datos or {}).items():
        lineas.append("data-urlencode = " + json.dumps(f"{k}={v}", ensure_ascii=False))
    import time
    for intento in range(4):  # la conexión a veces se corta: reintenta
        r = subprocess.run([curl, "-s", "--max-time", "20", "-K", "-"],
                           input=chr(10).join(lineas).encode("utf-8"), capture_output=True)
        if r.returncode == 0 and r.stdout:
            break
        time.sleep(2 + intento * 2)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"curl falló (código {r.returncode})")
    resp = json.loads(r.stdout.decode("utf-8"))
    if not resp.get("ok"):
        raise RuntimeError(resp.get("description", "Telegram rechazó la petición"))
    return resp


def enviar(texto):
    chat = credenciales()[1]
    if not chat:
        sys.exit("Falta el chat_id. Corre primero: python telegram.py configurar")
    # Telegram acepta hasta 4096 caracteres por mensaje: se parte en trozos
    partes, actual = [], ""
    for linea in texto.splitlines(keepends=True):
        if len(actual) + len(linea) > 3900:
            partes.append(actual)
            actual = ""
        actual += linea
    partes.append(actual)
    for p in partes:
        if p.strip():
            api("sendMessage", {"chat_id": chat, "text": p, "disable_web_page_preview": "true"})
    print("Enviado ✅")


def configurar():
    r = api("getUpdates")
    chats = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat", {})
        if c.get("id"):
            chats[c["id"]] = c.get("first_name") or c.get("title") or ""
    if not chats:
        sys.exit("No encontré mensajes. Abre tu bot en Telegram, escríbele \"hola\" y vuelve a correr esto.")
    chat_id = list(chats)[-1]
    guardar_credenciales(chat_id=chat_id)
    print(f"Listo ✅ chat_id guardado ({chats[chat_id]}).")
    enviar("✅ Tu vigilante de noticias ya está conectado. Aquí te llegarán las alertas.")


def configurar_facil():
    """Ventanita que pide el token, lo guarda y conecta el chat (sin editar archivos a mano)."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    raiz = tk.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    t = simpledialog.askstring(
        "Vigilante de noticias",
        "Pega aquí el código (token) que te dio BotFather\n(clic en el cuadro y Ctrl+V), luego Aceptar:",
        parent=raiz)
    if not t or ":" not in t:
        messagebox.showerror("Vigilante de noticias", "No pegaste un código válido. Vuelve a intentarlo.", parent=raiz)
        sys.exit("Token no válido o cancelado.")
    guardar_credenciales(token=t.strip())
    for _ in range(5):
        try:
            if api("getUpdates").get("result"):
                break
        except Exception as e:
            messagebox.showerror("Vigilante de noticias", f"Telegram no aceptó el código:\n{e}", parent=raiz)
            sys.exit("Token rechazado por Telegram.")
        messagebox.showinfo("Vigilante de noticias",
                            "Ahora abre tu bot en Telegram, toca INICIAR / START y escríbele: hola\n\n"
                            "Cuando lo hayas hecho, presiona Aceptar.", parent=raiz)
    configurar()
    messagebox.showinfo("Vigilante de noticias", "¡Listo! ✅ Revisa tu Telegram: te llegó un mensaje de prueba.", parent=raiz)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "facil":
        configurar_facil()
    elif sys.argv[1] == "configurar":
        configurar()
    elif sys.argv[1] == "probar":
        enviar("🔔 Prueba del vigilante de noticias: si lees esto, todo funciona.")
    elif sys.argv[1] == "enviar":
        enviar(" ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read())
    elif sys.argv[1] == "enviar-archivo":
        enviar(Path(sys.argv[2]).read_text(encoding="utf-8"))
    else:
        print(__doc__)
