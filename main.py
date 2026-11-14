import os
import random
import tempfile
import unicodedata

import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.environ.get("SPEAK_IT_SECRET", "cambia-esta-clave-local")

# Palabras disponibles: español -> inglés.
PALABRAS = [
    {"es": "MANZANA", "en": "apple"},
    {"es": "PERRO", "en": "dog"},
    {"es": "GATO", "en": "cat"},
    {"es": "CASA", "en": "house"},
    {"es": "LIBRO", "en": "book"},
    {"es": "AGUA", "en": "water"},
    {"es": "COMIDA", "en": "food"},
    {"es": "ESCUELA", "en": "school"},
    {"es": "AMIGO", "en": "friend"},
    {"es": "ÁRBOL", "en": "tree"},
    {"es": "SOL", "en": "sun"},
    {"es": "LUNA", "en": "moon"},
    {"es": "SILLA", "en": "chair"},
    {"es": "MESA", "en": "table"},
    {"es": "VENTANA", "en": "window"},
    {"es": "PUERTA", "en": "door"},
    {"es": "ZAPATO", "en": "shoe"},
    {"es": "CAMISA", "en": "shirt"},
    {"es": "LECHE", "en": "milk"},
    {"es": "PAN", "en": "bread"},
    {"es": "ROJO", "en": "red"},
    {"es": "AZUL", "en": "blue"},
    {"es": "VERDE", "en": "green"},
    {"es": "FELIZ", "en": "happy"},
    {"es": "CAKE", "en": "pastel"},
    
]

DIFICULTADES = {
    "Facil": {"nombre": "Fácil", "rondas": 5},
    "Medio": {"nombre": "Medio", "rondas": 7},
    "Dificil": {"nombre": "Difícil", "rondas": 10},
}


