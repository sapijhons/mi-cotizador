"""Mi Cotizador: convierte pesos a dólares y guarda un historial.

Para usar el conversor hay que iniciar sesión con un usuario de PocketBase.
"""

import json
import os
import re
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

NOMBRE_APP = "Mi Cotizador"
# Fuera del .app para que el historial sobreviva a actualizaciones y sea fácil de encontrar.
CARPETA_HISTORIAL = Path.home() / "Documents" / NOMBRE_APP
ARCHIVO_HISTORIAL = CARPETA_HISTORIAL / "historial.txt"

POCKETBASE_URL = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090").rstrip("/")
LARGO_MINIMO_PASSWORD = 8  # El mínimo que exige la colección "users" de PocketBase.

MENSAJES_VALIDACION = {
    "validation_not_unique": "Ese email ya está registrado.",
    "validation_is_email": "El email no es válido.",
    "validation_invalid_email": "El email no es válido.",
    "validation_min_text_constraint": (
        f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres."
    ),
    "validation_values_mismatch": "Las contraseñas no coinciden.",
    "validation_required": "Completá todos los campos.",
}


# --- PocketBase ---------------------------------------------------------------


class ErrorPocketBase(Exception):
    pass


def _pedir(ruta, datos, url_base=None):
    url = (url_base or POCKETBASE_URL) + ruta
    pedido = urllib.request.Request(
        url,
        data=json.dumps(datos).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=10) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            cuerpo = json.loads(e.read().decode("utf-8"))
        except ValueError:
            cuerpo = {}
        raise ErrorPocketBase(_traducir_error(cuerpo)) from e
    except (urllib.error.URLError, OSError) as e:
        raise ErrorPocketBase(
            f"No se pudo conectar con el servidor ({url_base or POCKETBASE_URL}).\n"
            "¿Está PocketBase encendido?"
        ) from e


def _traducir_error(cuerpo):
    for campo in (cuerpo.get("data") or {}).values():
        codigo = campo.get("code") if isinstance(campo, dict) else None
        if codigo in MENSAJES_VALIDACION:
            return MENSAJES_VALIDACION[codigo]
    return cuerpo.get("message") or "Ocurrió un error inesperado."


def iniciar_sesion(email, password, url_base=None):
    """Devuelve el registro del usuario si el email y la contraseña son correctos."""
    try:
        respuesta = _pedir(
            "/api/collections/users/auth-with-password",
            {"identity": email, "password": password},
            url_base,
        )
    except ErrorPocketBase as e:
        if str(e) == "Failed to authenticate.":
            raise ErrorPocketBase("Email o contraseña incorrectos.") from e
        raise
    return respuesta["record"]


def registrar(email, password, confirmacion, url_base=None):
    if not email or not password or not confirmacion:
        raise ErrorPocketBase(MENSAJES_VALIDACION["validation_required"])
    if password != confirmacion:
        raise ErrorPocketBase(MENSAJES_VALIDACION["validation_values_mismatch"])
    if len(password) < LARGO_MINIMO_PASSWORD:
        raise ErrorPocketBase(MENSAJES_VALIDACION["validation_min_text_constraint"])
    return _pedir(
        "/api/collections/users/records",
        {"email": email, "password": password, "passwordConfirm": confirmacion},
        url_base,
    )


# --- Conversión e historial ---------------------------------------------------


def parsear_numero(texto):
    """Convierte '1.234,56', '1234,56', '150.000' o '1234.56' en float."""
    limpio = texto.strip().replace(" ", "").replace("$", "")
    if not limpio:
        raise ValueError("vacío")
    if "," in limpio and "." in limpio:
        # Formato argentino: punto de miles, coma decimal.
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
        # '150.000' o '1.500' son miles, no decimales.
        limpio = limpio.replace(".", "")
    return float(limpio)


def convertir(pesos, cotizacion):
    if pesos < 0:
        raise ValueError("El monto no puede ser negativo.")
    if cotizacion <= 0:
        raise ValueError("La cotización debe ser mayor a cero.")
    return pesos / cotizacion


