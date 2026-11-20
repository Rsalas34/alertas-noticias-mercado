#!/usr/bin/env python3
"""
Vigilante de noticias que mueven el mercado — Robinson.

Revisa fuentes RSS cada pocos minutos, le pone puntaje a cada noticia
según su capacidad de mover el mercado o tus acciones, y te manda
una alerta por Telegram cuando pasa el umbral.

Uso:
  python vigilante.py              -> corre sin parar (modo normal)
  python vigilante.py --una-vez    -> revisa una sola vez y termina
  python vigilante.py --prueba     -> NO envía nada: muestra en pantalla qué alertaría
  python vigilante.py --prueba --todas  -> muestra también las de puntaje bajo

Solo usa librerías que ya trae Python (no hay que instalar nada).
"""
import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CARPETA = Path(__file__).resolve().parent
CONFIG = CARPETA / "config.json"
ESTADO = CARPETA / "estado.json"
LOG = CARPETA / "alertas.log"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

# ---------------------------------------------------------------- puntaje
FUENTES = {
    "reuters": 5, "bloomberg": 5, "wall street journal": 5, "wsj": 5, "dow jones": 5,
    "financial times": 5, "federal reserve": 6, "cnbc": 4, "barron": 4, "marketwatch": 4,
    "associated press": 4, "new york times": 4, "ap news": 4, "fox business": 3,
    "yahoo finance": 3, "investor's business daily": 3, "axios": 3, "business insider": 2,
    "benzinga": 2, "seeking alpha": 1, "motley fool": 0, "zacks": 0, "marketbeat": 0,
    "247wallst": 0, "24/7 wall st": 0, "gurufocus": 0, "simply wall st": 0, "tipranks": 1,
}

RUIDO = re.compile("|".join([
    r"transcript", r"class action", r"lead plaintiff", r"investor alert", r"shareholder (notice|alert)",
    r"securities fraud", r"law firm", r"\bllp\b", r"did you lose money", r"investigation (continues|of|announced)",
    r"faruqi", r"rosen law", r"pomerantz", r"key metrics", r"what you should know", r"\bbetter buy\b",
    r"should you buy", r"is it time to buy", r"stocks? to buy", r"millionaire", r"retire(ment)?\b",
    r"social security", r"dividend stock", r"\bpodcast\b", r"\bquiz\b", r"\bopinion\b", r"\breview:",
    r"price prediction", r"top \d+ ", r"\d+ (stocks|reasons|things)", r"watchlist", r"how to ",
    r"mortgage rates? today", r"cd rates", r"savings rates", r"credit card",
]), re.I)

