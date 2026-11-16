"""Mi Cotizador: convierte pesos a dólares y guarda un historial."""

import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

NOMBRE_APP = "Mi Cotizador"
# Fuera del .app para que el historial sobreviva a actualizaciones y sea fácil de encontrar.
CARPETA_HISTORIAL = Path.home() / "Documents" / NOMBRE_APP
ARCHIVO_HISTORIAL = CARPETA_HISTORIAL / "historial.txt"


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


def guardar_en_historial(pesos, cotizacion, dolares, archivo=ARCHIVO_HISTORIAL, ahora=None):
    ahora = ahora or datetime.now()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    linea = (
        f"{ahora:%Y-%m-%d %H:%M:%S} | ARS {formatear(pesos)} | "
        f"cotización {formatear(cotizacion)} | USD {formatear(dolares)}\n"
    )
    with open(archivo, "a", encoding="utf-8") as f:
        f.write(linea)
    return linea


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NOMBRE_APP)
        self.resizable(False, False)

        marco = ttk.Frame(self, padding=20)
        marco.grid()

        ttk.Label(marco, text=NOMBRE_APP, font=("Helvetica", 18, "bold")).grid(
            column=0, row=0, columnspan=2, pady=(0, 15)
        )

        ttk.Label(marco, text="Monto en pesos (ARS):").grid(column=0, row=1, sticky="w", pady=4)
        self.pesos = ttk.Entry(marco, width=18)
        self.pesos.grid(column=1, row=1, pady=4)

        ttk.Label(marco, text="Cotización del dólar:").grid(column=0, row=2, sticky="w", pady=4)
        self.cotizacion = ttk.Entry(marco, width=18)
        self.cotizacion.grid(column=1, row=2, pady=4)

        ttk.Button(marco, text="Convertir", command=self.convertir).grid(
            column=0, row=3, columnspan=2, pady=12
        )

        self.resultado = ttk.Label(marco, text="", font=("Helvetica", 16))
        self.resultado.grid(column=0, row=4, columnspan=2)

        ttk.Label(
            marco, text=f"Historial: {ARCHIVO_HISTORIAL}", foreground="gray", wraplength=320
        ).grid(column=0, row=5, columnspan=2, pady=(12, 0))

        self.bind("<Return>", lambda _e: self.convertir())
        self.pesos.focus()

    def convertir(self):
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
            guardar_en_historial(pesos, cotizacion, dolares)
        except OSError as e:
            messagebox.showwarning(NOMBRE_APP, f"No se pudo guardar el historial:\n{e}")


if __name__ == "__main__":
    App().mainloop()