def formatear(valor):
    """1234.5 -> '1.234,50'."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def guardar_en_historial(
    pesos, cotizacion, dolares, usuario=None, archivo=None, ahora=None
):
    archivo = archivo or ARCHIVO_HISTORIAL
    ahora = ahora or datetime.now()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    linea = (
        f"{ahora:%Y-%m-%d %H:%M:%S} | ARS {formatear(pesos)} | "
        f"cotización {formatear(cotizacion)} | USD {formatear(dolares)}"
    )
    if usuario:
        linea += f" | {usuario}"
    linea += "\n"
    with open(archivo, "a", encoding="utf-8") as f:
        f.write(linea)
    return linea


# --- Interfaz -----------------------------------------------------------------


def _titulo(marco, texto):
    ttk.Label(marco, text=texto, font=("Helvetica", 18, "bold")).grid(
        column=0, row=0, columnspan=2, pady=(0, 15)
    )


def _campo(marco, fila, etiqueta, oculto=False):
    ttk.Label(marco, text=etiqueta).grid(column=0, row=fila, sticky="w", pady=4)
    entrada = ttk.Entry(marco, width=24, show="•" if oculto else "")
    entrada.grid(column=1, row=fila, pady=4)
    return entrada


def _enlace(marco, fila, texto, accion):
    enlace = ttk.Label(marco, text=texto, foreground="#2563eb", cursor="hand2")
    enlace.grid(column=0, row=fila, columnspan=2, pady=(8, 0))
    enlace.bind("<Button-1>", lambda _e: accion())


class PantallaLogin(ttk.Frame):
    def __init__(self, app):
        super().__init__(app, padding=20)
        self.app = app
        _titulo(self, "Iniciar sesión")
        self.email = _campo(self, 1, "Email:")
        self.password = _campo(self, 2, "Contraseña:", oculto=True)
        ttk.Button(self, text="Ingresar", command=self.accion_principal).grid(
            column=0, row=3, columnspan=2, pady=12
        )
        _enlace(self, 4, "¿No tenés cuenta? Registrate", lambda: app.mostrar(PantallaRegistro))
        self.email.focus()

    def accion_principal(self):
        email, password = self.email.get().strip(), self.password.get()
        if not email or not password:
            messagebox.showerror(NOMBRE_APP, MENSAJES_VALIDACION["validation_required"])
            return
        try:
            usuario = iniciar_sesion(email, password)
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.app.mostrar(PantallaConversor, usuario=usuario)


class PantallaRegistro(ttk.Frame):
    def __init__(self, app):
        super().__init__(app, padding=20)
        self.app = app
        _titulo(self, "Crear cuenta")
        self.email = _campo(self, 1, "Email:")
        self.password = _campo(self, 2, "Contraseña:", oculto=True)
        self.confirmacion = _campo(self, 3, "Repetir contraseña:", oculto=True)
        ttk.Label(
            self, text=f"Mínimo {LARGO_MINIMO_PASSWORD} caracteres.", foreground="gray"
        ).grid(column=1, row=4, sticky="w")
        ttk.Button(self, text="Registrarme", command=self.accion_principal).grid(
            column=0, row=5, columnspan=2, pady=12
        )
        _enlace(self, 6, "¿Ya tenés cuenta? Iniciá sesión", lambda: app.mostrar(PantallaLogin))
        self.email.focus()

    def accion_principal(self):
        email = self.email.get().strip()
        password = self.password.get()
        try:
            registrar(email, password, self.confirmacion.get())
            usuario = iniciar_sesion(email, password)
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.app.mostrar(PantallaConversor, usuario=usuario)


class PantallaConversor(ttk.Frame):
    def __init__(self, app, usuario):
        super().__init__(app, padding=20)
        self.app = app
        self.usuario = usuario
        _titulo(self, NOMBRE_APP)

        self.pesos = _campo(self, 1, "Monto en pesos (ARS):")
        self.cotizacion = _campo(self, 2, "Cotización del dólar:")

        ttk.Button(self, text="Convertir", command=self.accion_principal).grid(
            column=0, row=3, columnspan=2, pady=12
        )

        self.resultado = ttk.Label(self, text="", font=("Helvetica", 16))
        self.resultado.grid(column=0, row=4, columnspan=2)

        ttk.Label(
            self, text=f"Historial: {ARCHIVO_HISTORIAL}", foreground="gray", wraplength=340
        ).grid(column=0, row=5, columnspan=2, pady=(12, 0))

        ttk.Label(self, text=f"Sesión: {usuario['email']}", foreground="gray").grid(
            column=0, row=6, columnspan=2, pady=(12, 0)
        )
        _enlace(self, 7, "Cerrar sesión", lambda: app.mostrar(PantallaLogin))
        self.pesos.focus()

    def accion_principal(self):
        try:
            pesos = parsear_numero(self.pesos.get())
            cotizacion = parsear_numero(self.cotizacion.get())
        except ValueError:
            messagebox.showerror(NOMBRE_APP, "Ingresá números válidos en ambos campos.")
            return
        try:
            dolares = convertir(pesos, cotizacion)
        except ValueError as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return

        self.resultado.config(text=f"USD {formatear(dolares)}")
        try:
            guardar_en_historial(pesos, cotizacion, dolares, usuario=self.usuario["email"])
        except OSError as e:
            messagebox.showwarning(NOMBRE_APP, f"No se pudo guardar el historial:\n{e}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NOMBRE_APP)
        self.resizable(False, False)
        self.pantalla = None
        self.bind("<Return>", lambda _e: self.pantalla.accion_principal())
        self.mostrar(PantallaLogin)

    def mostrar(self, clase, **datos):
        if self.pantalla is not None:
            self.pantalla.destroy()
        self.pantalla = clase(self, **datos)
        self.pantalla.grid()


if __name__ == "__main__":
    App().mainloop()