# (etiqueta, peso, regex)
TEMAS = [
    ("FED / TASAS", 7, r"\bfed\b|federal reserve|fomc|powell|warsh|rate (hike|cut)s?|interest rates?|basis points?|"
                       r"\bbps\b|dot plot|fed minutes|monetary policy"),
    ("BONOS", 5, r"treasury yields?|bond yields?|10-year|2-year|yields? (surge|jump|spike|soar|fall|drop|tumble)|"
                 r"bond market|treasury auction"),
    ("INFLACIÓN", 7, r"\bcpi\b|\bppi\b|\bpce\b|inflation|consumer prices|producer prices"),
    ("EMPLEO", 6, r"payrolls?|jobs report|unemployment rate|jobless claims|nonfarm|labor market"),
    ("ECONOMÍA", 4, r"\bgdp\b|retail sales|recession|\bism\b|manufacturing (index|activity)|"
                    r"consumer (confidence|sentiment)|housing starts"),
    ("ARANCELES / COMERCIO", 6, r"tariffs?|trade war|trade deal|trade talks|export controls?|sanctions?|"
                                r"chip (ban|curbs?|controls?)|duties"),
    ("GEOPOLÍTICA", 6, r"\bwar\b|missiles?|airstrikes?|attack|invasion|invades?|ceasefire|military|taiwan|iran|"
                       r"israel|ukraine|russia|north korea|strait of hormuz|nuclear"),
    ("GOBIERNO", 3, r"shutdown|debt ceiling|white house|congress|senate|trump|executive order|supreme court"),
    ("PETRÓLEO", 5, r"\bopec\+?|crude|oil prices?|brent|\bwti\b|natural gas|oil supply"),
    ("DÓLAR", 3, r"dollar index|\bdollar\b|\byen\b|\byuan\b|currency"),
    ("ORO / PLATA", 3, r"\bgold\b|\bsilver\b|bullion"),
    ("SHOCK EMPRESA", 7, r"resigns?|steps down|ousted|fired|ceo (exit|departure)|bankrupt|chapter 11|fraud|"
                         r"probe|subpoena|\bdoj\b|antitrust|sec (charges|probe|investigation)|recall|"
                         r"trading halted|halts? trading|downgrades?|upgrades?|"
                         r"(cuts|raises|slashes|lowers|boosts|withdraws) (its |full-year |annual )?(guidance|forecast|outlook)|"
                         r"profit warning|layoffs|data breach|hack"),
    ("FUSIONES", 5, r"acquires?|acquisition|merger|takeover|buyout|in talks to (buy|acquire)|deal to buy|to buy .* for \$"),
    ("RESULTADOS", 4, r"earnings|quarterly (results|revenue|profit)|\beps\b|revenue (beat|miss)|"
                      r"(beats|misses|tops) (estimates|expectations)"),
    ("IA / CHIPS", 3, r"\bai\b|artificial intelligence|semiconductors?|chipmakers?|data centers?|\bgpus?\b"),
    ("MERCADO", 4, r"s&p 500|nasdaq|dow jones|stock market|sell-?off|selloff|rally|correction|bear market|"
                   r"volatility|\bvix\b|stocks (fall|tumble|slide|sink|plunge|rise|jump|surge|soar)|futures"),
    ("CRIPTO", 2, r"bitcoin|crypto"),
]
TEMAS_RE = [(n, p, re.compile(rx, re.I)) for n, p, rx in TEMAS]

FUERTE = re.compile(
    r"plunge|plummet|crash|soar|surge|tumble|sink|skyrocket|biggest .* since|record|shock|emergency|unexpected|"
    r"surprise|historic|halt|collapse|resign|rattle|turmoil|spike|slump|breaking|just in|urgent|"
    r"worst|best day|meltdown|panic", re.I)

# Frases que casi siempre mueven todo el mercado: alerta alta directa
BOMBA = re.compile(
    r"fed (cuts|raises|hikes|holds)|(cuts|raises|hikes) (interest )?rates|emergency (rate|meeting)|"
    r"powell (says|signals|warns)|cpi (rises|jumps|falls|cools|hotter|cooler)|inflation (unexpectedly|surges|cools)|"
    r"jobs report|payrolls (surge|plunge|rise|fall|miss|beat)|"
    r"(imposes|announces|raises|slaps) .*tariffs|tariffs? on (china|mexico|canada|europe|eu|imports|chips|semiconductors)|"
    r"trading halted|circuit breaker|declares war|invades|airstrikes? on|ceasefire|strait of hormuz|"
    r"(opec\+?) (cuts|boosts|agrees)|bankruptcy|chapter 11|downgrades? (u\.s\.|us) (credit|debt)|"
    r"government shutdown|ceo (resigns|steps down|ousted)", re.I)

OPINION = re.compile(
    r"\?|^(why|how|what|is|are|should|could|can|will) |(could|may|might) (be|move|rise|fall)|opportunity|"
    r"here's|heres|my (top|thoughts)|our thoughts|i'm buying|takeaways|things to watch|explained|analysis:", re.I)

MEGA = {"NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX", "JPM", "TSM"}

MEGA_PALABRAS = {
    "NVDA": "nvidia", "AAPL": "apple", "MSFT": "microsoft", "AMZN": "amazon", "GOOGL": "alphabet|google",
    "META": "meta platforms|\\bmeta\\b", "TSLA": "tesla", "AVGO": "broadcom", "AMD": "\\bamd\\b",
    "NFLX": "netflix", "JPM": "jpmorgan", "TSM": "tsmc|taiwan semiconductor",
}
MEGA_RE = {k: re.compile(v, re.I) for k, v in MEGA_PALABRAS.items()}


