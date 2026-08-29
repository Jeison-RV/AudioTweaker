# 🎧 AudioTweaker

Optimizador de audio para gaming en Windows. Aplica curvas de corrección AutoEQ por auricular, supresión de disparos con compresión VST y boost de pasos — todo con un solo click.

> Desarrollado por **Jeison Ramirez Vallejo** · TikTok [@piranha_gg](https://tiktok.com/@piranha_gg)  
> ☕ [Apoyar con donación](https://paypal.me/Piranha97)

---

## ¿Qué hace?

- **AutoEQ integrado** — curvas de corrección medidas para tu auricular. Si no está en la lista, búscalo entre miles de modelos directamente desde la app.
- **Supresión de disparos** — compresión broadband (ReaComp) y multiband (ReaXcomp) para bajar el volumen de disparos sin perder los pasos del enemigo.
- **3 perfiles de combate:**
  - 🔇 **Agresivo** — disparos casi silenciados, pasos al máximo
  - 🔉 **Moderado** — balance entre sonido natural y ventaja táctica
  - 🔊 **Sin supresión** — EQ solamente, sonido más natural
- **Configuración automática de Equalizer APO** — detecta tu dispositivo y lo registra sin tocar nada a mano.

---

## Requisitos

| Dependencia | Notas |
|---|---|
| [Equalizer APO](https://sourceforge.net/projects/equalizerapo/) | Instalar con el instalador oficial (64-bit) |
| [ReaPlugs VST 2.36 64-bit](https://www.reaper.fm/reaplugs/) | Instalar en `C:\Program Files\VSTPlugins\ReaPlugs\` |
| Windows 10 / 11 | |

> La app verifica las dependencias al abrir y ofrece instalar ReaPlugs automáticamente.

---

## Instalación

### Opción A — Ejecutable (recomendado)

1. Descarga `AudioTweaker.exe` de [Releases](../../releases)
2. Ejecuta **como Administrador** (necesario para escribir configuración de APO)
3. La app guía la instalación de dependencias si faltan

### Opción B — Desde código fuente

```bash
pip install customtkinter sounddevice
python app.py
```

---

## Uso

1. **Selecciona tu auricular** en el dropdown  
   → Si no aparece tu modelo, click en *"🔍 Buscar otro auricular en AutoEQ"*
2. **Selecciona el juego** (Warzone)
3. **Selecciona el perfil de combate**
4. Click **⚡ Aplicar Perfil**

### Primera vez — configurar APO

En la sección **Tweaks**, click en **"🔧 Configurar APO para auricular seleccionado"**.  
La app escribe el registro y reinicia el servicio de audio automáticamente (~3 seg). No requiere reiniciar el PC.

---

## Auriculares compatibles con AutoEQ (lista base)

- Logitech G435 Wireless
- HyperX Cloud II
- Sony WH-1000XM4
- SteelSeries Arctis 7
- Razer BlackShark V2
- **+ miles más** vía búsqueda integrada

---

## Empaquetar en .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name AudioTweaker app.py
```

El ejecutable queda en `dist/AudioTweaker.exe`.

---

## Créditos

- [AutoEQ](https://github.com/jaakkopasanen/AutoEq) — base de datos de curvas de corrección
- [ReaPlugs](https://www.reaper.fm/reaplugs/) — VST de compresión (Cockos)
- [Equalizer APO](https://sourceforge.net/projects/equalizerapo/) — motor de procesamiento de audio
