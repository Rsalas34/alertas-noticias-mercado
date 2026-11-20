# 🔔 Sistema de alertas de noticias del mercado — Robinson

Tiene dos partes:

| Parte | Qué hace | Cuándo |
|---|---|---|
| **Vigilante** (`vigilante.py`) | Revisa noticias cada 2 minutos (WSJ, MarketWatch, CNBC, Reserva Federal, Google Noticias y Yahoo Finanzas de tus tickers). Les pone puntaje y, si una puede mover el mercado o tus acciones, te manda una alerta a Telegram en español, con el precio de SPY y del ticker. | 24/7 mientras la PC esté prendida |
| **Resúmenes de Claude** | Claude analiza las noticias con tus conectores (Clear Street, precios, calendario) y te manda un resumen completo a Telegram. | Lun–vie 8:00 a. m. (antes de abrir) y 4:30 p. m. (cierre) |

---

## Paso 1 — Crear tu bot de Telegram (5 minutos)

1. En Telegram busca **@BotFather** (tiene la palomita azul) y escríbele `/newbot`.
2. Ponle un nombre (ej. `Alertas Robinson`) y un usuario que termine en `bot` (ej. `alertas_robinson_bot`).
3. BotFather te da un **token** parecido a `123456789:ABCdef...`. **No lo compartas con nadie.**
4. Abre `config.json` y pega el token donde dice `PEGA_AQUI_EL_TOKEN_DEL_BOT` (deja las comillas).
5. En Telegram abre tu bot nuevo y escríbele **hola**.
6. En la carpeta de este sistema corre:

```bash
python telegram.py configurar
```

Te debe llegar el mensaje "✅ Tu vigilante de noticias ya está conectado".

## Paso 2 — Encender el vigilante

- **Para probarlo** (ventana visible): doble clic en `iniciar_vigilante.bat`.
- **Para que arranque solo cada vez que prendas la PC** (oculto), en PowerShell:

```bash
powershell -ExecutionPolicy Bypass -File encender_al_prender_pc.ps1
```

La primera vez no te manda noticias viejas: solo lo nuevo desde ese momento.

## Cómo leer una alerta

```
🔴 ALERTA ALTA · FED / TASAS
📰 La Fed sube las tasas 0,25 puntos
🕒 14:00 NY · Reserva Federal
💡 Por qué: noticia de las que mueven todo el mercado
📈 SPY: 715.87 (-2.0 % hoy)
```

- 🔴 **ALTA**: Fed, inflación, empleo, aranceles, guerra, quiebras, renuncias de CEO… o una noticia muy fuerte de tus tickers. Revisa el gráfico.
- 🟠 **MEDIA**: noticia importante de tus tickers o del mercado. Tenla en cuenta.
- De noche (9 p. m. a 6 a. m.) solo llegan las 🔴.
- **Una noticia no es una entrada.** Mira si el precio la confirma antes de operar.

## Ajustes (en `config.json`)

| Ajuste | Para qué |
|---|---|
| `vigilados` | Tus tickers y las palabras que los identifican en inglés (ej. NVDA → "nvidia"). Agrega o borra los que quieras. |
| `umbral_alerta_alta` / `umbral_alerta_media` | Súbelos si te llegan demasiadas alertas; bájalos si te llegan muy pocas. |
| `max_alertas_por_hora` | Tope para que no te sature (12 por defecto). |
| `horario_noche` y `de_noche_solo_alertas_altas` | Silencio nocturno. |
| `cada_cuantos_segundos` | Cada cuánto revisa (mínimo 60). |

Los cambios se aplican solos en la siguiente revisión.

## Probar sin mandar nada

```bash
python vigilante.py --prueba
```

Muestra en pantalla lo que alertaría ahora mismo. Con `--todas` ves también las que no pasaron el filtro y su puntaje.

## Archivos

- `alertas.log`: historial de todo lo que revisó y envió.
- `estado.json`: memoria de noticias ya vistas (si lo borras, empieza de cero).
- `resumen.txt`: último resumen que hizo Claude.

## Apagarlo

- Si lo abriste con el `.bat`: cierra la ventana.
- Si lo dejaste automático:

```bash
powershell -Command "Stop-ScheduledTask VigilanteNoticias; Unregister-ScheduledTask VigilanteNoticias -Confirm:$false"
```

- Los resúmenes de Claude se pausan o se borran en la sección **Programado** de la barra lateral de la app.

> Es información y educación, no asesoría financiera. El sistema nunca ejecuta órdenes.