# ---------------------------------------------------------------- utilidades
def leer_json(ruta, defecto):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return defecto


def guardar_json(ruta, obj):
    Path(ruta).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def log(msg):
    linea = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linea, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


def descargar(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def limpiar(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    return re.sub(r"\s+", " ", t).strip()


def fecha(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def clave(titulo):
    t = re.sub(r"\W+", " ", titulo.lower()).strip()
    return hashlib.md5(t[:120].encode()).hexdigest()[:16]


def palabras(t):
    return {w for w in re.findall(r"[a-z0-9&]+", t.lower()) if len(w) > 3}


def parecido(a, b):
    a, b = palabras(a), palabras(b)
    if not a or not b:
        return 0
    return len(a & b) / min(len(a), len(b))


# ---------------------------------------------------------------- fuentes
def leer_rss(fuente, vigilados):
    url = fuente["url"]
    if url == "YAHOO_VIGILADOS":
        acciones = [v["precio"] for v in vigilados.values()
                    if re.fullmatch(r"[A-Z]{1,5}", v.get("precio", ""))]
        url = ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=" + ",".join(acciones)
               + "&region=US&lang=en-US")
    raiz = ET.fromstring(descargar(url))
    salida = []
    items = raiz.findall(".//item")
    atom = "{http://www.w3.org/2005/Atom}"
    if not items:
        items = raiz.findall(f".//{atom}entry")
    for it in items:
        def txt(tag):
            e = it.find(tag)
            if e is None:
                e = it.find(atom + tag)
            return (e.text or "") if e is not None else ""
        titulo = limpiar(txt("title"))
        link = txt("link")
        if not link:
            e = it.find(atom + "link")
            link = e.get("href", "") if e is not None else ""
        editor = fuente["nombre"]
        src = it.find("source")
        if src is not None and src.text:  # Google Noticias trae el medio real
            editor = src.text.strip()
            titulo = re.sub(r"\s+-\s+" + re.escape(editor) + r"$", "", titulo)
        if not titulo:
            continue
        salida.append({
            "titulo": titulo,
            "resumen": limpiar(txt("description") or txt("summary"))[:400],
            "fuente": editor,
            "peso_fuente": fuente.get("peso", 0),
            "fecha": fecha(txt("pubDate") or txt("published") or txt("updated")),
            "url": link.strip(),
        })
    return salida


def peso_editor(nombre, peso_dado):
    if peso_dado:
        return peso_dado
    n = nombre.lower()
    for k, v in FUENTES.items():
        if k in n:
            return v
    return 1


# ---------------------------------------------------------------- análisis
def puntuar(n, vigilados_re):
    texto = n["titulo"] + " " + n["resumen"][:300]
    if RUIDO.search(n["titulo"]):
        return None
    temas = [(nom, p) for nom, p, rx in TEMAS_RE if rx.search(texto)]
    pf = peso_editor(n["fuente"], n["peso_fuente"])
    if pf == 0:
        return None
    score = pf * 2 + sum(p for _, p in sorted(temas, key=lambda x: -x[1])[:3])
    motivos = []
    if FUERTE.search(n["titulo"]):
        score += 4
        motivos.append("lenguaje de impacto")
    tuyos = [t for t, rx in vigilados_re.items() if rx.search(texto)]
    if tuyos:
        score += 6
        motivos.append("tus tickers: " + ", ".join(tuyos[:5]))
    megas = [t for t, rx in MEGA_RE.items() if rx.search(n["titulo"])]
    if megas:
        score += 3
        motivos.append("mega-cap: " + ", ".join(megas))
    if OPINION.search(n["titulo"]):
        score -= 6  # preguntas, opiniones y "podría" no son noticia dura
    if pf <= 1:
        score -= 3  # medio desconocido: necesita más para alertar
    bomba = bool(BOMBA.search(n["titulo"])) and pf >= 3
    if bomba:
        score += 10
        motivos.insert(0, "noticia de las que mueven todo el mercado")
    return {
        **n, "puntaje": score, "temas": [t for t, _ in temas[:3]], "tuyos": tuyos,
        "megas": megas, "motivos": motivos, "bomba": bomba, "peso": pf,
    }


def traducir(texto):
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=es&dt=t&q="
               + urllib.parse.quote(texto))
        data = json.loads(descargar(url, timeout=8))
        return "".join(p[0] for p in data[0] if p and p[0]) or texto
    except Exception:
        return texto


def precio(simbolo):
    """Cambio % de hoy desde Yahoo (dato aproximado, puede venir con retraso)."""
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               + urllib.parse.quote(simbolo) + "?range=1d&interval=5m")
        m = json.loads(descargar(url, timeout=8))["chart"]["result"][0]["meta"]
        ultimo = m.get("regularMarketPrice")
        prev = m.get("chartPreviousClose") or m.get("previousClose")
        if ultimo and prev:
            return ultimo, (ultimo / prev - 1) * 100
    except Exception:
        pass
    return None