def normalizar(texto):
    """Pasa el texto a minúsculas y elimina puntuación/espacios extra."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return "".join(c for c in texto if c.isalnum() or c.isspace()).strip()


def grabar_y_reconocer(duracion=5, frecuencia=16000):
    """Graba desde el micrófono conectado al equipo donde corre Flask."""
    audio = sd.rec(
        int(duracion * frecuencia),
        samplerate=frecuencia,
        channels=1,
        dtype="int16"
    )
    sd.wait()

    reconocedor = sr.Recognizer()

    # SpeechRecognition puede leer el archivo WAV creado por scipy.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as archivo:
        ruta_audio = archivo.name

    try:
        write(ruta_audio, frecuencia, audio)
        with sr.AudioFile(ruta_audio) as fuente:
            datos = reconocedor.record(fuente)
        return reconocedor.recognize_google(datos, language="en-US")
    finally:
        if os.path.exists(ruta_audio):
            os.remove(ruta_audio)


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        dificultad = request.form.get("dificultad", "Facil")
        if dificultad not in DIFICULTADES:
            dificultad = "Facil"

        total = DIFICULTADES[dificultad]["rondas"]
        palabras = PALABRAS.copy()
        random.shuffle(palabras)

        session.clear()
        session["dificultad"] = dificultad
        session["nombre_dificultad"] = DIFICULTADES[dificultad]["nombre"]
        session["total"] = total
        session["ronda"] = 1
        session["puntos"] = 0
        session["palabras"] = palabras[:total]
        session["respondio"] = False
        session["terminado"] = False

        return redirect(url_for("juego"))

    return render_template("index.html", pantalla="menu")


@app.route("/juego")
def juego():
    if not session.get("palabras"):
        return redirect(url_for("inicio"))

    if session.get("terminado"):
        return redirect(url_for("resultado"))

    indice = session["ronda"] - 1
    palabra = session["palabras"][indice]

    return render_template(
        "index.html",
        pantalla="juego",
        palabra=palabra["es"],
        ronda=session["ronda"],
        total=session["total"],
        puntos=session["puntos"],
        dificultad=session["nombre_dificultad"],
        respondio=session.get("respondio", False),
        feedback=session.get("feedback"),
    )


@app.route("/grabar", methods=["POST"])
def grabar():
    if not session.get("palabras") or session.get("terminado"):
        return redirect(url_for("inicio"))

    if session.get("respondio"):
        return redirect(url_for("juego"))

    indice = session["ronda"] - 1
    respuesta_correcta = session["palabras"][indice]["en"]

    try:
        respuesta_usuario = grabar_y_reconocer()
        correcta = normalizar(respuesta_usuario) == normalizar(respuesta_correcta)

        if correcta:
            session["puntos"] += 10
            titulo = "✅ ¡EXCELENTE PRONUNCIACIÓN! (+10 pts)"
        else:
            titulo = "❌ ¡CASI LO LOGRAS!"

        detalle = (
            f'Escuchamos: "{respuesta_usuario}" | '
            f'Esperado: "{respuesta_correcta}"'
        )

    except sr.UnknownValueError:
        correcta = False
        titulo = "🤔 NO LOGRAMOS ENTENDERTE"
        detalle = f'La palabra correcta era "{respuesta_correcta}". Inténtalo en la próxima ronda.'
    except sr.RequestError:
        correcta = False
        titulo = "🌐 ERROR DE CONEXIÓN"
        detalle = "El reconocimiento de voz necesita internet. Comprueba tu conexión."
    except sd.PortAudioError:
        correcta = False
        titulo = "🎙️ NO SE PUDO ACCEDER AL MICRÓFONO"
        detalle = "Revisa que el micrófono esté conectado y permitido en tu equipo."
    except Exception as error:
        correcta = False
        titulo = "⚠️ OCURRIÓ UN ERROR"
        detalle = f"Revisa la configuración del micrófono. Detalle: {error}"

    session["respondio"] = True
    session["feedback"] = {
        "correcta": correcta,
        "titulo": titulo,
        "detalle": detalle,
    }
    session.modified = True
    return redirect(url_for("juego"))


@app.route("/responder", methods=["POST"])
def responder():
    """Permite escribir la traducción cuando el jugador no puede hablar."""
    if not session.get("palabras") or session.get("terminado"):
        return redirect(url_for("inicio"))

    if session.get("respondio"):
        return redirect(url_for("juego"))

    respuesta_usuario = request.form.get("respuesta", "").strip()
    if not respuesta_usuario:
        session["respondio"] = True
        session["feedback"] = {
            "correcta": False,
            "titulo": "✍️ NO ESCRIBISTE NINGUNA PALABRA",
            "detalle": "Puedes avanzar e intentarlo en la próxima ronda.",
        }
        session.modified = True
        return redirect(url_for("juego"))

    indice = session["ronda"] - 1
    respuesta_correcta = session["palabras"][indice]["en"]
    correcta = normalizar(respuesta_usuario) == normalizar(respuesta_correcta)

    if correcta:
        session["puntos"] += 10
        titulo = "✅ ¡RESPUESTA CORRECTA! (+10 pts)"
    else:
        titulo = "❌ ¡CASI LO LOGRAS!"

    session["respondio"] = True
    session["feedback"] = {
        "correcta": correcta,
        "titulo": titulo,
        "detalle": (
            f'Respuesta escrita: "{respuesta_usuario}" | '
            f'Esperado: "{respuesta_correcta}"'
        ),
    }
    session.modified = True
    return redirect(url_for("juego"))


@app.route("/siguiente", methods=["POST"])
def siguiente():
    if not session.get("respondio"):
        return redirect(url_for("juego"))

    if session["ronda"] < session["total"]:
        session["ronda"] += 1
        session["respondio"] = False
        session.pop("feedback", None)
        session.modified = True
        return redirect(url_for("juego"))

    session["terminado"] = True
    session.modified = True
    return redirect(url_for("resultado"))


@app.route("/resultado")
def resultado():
    if not session.get("terminado"):
        return redirect(url_for("inicio"))

    total_puntos = session["total"] * 10
    puntos = session["puntos"]
    porcentaje = (puntos / total_puntos) * 100 if total_puntos else 0

    if porcentaje == 100:
        rango = "🥇 ¡PERFECTO!"
    elif porcentaje >= 70:
        rango = "🥈 ¡BUEN TRABAJO!"
    elif porcentaje >= 40:
        rango = "🥉 ¡VAS POR BUEN CAMINO!"
    else:
        rango = "💪 ¡SIGUE PRACTICANDO!"

    return render_template(
        "index.html",
        pantalla="final",
        puntos=puntos,
        total_puntos=total_puntos,
        rango=rango,
        dificultad=session.get("nombre_dificultad", ""),
    )


if __name__ == "__main__":
    app.run(debug=True)
