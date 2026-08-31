import customtkinter as ctk
import sounddevice as sd
import winreg
import urllib.request
import urllib.parse
import os
import re
import subprocess
import threading
import webbrowser
import tempfile
import json

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APO_DIR = r"C:\Program Files\EqualizerAPO"
APO_CONFIG = r"C:\Program Files\EqualizerAPO\config\config.txt"
REAPLUGS_URL = "https://www.reaper.fm/reaplugs/reaplugs236_x64-install.exe"
APO_URL = "https://github.com/Jeison-RV/AudioTweaker/releases/download/v1.0.0/EqualizerAPO-x64-1.4.2.exe"
VOICEMEETER_URL = "https://vb-audio.com/Voicemeeter/"
VOICEMEETER_EXE = r"C:\Program Files (x86)\VB\Voicemeeter\voicemeeter.exe"
VBCABLE_URL = "https://vb-audio.com/Cable/"

# APO registry automation
_MMDEVICES_RENDER = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
_MMDEVICES_CAPTURE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
_NAME_PROP = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
_APO_PROP_KEY = "{d04e05a6-594b-4fb6-a80d-01af5eed7d1d}"
_APO_LFX_CLSID = "{EACD2258-FCAC-4FF4-B36D-419E924A6D79}"
_APO_GFX_CLSID = "{EC1CC9CE-FAED-4822-828A-82A81A6F018F}"

# Keywords to match friendly device name → registry display name
DEVICE_SEARCH_KEYWORDS = {
    "G435 Wireless Gaming Headset": ["G435", "Audífono", "Audifonos"],
    "HyperX Cloud II": ["HyperX", "Cloud"],
    "Sony WH-1000XM4": ["WH-1000XM4", "Sony"],
    "SteelSeries Arctis 7": ["Arctis"],
    "Razer BlackShark V2": ["BlackShark"],
    "AT Gaming": ["AT Gaming", "CABLE Input"],
}


def list_render_devices():
    """Return [(display_name, guid), ...] for all audio render endpoints."""
    result = []
    try:
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _MMDEVICES_RENDER,
                              0, winreg.KEY_READ)
    except OSError:
        return result
    i = 0
    while True:
        try:
            guid = winreg.EnumKey(base, i)
            i += 1
        except OSError:
            break
        try:
            props = winreg.OpenKey(base, guid + r"\Properties")
            name, _ = winreg.QueryValueEx(props, _NAME_PROP)
            props.Close()
            if name:
                result.append((str(name), guid))
        except OSError:
            pass
    base.Close()
    return result


def find_guid_for_device(friendly_name):
    """Find endpoint GUID for a friendly device name. Returns guid or None."""
    keywords = DEVICE_SEARCH_KEYWORDS.get(friendly_name, [friendly_name])
    devices = list_render_devices()
    for kw in keywords:
        for name, guid in devices:
            if kw.lower() in name.lower():
                return guid
    return None


def register_apo_device(guid):
    """Write Equalizer APO CLSIDs into FxProperties for endpoint guid."""
    path = _MMDEVICES_RENDER + "\\" + guid + "\\FxProperties"
    key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0,
                             winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, f"{_APO_PROP_KEY},1", 0, winreg.REG_SZ, _APO_LFX_CLSID)
    winreg.SetValueEx(key, f"{_APO_PROP_KEY},2", 0, winreg.REG_SZ, _APO_GFX_CLSID)
    key.Close()


def deregister_apo_device(guid):
    """Remove Equalizer APO CLSIDs from FxProperties for endpoint guid."""
    path = _MMDEVICES_RENDER + "\\" + guid + "\\FxProperties"
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE)
        for suffix in (",1", ",2"):
            try:
                winreg.DeleteValue(key, f"{_APO_PROP_KEY}{suffix}")
            except OSError:
                pass
        key.Close()
    except OSError:
        pass


def list_capture_devices():
    result = []
    try:
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _MMDEVICES_CAPTURE, 0, winreg.KEY_READ)
    except OSError:
        return result
    i = 0
    while True:
        try:
            guid = winreg.EnumKey(base, i); i += 1
        except OSError:
            break
        try:
            props = winreg.OpenKey(base, guid + r"\Properties")
            name, _ = winreg.QueryValueEx(props, _NAME_PROP)
            props.Close()
            if name:
                result.append((str(name), guid))
        except OSError:
            pass
    base.Close()
    return result


def vbcable_detected():
    keywords = ["CABLE", "AT Gaming", "AT Clean"]
    for name, _ in list_render_devices() + list_capture_devices():
        if any(k.lower() in name.lower() for k in keywords):
            return True
    return False


def rename_endpoint(guid, new_name, capture=False):
    base = _MMDEVICES_CAPTURE if capture else _MMDEVICES_RENDER
    path = base + "\\" + guid + "\\Properties"
    key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, _NAME_PROP, 0, winreg.REG_SZ, new_name)
    key.Close()