def es_de_noche(cfg):
    ini, fin = cfg.get("horario_noche", ["21:00", "06:00"])
    ahora = datetime.now().strftime("%H:%M")
    return ahora >= ini or ahora < fin if ini > fin else ini <= ahora < fin


def armar_mensaje(a, cfg, vigilados):
    nivel = "🔴 ALERTA ALTA" if a["nivel"] == "alta" else "🟠 ALERTA MEDIA"
    titulo = traducir(a["titulo"]) if cfg.get("traducir_al_espanol", True) else a["titulo"]
    hora = a["fecha"].astimezone().strftime("%H:%M") if a["fecha"] else "?"
    lineas = [f"{nivel} · {', '.join(a['temas'][:2]) or 'NOTICIA'}",
              "",
              f"📰 {titulo}",
              f"🕒 {hora} NY · {a['fuente']}"]
    if a["motivos"]:
        lineas.append("💡 Por qué: " + "; ".join(a["motivos"]))
    if cfg.get("mostrar_precio", True):
        simbolos = []
        for t in a["tuyos"] + a["megas"]:
            s = vigilados.get(t, {}).get("precio", t)
            if s not in simbolos:
                simbolos.append(s)
        for s in (["SPY"] + [x for x in simbolos if x != "SPY"])[:4]:
            p = precio(s)
            if p:
                lineas.append(f"📈 {s}: {p[0]:.2f} ({p[1]:+.1f} % hoy)")
        lineas.append("(Confirma con el precio antes de operar.)")
    if a["url"]:
        lineas.append(a["url"])
    return "\n".join(lineas)


def enviar_telegram(cfg, texto):
    from telegram import credenciales
    token, chat = credenciales()
    if not token or "PEGA_AQUI" in token or not chat:
        log("⚠️ Telegram no está configurado (falta el token o el chat_id).")
        return False
    try:
        from telegram import llamar_telegram
        llamar_telegram(token, "sendMessage", {"chat_id": chat, "text": texto[:4000],
                                               "disable_web_page_preview": "true"})
        return True
    except Exception as e:
        log(f"⚠️ No pude enviar a Telegram: {e}")
        return False


