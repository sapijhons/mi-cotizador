"""Mi Cotizador: convierte pesos a dólares y guarda un historial.

Para usar el conversor hay que iniciar sesión con un usuario de PocketBase.
"""

import json
import os
import re
import secrets
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


def _pedir(ruta, datos=None, url_base=None, metodo="POST", token=None):
    url = (url_base or POCKETBASE_URL) + ruta
    encabezados = {"Content-Type": "application/json"}
    if token:
        encabezados["Authorization"] = token
    pedido = urllib.request.Request(
        url,
        data=json.dumps(datos).encode("utf-8") if datos is not None else None,
        headers=encabezados,
        method=metodo,
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
    """Devuelve {'token', 'record'} si el email y la contraseña son correctos."""
    try:
        return _pedir(
            "/api/collections/users/auth-with-password",
            {"identity": email, "password": password},
            url_base,
        )
    except ErrorPocketBase as e:
        if str(e) == "Failed to authenticate.":
            raise ErrorPocketBase("Email o contraseña incorrectos.") from e
        if "requirements to authenticate" in str(e):
            # La regla authRule rechaza las cuentas desactivadas.
            raise ErrorPocketBase("Tu cuenta está desactivada.") from e
        raise


def es_admin(sesion):
    return sesion["record"].get("rol") == "admin"


def listar_usuarios(sesion, url_base=None):
    respuesta = _pedir(
        "/api/collections/users/records?perPage=500&sort=email",
        url_base=url_base,
        metodo="GET",
        token=sesion["token"],
    )
    return respuesta["items"]


def actualizar_usuario(sesion, id_usuario, datos, url_base=None):
    return _pedir(
        f"/api/collections/users/records/{id_usuario}",
        datos,
        url_base,
        metodo="PATCH",
        token=sesion["token"],
    )


def generar_password(largo=12):
    # Sin caracteres que se confunden al dictarlos (0/O, 1/l/I).
    alfabeto = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


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
            sesion = iniciar_sesion(email, password)
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.app.entrar(sesion)


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
            sesion = iniciar_sesion(email, password)
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.app.entrar(sesion)


class PantallaConversor(ttk.Frame):
    def __init__(self, app, sesion):
        super().__init__(app, padding=20)
        self.app = app
        self.usuario = sesion["record"]
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

        ttk.Label(self, text=f"Sesión: {self.usuario['email']}", foreground="gray").grid(
            column=0, row=6, columnspan=2, pady=(12, 0)
        )
        if es_admin(sesion):
            _enlace(self, 7, "Volver al panel de admin", lambda: app.mostrar(PantallaAdmin, sesion=sesion))
        _enlace(self, 8, "Cerrar sesión", lambda: app.mostrar(PantallaLogin))
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


class PantallaAdmin(ttk.Frame):
    """Solo para rol admin. PocketBase rechaza estas acciones a cualquier otro usuario."""

    def __init__(self, app, sesion):
        super().__init__(app, padding=20)
        self.app = app
        self.sesion = sesion
        self.usuarios = {}
        _titulo(self, "Panel de administración")

        self.tabla = ttk.Treeview(
            self, columns=("email", "rol", "estado"), show="headings", height=10,
            selectmode="browse",
        )
        for columna, titulo, ancho in (
            ("email", "Email", 260), ("rol", "Rol", 80), ("estado", "Estado", 100)
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="w")
        self.tabla.grid(column=0, row=1, columnspan=2)

        botones = ttk.Frame(self)
        botones.grid(column=0, row=2, columnspan=2, pady=12)
        self.boton_estado = ttk.Button(
            botones, text="Desactivar", command=self.cambiar_estado
        )
        self.boton_estado.grid(column=0, row=0, padx=4)
        ttk.Button(
            botones, text="Resetear contraseña", command=self.resetear_password
        ).grid(column=1, row=0, padx=4)
        ttk.Button(botones, text="Actualizar", command=self.cargar).grid(
            column=2, row=0, padx=4
        )
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._actualizar_boton_estado())

        ttk.Label(self, text=f"Sesión: {sesion['record']['email']}", foreground="gray").grid(
            column=0, row=3, columnspan=2
        )
        _enlace(self, 4, "Abrir el conversor", lambda: app.mostrar(PantallaConversor, sesion=sesion))
        _enlace(self, 5, "Cerrar sesión", lambda: app.mostrar(PantallaLogin))
        self.cargar()

    def accion_principal(self):
        self.cargar()

    def cargar(self):
        try:
            usuarios = listar_usuarios(self.sesion)
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.usuarios = {u["id"]: u for u in usuarios}
        self.tabla.delete(*self.tabla.get_children())
        for u in usuarios:
            self.tabla.insert("", "end", iid=u["id"], values=(
                u["email"],
                "admin" if u.get("rol") == "admin" else "usuario",
                "Desactivada" if u.get("desactivado") else "Activa",
            ))
        self._actualizar_boton_estado()

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo(NOMBRE_APP, "Elegí una cuenta de la lista.")
            return None
        return self.usuarios[seleccion[0]]

    def _actualizar_boton_estado(self):
        seleccion = self.tabla.selection()
        desactivado = seleccion and self.usuarios[seleccion[0]].get("desactivado")
        self.boton_estado.config(text="Activar" if desactivado else "Desactivar")

    def cambiar_estado(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        if usuario["id"] == self.sesion["record"]["id"]:
            messagebox.showerror(NOMBRE_APP, "No podés desactivar tu propia cuenta.")
            return
        desactivar = not usuario.get("desactivado")
        accion = "desactivar" if desactivar else "activar"
        if not messagebox.askyesno(NOMBRE_APP, f"¿Querés {accion} la cuenta {usuario['email']}?"):
            return
        try:
            actualizar_usuario(self.sesion, usuario["id"], {"desactivado": desactivar})
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.cargar()
        self.tabla.selection_set(usuario["id"])

    def resetear_password(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        if not messagebox.askyesno(
            NOMBRE_APP, f"¿Generar una contraseña nueva para {usuario['email']}?"
        ):
            return
        nueva = generar_password()
        try:
            actualizar_usuario(
                self.sesion, usuario["id"], {"password": nueva, "passwordConfirm": nueva}
            )
        except ErrorPocketBase as e:
            messagebox.showerror(NOMBRE_APP, str(e))
            return
        self.clipboard_clear()
        self.clipboard_append(nueva)
        messagebox.showinfo(
            NOMBRE_APP,
            f"Nueva contraseña de {usuario['email']}:\n\n{nueva}\n\n"
            "Ya está copiada al portapapeles. Pasásela al usuario por un medio seguro.",
        )


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

    def entrar(self, sesion):
        self.mostrar(PantallaAdmin if es_admin(sesion) else PantallaConversor, sesion=sesion)


if __name__ == "__main__":
    App().mainloop()