def configure_voicemeeter(headphone_name=""):
    """Auto-configure Voicemeeter: A1=headphones, Strip1=AT Clean→A1, VirtualInput→A1."""
    import ctypes as _ct
    dll = r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"
    if not os.path.exists(dll):
        return False, "Voicemeeter no instalado"
    vm = _ct.WinDLL(dll)
    ret = vm.VBVMR_Login()
    if ret not in (0, 1):
        return False, "No se pudo conectar a Voicemeeter (¿está abierto?)"
    import time; time.sleep(0.3)
    try:
        vtype = _ct.c_long(0)
        vm.VBVMR_GetVoicemeeterType(_ct.byref(vtype))
        # Standard=1 → virtual strip index 2; Banana=2 → 3; Potato=3 → 5
        vstrip = {1: 2, 2: 3, 3: 5}.get(vtype.value, 2)

        def sf(param, val):
            vm.VBVMR_SetParameterFloat(param.encode(), _ct.c_float(val))

        def ss(param, val):
            vm.VBVMR_SetParameterStringA(param.encode(), val.encode())

        # A1 output = physical headphone
        if not headphone_name:
            skip = {"AT Gaming", "AT Clean", "CABLE", "Voicemeeter", "VB-Audio"}
            for name, _ in list_render_devices():
                if not any(k.lower() in name.lower() for k in skip):
                    headphone_name = name
                    break
        if headphone_name:
            ss("Bus[0].device.wdm", headphone_name)

        # Strip 0 = AT Clean → A1
        ss("Strip[0].device.wdm", "AT Clean")
        sf("Strip[0].A1", 1.0)
        sf("Strip[0].B1", 0.0)

        # Virtual Input (Discord) → A1
        sf(f"Strip[{vstrip}].A1", 1.0)

        return True, "Voicemeeter configurado"
    except Exception as e:
        return False, str(e)
    finally:
        vm.VBVMR_Logout()


def voicemeeter_configured():
    """Check if Voicemeeter Strip[0] already has AT Clean assigned."""
    import ctypes as _ct
    dll = r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll"
    if not os.path.exists(dll):
        return False
    try:
        vm = _ct.WinDLL(dll)
        if vm.VBVMR_Login() not in (0, 1):
            return False
        buf = _ct.create_string_buffer(256)
        vm.VBVMR_GetParameterStringA(b"Strip[0].device.wdm", buf)
        vm.VBVMR_Logout()
        return "AT Clean" in buf.value.decode(errors="ignore") or \
               "CABLE" in buf.value.decode(errors="ignore")
    except Exception:
        return False


def setup_at_devices():
    """Rename VB-Cable endpoints to AT Gaming (render) and AT Clean (capture)."""
    for name, guid in list_render_devices():
        if any(k in name for k in ["CABLE Input", "AT Gaming"]):
            rename_endpoint(guid, "AT Gaming", capture=False)
            break
    for name, guid in list_capture_devices():
        if any(k in name for k in ["CABLE Output", "AT Clean"]):
            rename_endpoint(guid, "AT Clean", capture=True)
            break


def dep_status():
    apo_ok = os.path.exists(os.path.join(APO_DIR, "EqualizerAPO.dll"))
    reacomp_ok = os.path.exists(
        r"C:\Program Files\VSTPlugins\ReaPlugs\reacomp-standalone.dll")
    reaxcomp_ok = os.path.exists(
        r"C:\Program Files\VSTPlugins\ReaPlugs\reaxcomp-standalone.dll")
    vm_ok = os.path.exists(VOICEMEETER_EXE)
    return {
        "required": {
            "Equalizer APO": apo_ok,
            "ReaPlugs (ReaComp)": reacomp_ok,
            "ReaPlugs (ReaXcomp)": reaxcomp_ok,
        },
        "optional": {
            "Voicemeeter": vm_ok,
            "VB-Cable (AT Gaming/AT Clean)": vbcable_detected(),
        },
    }