# ---------------------------------------------------------------- ciclo
def revisar(cfg, estado, prueba=False, todas=False, primera=False):
    vigilados = cfg.get("vigilados", {})
    # El ticker (ej. "NVDA") solo cuenta en MAYÚSCULAS; las palabras ("nvidia") sin importar mayúsculas.
    vig_re = {}
    for t, v in vigilados.items():
        palabras_t = [re.escape(p) for p in v.get("palabras", []) if p]
        rx = r"\b" + re.escape(t) + r"\b"
        if palabras_t:
            rx += "|(?i:" + "|".join(palabras_t) + ")"
        vig_re[t] = re.compile(rx)

    noticias, fallas = [], []
    for f in cfg.get("fuentes_rss", []):
        try:
            noticias += leer_rss(f, vigilados)
        except Exception as e:
            fallas.append(f"{f['nombre']}: {type(e).__name__}")
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(minutes=cfg.get("ignorar_noticias_mas_viejas_de_minutos", 90))

    vistas = estado.setdefault("vistas", {})
    enviadas = estado.setdefault("enviadas", [])  # [{titulo, ts}]
    candidatas = []
    for n in noticias:
        k = clave(n["titulo"])
        if k in vistas and not prueba:
            continue
        vistas[k] = ahora.timestamp()
        if n["fecha"] and n["fecha"] < limite and not todas:
            continue
        p = puntuar(n, vig_re)
        if p:
            candidatas.append(p)

    alta, media = cfg.get("umbral_alerta_alta", 24), cfg.get("umbral_alerta_media", 18)
    candidatas.sort(key=lambda x: -x["puntaje"])
    noche = es_de_noche(cfg) and cfg.get("de_noche_solo_alertas_altas", True)
    hace_1h = ahora.timestamp() - 3600
    recientes = [e for e in enviadas if e["ts"] > hace_1h]
    tope = cfg.get("max_alertas_por_hora", 12)

    a_enviar = []
    for c in candidatas:
        if c["bomba"] or c["puntaje"] >= alta:
            c["nivel"] = "alta"
        elif c["puntaje"] >= media and not noche:
            c["nivel"] = "media"
        else:
            if todas:
                print(f"   ({c['puntaje']:>2}) {c['fuente'][:22]:<22} {c['titulo'][:110]}")
            continue
        # misma historia ya avisada en las últimas 6 h -> no repetir
        historico = [e["titulo"] for e in enviadas if e["ts"] > ahora.timestamp() - 6 * 3600]
        historico += [x["titulo"] for x in a_enviar]
        if any(parecido(c["titulo"], h) >= 0.6 for h in historico):
            continue
        a_enviar.append(c)

    if primera and not prueba:
        log(f"Primera revisión: guardé {len(vistas)} noticias como ya vistas (no envío lo viejo).")
        a_enviar = [c for c in a_enviar if c["nivel"] == "alta"][:2]

    enviados_ahora = 0
    for c in a_enviar:
        if len(recientes) + enviados_ahora >= tope and not prueba:
            log("Tope de alertas por hora alcanzado; espero.")
            break
        msg = armar_mensaje(c, cfg, vigilados)
        if prueba:
            print("\n" + "=" * 60 + f"\n[puntaje {c['puntaje']}]\n" + msg)
        else:
            if enviar_telegram(cfg, msg):
                log(f"ENVIADA ({c['nivel']}, {c['puntaje']}): {c['titulo']}")
            enviadas.append({"titulo": c["titulo"], "ts": ahora.timestamp()})
            enviados_ahora += 1

    # limpiar memoria vieja (3 días)
    corte = ahora.timestamp() - 3 * 86400
    estado["vistas"] = {k: v for k, v in vistas.items() if v > corte}
    estado["enviadas"] = [e for e in enviadas if e["ts"] > corte]
    resumen = (f"Revisé {len(noticias)} noticias de {len(cfg.get('fuentes_rss', [])) - len(fallas)} fuentes · "
               f"{len(candidatas)} nuevas relevantes · {len(a_enviar)} alertas")
    if fallas:
        resumen += " · fallaron: " + "; ".join(fallas)
    log(resumen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--una-vez", action="store_true")
    ap.add_argument("--prueba", action="store_true", help="no envía, solo muestra")
    ap.add_argument("--todas", action="store_true", help="con --prueba: muestra también lo que no alerta")
    a = ap.parse_args()

    cfg = leer_json(CONFIG, None)
    if cfg is None:
        print("No pude leer config.json (¿tiene un error de formato?)")
        sys.exit(1)
    estado = leer_json(ESTADO, {})
    primera = not estado.get("vistas")

    if a.prueba or a.una_vez:
        revisar(cfg, estado, prueba=a.prueba, todas=a.todas, primera=primera)
        if not a.prueba:
            guardar_json(ESTADO, estado)
        return

    log("🟢 Vigilante de noticias encendido. Ctrl+C para detenerlo.")
    while True:
        try:
            cfg = leer_json(CONFIG, cfg)  # relee por si cambiaste algo
            revisar(cfg, estado, primera=primera)
            guardar_json(ESTADO, estado)
            primera = False
        except Exception as e:
            log(f"Error en la revisión: {e}")
        time.sleep(max(60, int(cfg.get("cada_cuantos_segundos", 120))))


if __name__ == "__main__":
    main()