def show_setup_window(on_done):
    setup = ctk.CTkToplevel()
    setup.title("AudioTweaker — Configuración inicial")
    setup.geometry("500x720")
    setup.resizable(False, False)
    setup.grab_set()

    ctk.CTkLabel(setup, text="🎧 AudioTweaker Setup",
                 font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 4))
    ctk.CTkLabel(setup, text="Sigue los pasos en orden. Solo se hace una vez.",
                 font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 12))

    scroll = ctk.CTkScrollableFrame(setup, height=520)
    scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    btn_continue = ctk.CTkButton(setup, text="✅ Continuar a AudioTweaker", state="disabled",
                                 font=ctk.CTkFont(size=14, weight="bold"), height=42,
                                 command=lambda: [setup.destroy(), on_done()])
    btn_continue.pack(pady=(0, 16), padx=16, fill="x")

    def make_step(parent, number, title, subtitle, color="#1e1e2e"):
        frame = ctk.CTkFrame(parent, fg_color=color, corner_radius=10)
        frame.pack(fill="x", pady=6, padx=4)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text=f"  {number}  ", font=ctk.CTkFont(size=13, weight="bold"),
                     fg_color="#2a2a4a", corner_radius=6, width=32).pack(side="left")
        ctk.CTkLabel(header, text=f"  {title}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        if subtitle:
            ctk.CTkLabel(frame, text=subtitle, font=ctk.CTkFont(size=11),
                         text_color="gray", wraplength=420).pack(padx=12, pady=(0, 6), anchor="w")
        return frame

    def add_btn(parent, text, color, cmd, pady=4):
        b = ctk.CTkButton(parent, text=text, fg_color=color, height=34, command=cmd)
        b.pack(fill="x", padx=12, pady=(0, pady))
        return b

    def refresh():
        deps = dep_status()
        req = deps["required"]
        opt = deps["optional"]
        all_req_ok = all(req.values())
        vm_ok = opt["Voicemeeter"]
        cable_ok = opt["VB-Cable (AT Gaming/AT Clean)"]
        at_renamed = any("AT Gaming" in n for n, _ in list_render_devices())
        all_done = all_req_ok and vm_ok and cable_ok and at_renamed

        for w in scroll.winfo_children():
            w.destroy()

        # ── PASO 1: Motor de audio ──────────────────────────────────────────
        apo_ok = req["Equalizer APO"]
        rea_ok = req["ReaPlugs (ReaComp)"] and req["ReaPlugs (ReaXcomp)"]
        p1_ok = apo_ok and rea_ok
        p1 = make_step(scroll, "1", "Motor de audio",
                       "Equalizer APO procesa el sonido. ReaPlugs comprime disparos.",
                       "#1a2a1a" if p1_ok else "#2a1a1a")
        ctk.CTkLabel(p1, text=f"{'✅' if apo_ok else '❌'} Equalizer APO",
                     font=ctk.CTkFont(size=12),
                     text_color="green" if apo_ok else "red").pack(anchor="w", padx=16)
        ctk.CTkLabel(p1, text=f"{'✅' if rea_ok else '❌'} ReaPlugs VST",
                     font=ctk.CTkFont(size=12),
                     text_color="green" if rea_ok else "red").pack(anchor="w", padx=16, pady=(0, 6))

        if not apo_ok:
            btn_apo = add_btn(p1, "⬇ Instalar Equalizer APO automáticamente", "#1a5c8a",
                              lambda: None)
            def install_apo():
                btn_apo.configure(state="disabled")
                def _run():
                    tmp = os.path.join(tempfile.gettempdir(), "EqualizerAPO_setup.exe")
                    try:
                        def _prog(c, b, t):
                            if t > 0:
                                setup.after(0, lambda p=min(100, c*b*100//t):
                                    btn_apo.configure(text=f"⬇ Descargando APO... {p}%"))
                        urllib.request.urlretrieve(APO_URL, tmp, reporthook=_prog)
                        setup.after(0, lambda: btn_apo.configure(text="🔧 Instalando... acepta el UAC"))
                        import ctypes as _c, time
                        _c.windll.shell32.ShellExecuteW(None, "runas", tmp, "/S", None, 1)
                        time.sleep(15)
                    except Exception as e:
                        setup.after(0, lambda err=str(e): btn_apo.configure(text=f"❌ {err}"))
                    setup.after(0, refresh)
                threading.Thread(target=_run, daemon=True).start()
            btn_apo.configure(command=install_apo)

        if not rea_ok:
            btn_rp = add_btn(p1, "⬇ Instalar ReaPlugs automáticamente", "#1a6b3a", lambda: None)
            def install_reaplugs():
                btn_rp.configure(state="disabled")
                def _run():
                    tmp = os.path.join(tempfile.gettempdir(), "reaplugs_install.exe")
                    try:
                        def _prog(c, b, t):
                            if t > 0:
                                setup.after(0, lambda p=min(100, c*b*100//t):
                                    btn_rp.configure(text=f"⬇ Descargando ReaPlugs... {p}%"))
                        urllib.request.urlretrieve(REAPLUGS_URL, tmp, reporthook=_prog)
                        setup.after(0, lambda: btn_rp.configure(text="🔧 Instalando..."))
                        import ctypes as _c, time
                        _c.windll.shell32.ShellExecuteW(None, "runas", tmp, None, None, 1)
                        time.sleep(10)
                    except Exception as e:
                        setup.after(0, lambda err=str(e): btn_rp.configure(text=f"❌ {err}"))
                    setup.after(0, refresh)
                threading.Thread(target=_run, daemon=True).start()
            btn_rp.configure(command=install_reaplugs)

        # ── PASO 2: Enrutamiento de audio ───────────────────────────────────
        p2_ok = vm_ok and cable_ok
        p2 = make_step(scroll, "2", "Enrutamiento de audio",
                       "VB-Cable crea el canal virtual AT Gaming. Voicemeeter mezcla el juego y Discord.",
                       "#1a2a1a" if p2_ok else "#222233")
        ctk.CTkLabel(p2, text=f"{'✅' if cable_ok else '⚪'} VB-Cable (AT Gaming / AT Clean)",
                     font=ctk.CTkFont(size=12),
                     text_color="green" if cable_ok else "gray").pack(anchor="w", padx=16)
        ctk.CTkLabel(p2, text=f"{'✅' if vm_ok else '⚪'} Voicemeeter",
                     font=ctk.CTkFont(size=12),
                     text_color="green" if vm_ok else "gray").pack(anchor="w", padx=16, pady=(0, 6))

        if not cable_ok:
            btn_cable = add_btn(p2, "🌐 Descargar VB-Cable (gratis)", "#3a5a8a", lambda: None)
            def open_cable():
                webbrowser.open(VBCABLE_URL)
                btn_cable.configure(text="🌐 Descargado — instala y presiona Verificar")
            btn_cable.configure(command=open_cable)

        if not vm_ok:
            btn_vm = add_btn(p2, "🌐 Descargar Voicemeeter (gratis)", "#5a3a8a", lambda: None)
            def open_vm():
                webbrowser.open(VOICEMEETER_URL)
                btn_vm.configure(text="🌐 Descargado — instala y presiona Verificar")
            btn_vm.configure(command=open_vm)

        if cable_ok and vm_ok:
            ctk.CTkLabel(p2, text="✅ Listo — continúa al paso 3",
                         font=ctk.CTkFont(size=11), text_color="green").pack(padx=12, pady=(0, 6))

        # ── PASO 3: Reiniciar PC ────────────────────────────────────────────
        need_reboot = (cable_ok or vm_ok) and not at_renamed
        p3_ok = at_renamed
        p3 = make_step(scroll, "3", "Reiniciar PC",
                       "Necesario después de instalar VB-Cable y Voicemeeter.",
                       "#1a2a1a" if p3_ok else "#2a2010")
        if p3_ok:
            ctk.CTkLabel(p3, text="✅ Reinicio ya realizado",
                         font=ctk.CTkFont(size=12), text_color="green").pack(padx=16, pady=(0, 6))
        elif not (cable_ok and vm_ok):
            ctk.CTkLabel(p3, text="⏳ Completa el paso 2 primero",
                         font=ctk.CTkFont(size=12), text_color="gray").pack(padx=16, pady=(0, 6))
        else:
            add_btn(p3, "🔄 Reiniciar PC ahora", "#7a4a10",
                    lambda: subprocess.run(["shutdown", "/r", "/t", "5"]))
            ctk.CTkLabel(p3, text="El PC reiniciará en 5 segundos al presionar el botón.",
                         font=ctk.CTkFont(size=11), text_color="orange").pack(padx=12, pady=(0, 8))

        # ── PASO 4: Configurar dispositivos ────────────────────────────────
        p4_ok = at_renamed
        p4 = make_step(scroll, "4", "Configurar dispositivos",
                       "Renombra VB-Cable a AT Gaming / AT Clean y configura APO.",
                       "#1a2a1a" if p4_ok else "#222233")
        if not (cable_ok and vm_ok):
            ctk.CTkLabel(p4, text="⏳ Completa los pasos anteriores primero",
                         font=ctk.CTkFont(size=12), text_color="gray").pack(padx=16, pady=(0, 6))
        elif not at_renamed:
            btn_ren = add_btn(p4, "🏷️ Renombrar AT Gaming / AT Clean", "#3a5a8a", lambda: None)
            def do_rename():
                try:
                    setup_at_devices()
                    btn_ren.configure(text="✅ Renombrado")
                except PermissionError:
                    btn_ren.configure(text="❌ Ejecuta como Administrador")
                setup.after(1500, refresh)
            btn_ren.configure(command=do_rename)
        else:
            ctk.CTkLabel(p4, text="✅ AT Gaming / AT Clean configurados",
                         font=ctk.CTkFont(size=12), text_color="green").pack(padx=16, pady=(0, 6))

        # ── Verificar / Continuar ───────────────────────────────────────────
        ctk.CTkButton(scroll, text="🔄 Verificar estado", command=refresh,
                      fg_color="#444", height=32).pack(fill="x", padx=4, pady=(8, 2))

        btn_continue.configure(state="normal" if all_req_ok else "disabled")

    refresh()


def launch_main():
    """Build and run the main AudioTweaker window."""


CONFIG_PATH = r"C:\Program Files\EqualizerAPO\config\config.txt"
AUTOEQ_BASE = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/"
CACHE_DIR = os.path.join(os.environ.get("APPDATA", "."),
                         "AudioTweaker", "autoeq_cache")

REACOMP_DLL = r"C:\Program Files\VSTPlugins\ReaPlugs\reacomp-standalone.dll"
REAXCOMP_DLL = r"C:\Program Files\VSTPlugins\ReaPlugs\reaxcomp-standalone.dll"

# ReaComp lines (text params, no chunk needed)


def _reacomp(thresh, ratio, attack, release, wet, hipass=0.01, lowpass=0.3):
    return (
        f'VSTPlugin: Library "{REACOMP_DLL}" '
        f'Hipass {hipass} Thresh {thresh} Ratio {ratio} '
        f'Attack {attack} Release {release} '
        f'Pre-comp 0 resvd 0 Lowpass {lowpass} SignIn 0 AudIn 0 '
        f'Dry 3.16228e-08 Wet {wet} AutoMkUp 0 PreviewF 0 '
        f'"RMS size" 0.005 Knee 0 AutoRel 0 ClsAttk 1 AntiAls 0'
    )


# ReaXcomp chunk captured from user session (Agresivo tuned in Warzone)
_REAXCOMP_CHUNK = "OAAAAAQAAAAAAAAAAMByQAAAAAAAAPA/y+VeHKc1kj8AAAAAAABZQAAAAAAAAAAAAQAAAJYAAAAFAAAAEQAAAAAAAAAAQK9AAAAAAAAA8D/L5V4cpzWSPwAAAAAAAFlAAAAAAAAAAAABAAAAlgAAAAUAAAARAAAAAAAAAACIs0AAAAAAAADwP7MkdX+Wetk/AAAAAAAAAEAAAAAAAAAAAA8AAAAyAAAABQAAABEAAAAAAAAAAHDXQAAAAAAAAPA/syR1f5Z62T8AAAAAAAAAQAAAAAAAAAAADwAAADIAAAAFAAAAEQAAAAEAAAABAAAAAAAAAAAA8D8AAAAA"
_REAXCOMP_LINE = f'VSTPlugin: Library "{REAXCOMP_DLL}" ChunkData "{_REAXCOMP_CHUNK}"'

# Suppression levels: (footstep_boost_filters, reacomp_line_or_None, reaxcomp_line_or_None)
SUPPRESSION_LEVELS = {
    "Agresivo": (
        [
            "ON PK Fc 500 Hz Gain +2.0 dB Q 1.0",
            "ON PK Fc 1500 Hz Gain +6.0 dB Q 1.2",
            "ON PK Fc 3000 Hz Gain +5.0 dB Q 1.0",
            "ON PK Fc 4000 Hz Gain +3.0 dB Q 1.0",
        ],
        # Thresh -30dB=0.0316, Ratio~20:1=0.4949, Attack 2ms, Release 16ms, Wet=2.51
        _reacomp(0.0316228, 0.494949, 0.002, 0.016, 2.51189),
        _REAXCOMP_LINE,
    ),
    "Moderado": (
        [
            "ON PK Fc 500 Hz Gain +7.0 dB Q 1.0",
            "ON PK Fc 700 Hz Gain +7.0 dB Q 1.0",
            "ON PK Fc 1500 Hz Gain +12.0 dB Q 1.2",
            "ON PK Fc 3000 Hz Gain +11.0 dB Q 1.0",
            "ON PK Fc 4000 Hz Gain +8.0 dB Q 1.0",
        ],
        _reacomp(0.1, 0.114, 0.003, 0.05, 1.99526),
        None,
    ),
    "Sin supresión": (
        [
            "ON PK Fc 500 Hz Gain +8.0 dB Q 1.0",
            "ON PK Fc 700 Hz Gain +8.0 dB Q 1.0",
            "ON PK Fc 1500 Hz Gain +13.0 dB Q 1.2",
            "ON PK Fc 3000 Hz Gain +12.0 dB Q 1.0",
            "ON PK Fc 4000 Hz Gain +9.0 dB Q 1.0",
        ],
        None,
        None,
    ),
}

AUTOEQ_PATHS = {
    "G435 Wireless Gaming Headset": (
        "Rtings/HMS II.3 over-ear/Logitech G435 LIGHTSPEED/"
        "Logitech G435 LIGHTSPEED ParametricEQ.txt"
    ),
    "HyperX Cloud II": (
        "Rtings/HMS II.3 over-ear/HyperX Cloud II/"
        "HyperX Cloud II ParametricEQ.txt"
    ),
    "Sony WH-1000XM4": (
        "Rtings/HMS II.3 over-ear/Sony WH-1000XM4/"
        "Sony WH-1000XM4 ParametricEQ.txt"
    ),
    "SteelSeries Arctis 7": (
        "Rtings/HMS II.3 over-ear/SteelSeries Arctis 7/"
        "SteelSeries Arctis 7 ParametricEQ.txt"
    ),
    "Razer BlackShark V2": (
        "Rtings/HMS II.3 over-ear/Razer BlackShark V2/"
        "Razer BlackShark V2 ParametricEQ.txt"
    ),
}

GAME_DELTAS = {
    "Warzone": {
        "preamp": 0,
        "filters": [
            "ON PK Fc 80 Hz Gain -3.0 dB Q 1.0",
            "ON PK Fc 10000 Hz Gain +1.5 dB Q 1.0",
        ],
    },
}


AUTOEQ_INDEX_CACHE = os.path.join(CACHE_DIR, "_autoeq_index.json")
AUTOEQ_TREE_URL = (
    "https://api.github.com/repos/jaakkopasanen/AutoEq/git/trees/master?recursive=1"
)
autoeq_override_path = None  # set by search dialog


def load_autoeq_index():
    if os.path.exists(AUTOEQ_INDEX_CACHE):
        with open(AUTOEQ_INDEX_CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def fetch_autoeq_index():
    req = urllib.request.Request(
        AUTOEQ_TREE_URL,
        headers={"Accept": "application/vnd.github.v3+json",
                 "User-Agent": "AudioTweaker/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    index = {}
    for item in data.get("tree", []):
        path = item.get("path", "")
        if path.endswith(" ParametricEQ.txt"):
            name = os.path.basename(path).replace(" ParametricEQ.txt", "")
            index[name] = path
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(AUTOEQ_INDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(index, f)
    return index


def fetch_autoeq(device_name):
    global autoeq_override_path
    path = autoeq_override_path or AUTOEQ_PATHS.get(device_name)
    if not path:
        return None
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", path)
    cache_file = os.path.join(CACHE_DIR, safe_name)
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()
    try:
        url = AUTOEQ_BASE + urllib.parse.quote(path)
        with urllib.request.urlopen(url, timeout=8) as r:
            text = r.read().decode("utf-8")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(text)
        return text
    except Exception:
        return None


def parse_eq_text(text):
    preamp = 0.0
    filters = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"Preamp:\s*([-+]?\d+\.?\d*)\s*dB", line)
        if m:
            preamp = float(m.group(1))
            continue
        m2 = re.match(r"Filter\s+\d+:\s+(ON .+)", line)
        if m2:
            filters.append(m2.group(1))
    return preamp, filters


def build_config(device_name, game, suppression):
    delta = GAME_DELTAS.get(game, {"preamp": 0, "filters": []})
    autoeq_text = fetch_autoeq(device_name)

    if autoeq_text:
        _, base_filters = parse_eq_text(autoeq_text)
        source = "AutoEQ+"
    else:
        base_filters = []
        source = "genérico"

    boost_filters, reacomp_line, reaxcomp_line = SUPPRESSION_LEVELS[suppression]
    all_filters = base_filters + delta["filters"] + boost_filters

    lines = [f"# AudioTweaker: {device_name} + {game} + {suppression} ({source})"]
    at_guid = find_guid_for_device("AT Gaming")
    if at_guid:
        at_name = "AT Gaming"
        for name, g in list_render_devices():
            if g == at_guid:
                at_name = name
                break
        lines.append(f"Device: {at_name} {at_guid}")
    lines.append("Preamp: 0.0 dB")
    for i, f in enumerate(all_filters, 1):
        lines.append(f"Filter {i}: {f}")

    if reacomp_line and os.path.exists(REACOMP_DLL):
        lines.append(reacomp_line)
    if reaxcomp_line and os.path.exists(REAXCOMP_DLL):
        lines.append(reaxcomp_line)

    return "\n".join(lines) + "\n", source


def get_dispositivos():
    devices = sd.query_devices()
    vistos = set()
    outputs = []
    nombres_amigables = [
        ("Audífono", "G435 Wireless Gaming Headset"),
        ("G435", "G435 Wireless Gaming Headset"),
        ("LS27DG30X", "Monitor LS27DG30X"),
        ("HyperX", "HyperX Cloud II"),
        ("WH-1000XM4", "Sony WH-1000XM4"),
        ("Arctis", "SteelSeries Arctis 7"),
        ("BlackShark", "Razer BlackShark V2"),
        ("AT Gaming", "AT Gaming"),
        ("CABLE Input", "AT Gaming"),
    ]
    for d in devices:
        if d["max_output_channels"] > 0:
            nombre = d["name"].strip()
            ignorar = ["Microsoft", "Output (", "Speakers ()", "Output ()",
                       "Controlador primario", "Asignador"]
            if any(x in nombre for x in ignorar):
                continue
            clave = nombre[:20].strip()
            if clave not in vistos:
                vistos.add(clave)
                nombre_final = nombre
                for fragmento, amigable in nombres_amigables:
                    if fragmento.lower() in nombre.lower():
                        nombre_final = amigable
                        break
                outputs.append(nombre_final)
    return outputs if outputs else ["No se encontraron dispositivos"]


def show_autoeq_search():
    global autoeq_override_path
    dlg = ctk.CTkToplevel(app)
    dlg.title("Buscar auricular en AutoEQ")
    dlg.geometry("500x520")
    dlg.resizable(False, False)
    dlg.grab_set()

    ctk.CTkLabel(dlg, text="🔍 Buscar curva AutoEQ",
                 font=ctk.CTkFont(size=16, weight="bold")).pack(pady=12)

    search_frame = ctk.CTkFrame(dlg, fg_color="transparent")
    search_frame.pack(padx=15, fill="x")
    search_var = ctk.StringVar()
    search_entry = ctk.CTkEntry(search_frame, textvariable=search_var,
                                placeholder_text="Ej: HyperX Cloud Alpha...", width=460)
    search_entry.pack(pady=5)

    status_dlg = ctk.CTkLabel(dlg, text="", font=ctk.CTkFont(size=12), text_color="gray")
    status_dlg.pack()

    results_frame = ctk.CTkScrollableFrame(dlg, height=310)
    results_frame.pack(padx=15, pady=5, fill="both", expand=True)

    _index = [{}]

    def do_search(*_):
        query = search_var.get().strip().lower()
        for w in results_frame.winfo_children():
            w.destroy()
        if len(query) < 2:
            return
        matches = sorted(
            [(n, p) for n, p in _index[0].items() if query in n.lower()],
            key=lambda x: x[0]
        )[:60]
        if not matches:
            ctk.CTkLabel(results_frame, text="Sin resultados").pack()
            return
        for name, path in matches:
            def make_cmd(n=name, p=path):
                def cmd():
                    global autoeq_override_path
                    autoeq_override_path = p
                    autoeq_label.configure(text=f"AutoEQ: {n}", text_color="#4CAF50")
                    dlg.destroy()
                return cmd
            ctk.CTkButton(results_frame, text=name, anchor="w",
                          fg_color="transparent", hover_color="#2a2a2a",
                          command=make_cmd()).pack(fill="x", pady=1, padx=5)

    search_var.trace_add("write", do_search)

    def load_index():
        status_dlg.configure(text="⬇ Descargando índice de AutoEQ (~1.5MB)...")
        def _run():
            try:
                idx = fetch_autoeq_index()
                _index[0] = idx
                status_dlg.configure(text=f"✅ {len(idx)} auriculares. Escribe para buscar.")
                do_search()
            except Exception as e:
                status_dlg.configure(text=f"❌ {e}", text_color="red")
        threading.Thread(target=_run, daemon=True).start()

    cached = load_autoeq_index()
    if cached:
        _index[0] = cached
        status_dlg.configure(text=f"✅ {len(cached)} auriculares. Escribe para buscar.")
    else:
        load_index()

    search_entry.focus()


def aplicar_perfil():
    status_label.configure(text="⏳ Aplicando...", text_color="gray")
    app.update_idletasks()

    def _run():
        try:
            juego = perfil_var.get()
            device = dispositivo_var.get()
            suppression = supresion_var.get()
            config, source = build_config(device, juego, suppression)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(config)
            app.after(0, lambda: status_label.configure(
                text=f"✅ {juego} · {suppression} ({source})", text_color="green"))
        except FileNotFoundError:
            app.after(0, lambda: status_label.configure(
                text="⚠️ Equalizer APO no encontrado. ¿Está instalado?", text_color="orange"))
        except PermissionError:
            app.after(0, lambda: status_label.configure(
                text="❌ Ejecuta la app como Administrador", text_color="red"))
        except Exception as e:
            app.after(0, lambda err=e: status_label.configure(
                text=f"❌ Error: {err}", text_color="red"))

    threading.Thread(target=_run, daemon=True).start()


def restaurar_defaults():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("# Restaurado por AudioTweaker\nPreamp: 0 dB\n")
        status_label.configure(
            text="✅ Audio restaurado a valores por defecto", text_color="green")
    except Exception as e:
        status_label.configure(text=f"❌ Error: {str(e)}", text_color="red")


def deshabilitar_enhancements():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render",
            0, winreg.KEY_READ
        )
        key.Close()
        status_label.configure(
            text="✅ Audio Enhancements deshabilitados", text_color="green")
    except Exception as e:
        status_label.configure(text=f"❌ Error: {str(e)}", text_color="red")


def quitar_apo_dispositivo():
    device = dispositivo_var.get()
    guid = find_guid_for_device(device)
    if not guid:
        status_label.configure(text=f"❌ No se encontró '{device}' en el registro", text_color="red")
        return
    try:
        deregister_apo_device(guid)
    except PermissionError:
        status_label.configure(text="❌ Ejecuta la app como Administrador", text_color="red")
        return
    except Exception as e:
        status_label.configure(text=f"❌ Error: {e}", text_color="red")
        return
    status_label.configure(text=f"✅ APO quitado de '{device}'. Reinicia el servicio de audio.", text_color="orange")

    def _restart():
        try:
            subprocess.run(["powershell", "-Command",
                            "Stop-Service audiosrv -Force; Start-Service audiosrv"],
                           capture_output=True, timeout=15)
            app.after(0, lambda: status_label.configure(
                text=f"✅ APO quitado de '{device}'. Listo.", text_color="green"))
        except Exception:
            pass
    threading.Thread(target=_restart, daemon=True).start()


def configurar_apo_dispositivo():
    device = dispositivo_var.get()
    guid = find_guid_for_device(device)
    if not guid:
        # Fallback: show all registry devices for manual selection
        devices = list_render_devices()
        if not devices:
            status_label.configure(
                text="❌ No se encontraron dispositivos en el registro", text_color="red")
            return
        # Show picker dialog
        _show_device_picker(devices, device)
        return
    try:
        register_apo_device(guid)
    except PermissionError:
        status_label.configure(
            text="❌ Ejecuta la app como Administrador para configurar APO", text_color="red")
        return
    except Exception as e:
        status_label.configure(text=f"❌ Error: {str(e)}", text_color="red")
        return

    status_label.configure(text="🔄 Reiniciando servicio de audio...", text_color="gray")

    def _restart_audio():
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Stop-Service audiosrv -Force; "
                 "Stop-Service AudioEndpointBuilder -Force; "
                 "Start-Service AudioEndpointBuilder; "
                 "Start-Service audiosrv"],
                capture_output=True, timeout=15
            )
            status_label.configure(
                text=f"✅ APO activo para '{device}'. Listo.", text_color="green")
        except Exception as e:
            status_label.configure(
                text=f"✅ Registro OK. Reinicia el PC para aplicar. ({e})",
                text_color="orange")

    threading.Thread(target=_restart_audio, daemon=True).start()


def _show_device_picker(devices, hint):
    """Fallback dialog when auto-detection fails — let user pick from registry list."""
    dlg = ctk.CTkToplevel(app)
    dlg.title("Seleccionar dispositivo")
    dlg.geometry("460x320")
    dlg.grab_set()
    ctk.CTkLabel(dlg, text=f"No se encontró '{hint}' automáticamente.\nElige tu auricular de la lista:",
                 wraplength=420, justify="left").pack(pady=15, padx=15)
    names = [n for n, _ in devices]
    picker_var = ctk.StringVar(value=names[0])
    ctk.CTkOptionMenu(dlg, values=names, variable=picker_var, width=400).pack(padx=15)

    def _apply():
        chosen = picker_var.get()
        guid = next((g for n, g in devices if n == chosen), None)
        if not guid:
            return
        try:
            register_apo_device(guid)
            dlg.destroy()
        except PermissionError:
            status_label.configure(
                text="❌ Ejecuta como Administrador", text_color="red")
            dlg.destroy()
            return
        except Exception as e:
            status_label.configure(text=f"❌ {e}", text_color="red")
            dlg.destroy()
            return

        status_label.configure(text="🔄 Reiniciando servicio de audio...", text_color="gray")

        def _restart():
            try:
                subprocess.run(
                    ["powershell", "-Command",
                     "Stop-Service audiosrv -Force; "
                     "Stop-Service AudioEndpointBuilder -Force; "
                     "Start-Service AudioEndpointBuilder; "
                     "Start-Service audiosrv"],
                    capture_output=True, timeout=15
                )
                status_label.configure(
                    text=f"✅ APO activo para '{chosen}'. Listo.", text_color="green")
            except Exception as e2:
                status_label.configure(
                    text=f"✅ Registro OK. Reinicia el PC para aplicar. ({e2})",
                    text_color="orange")

        threading.Thread(target=_restart, daemon=True).start()

    ctk.CTkButton(dlg, text="Configurar este dispositivo", command=_apply,
                  height=40).pack(pady=15, padx=15, fill="x")


# --- GUI ---
app = ctk.CTk()
app.title("AudioTweaker")
app.geometry("500x910")
app.resizable(False, False)

def _resource(name):
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

try:
    app.iconbitmap(_resource("icon.ico"))
except Exception:
    pass


def _show_main():
    pass  # app ya visible


titulo = ctk.CTkLabel(app, text="🎧 AudioTweaker",
                      font=ctk.CTkFont(size=28, weight="bold"))
titulo.pack(pady=(12, 2))

subtitulo = ctk.CTkLabel(app, text="Optimiza tu audio para gaming",
                         font=ctk.CTkFont(size=14), text_color="gray")
subtitulo.pack()

autoeq_badge = ctk.CTkLabel(app, text="⚡ AutoEQ integrado",
                            font=ctk.CTkFont(size=11), text_color="#4CAF50")
autoeq_badge.pack(pady=(2, 0))

# Auricular
frame_dispositivo = ctk.CTkFrame(app)
frame_dispositivo.pack(pady=6, padx=20, fill="x")
ctk.CTkLabel(frame_dispositivo, text="Auricular:",
             font=ctk.CTkFont(weight="bold")).pack(pady=(6, 3))
dispositivos = get_dispositivos()
dispositivo_var = ctk.StringVar(value=dispositivos[0])
ctk.CTkOptionMenu(frame_dispositivo, values=dispositivos,
                  variable=dispositivo_var, width=300).pack(pady=(0, 3))

autoeq_label = ctk.CTkLabel(frame_dispositivo, text="AutoEQ: según selección",
                             font=ctk.CTkFont(size=11), text_color="gray")
autoeq_label.pack()

ctk.CTkButton(frame_dispositivo, text="🔍 Buscar otro auricular en AutoEQ",
              command=show_autoeq_search, fg_color="transparent",
              border_width=1, border_color="#444",
              font=ctk.CTkFont(size=12), height=28
              ).pack(pady=(2, 4), padx=20, fill="x")

# Juego + Supresión en mismo frame
frame_perfil = ctk.CTkFrame(app)
frame_perfil.pack(pady=4, padx=20, fill="x")

ctk.CTkLabel(frame_perfil, text="Juego:",
             font=ctk.CTkFont(weight="bold")).pack(pady=(6, 2))
perfil_var = ctk.StringVar(value="Warzone")
ctk.CTkOptionMenu(frame_perfil, values=list(GAME_DELTAS.keys()),
                  variable=perfil_var, width=300).pack(pady=(0, 4))

ctk.CTkLabel(frame_perfil, text="Perfil de combate:",
             font=ctk.CTkFont(weight="bold")).pack(pady=(4, 4))
supresion_var = ctk.StringVar(value="Agresivo")

DESCRIPCIONES = {
    "Agresivo": "🔇 Disparos casi silenciados\n👟 Pasos al máximo\nIdeal para escuchar enemigos a cualquier distancia.",
    "Moderado": "🔉 Disparos reducidos\n👟 Pasos amplificados\nBalance entre sonido natural y ventaja táctica.",
    "Sin supresión": "🔊 Disparos normales\n👟 Pasos boosteados por EQ\nSonido más natural, pasos más claros que stock.",
}

desc_label = ctk.CTkLabel(
    frame_perfil,
    text=DESCRIPCIONES["Agresivo"],
    font=ctk.CTkFont(size=12),
    text_color="gray",
    justify="left",
    wraplength=340,
)


def on_supresion_change(*_):
    desc_label.configure(text=DESCRIPCIONES.get(supresion_var.get(), ""))


supresion_var.trace_add("write", on_supresion_change)

ctk.CTkOptionMenu(frame_perfil, values=list(SUPPRESSION_LEVELS.keys()),
                  variable=supresion_var, width=300).pack(pady=(0, 4))
desc_label.pack(pady=(0, 6), padx=10, anchor="w")

# Botón principal
ctk.CTkButton(
    app,
    text="⚡ Aplicar Perfil",
    font=ctk.CTkFont(size=16, weight="bold"),
    height=50,
    command=aplicar_perfil,
).pack(pady=8, padx=20, fill="x")

status_label = ctk.CTkLabel(app, text="", font=ctk.CTkFont(size=13),
                            wraplength=460)
status_label.pack(pady=(0, 4))

# Tweaks
frame_tweaks = ctk.CTkFrame(app)
frame_tweaks.pack(pady=6, padx=20, fill="x")
ctk.CTkLabel(frame_tweaks, text="Tweaks de Windows:",
             font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
ctk.CTkButton(frame_tweaks, text="📦 Verificar e instalar dependencias",
              command=lambda: show_setup_window(lambda: None),
              fg_color="#444").pack(pady=5, padx=10, fill="x")
ctk.CTkButton(frame_tweaks, text="🔧 Configurar APO para auricular seleccionado",
              command=configurar_apo_dispositivo, fg_color="#1a5c8a"
              ).pack(pady=5, padx=10, fill="x")
ctk.CTkButton(frame_tweaks, text="🗑️ Quitar APO del auricular seleccionado",
              command=quitar_apo_dispositivo, fg_color="#6b2a2a"
              ).pack(pady=5, padx=10, fill="x")
ctk.CTkButton(frame_tweaks, text="Deshabilitar Audio Enhancements",
              command=deshabilitar_enhancements, fg_color="gray"
              ).pack(pady=5, padx=10, fill="x")
ctk.CTkButton(frame_tweaks, text="Restaurar Defaults",
              command=restaurar_defaults, fg_color="gray"
              ).pack(pady=(5, 10), padx=10, fill="x")

# Footer
frame_footer = ctk.CTkFrame(app, fg_color="transparent")
frame_footer.pack(pady=(0, 12), padx=20, fill="x")

ctk.CTkLabel(frame_footer, text="Desarrollado por Jeison Ramirez",
             font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack()

ctk.CTkLabel(frame_footer, text="TikTok: @piranha_gg",
             font=ctk.CTkFont(size=11), text_color="#4CAF50").pack()


def abrir_donacion():
    import webbrowser
    webbrowser.open("https://paypal.me/Piranha97")


ctk.CTkButton(
    frame_footer,
    text="☕ Apoyar con donación",
    font=ctk.CTkFont(size=11),
    height=28,
    fg_color="#0070BA",
    hover_color="#005ea6",
    command=abrir_donacion,
).pack(pady=(6, 0))

# Arranque: checker si faltan deps, directo si todo OK
if all(dep_status()["required"].values()):
    _show_main()
else:
    app.after(100, lambda: show_setup_window(_show_main))

app.mainloop()
