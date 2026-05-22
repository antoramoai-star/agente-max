import anthropic
import sqlite3
import schedule
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import sys

from dotenv import load_dotenv
import os
load_dotenv()
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
HORA_RESUMEN = "06:00"

client = anthropic.Anthropic(api_key=API_KEY)

# CONTADOR DE COSTOS
SALDO_INICIAL = 19.32
costo_total_sesion = 0.0
PRECIO_INPUT = 0.80 / 1_000_000
PRECIO_OUTPUT = 4.00 / 1_000_000

def calcular_costo(input_tokens, output_tokens):
    return (input_tokens * PRECIO_INPUT) + (output_tokens * PRECIO_OUTPUT)

def mostrar_costo(response):
    global costo_total_sesion
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    costo_msg = calcular_costo(input_tokens, output_tokens)
    costo_total_sesion += costo_msg
    saldo_estimado = SALDO_INICIAL - costo_total_sesion
    print(f"\n💰 Este mensaje: ${costo_msg:.4f} USD | 📊 Sesion: ${costo_total_sesion:.4f} USD | 💳 Saldo estimado: ${saldo_estimado:.2f} USD\n")

app = Flask(__name__)

def escuchar_voz():
    try:
        import pyaudio
        import wave
        import speech_recognition as sr
        import threading

        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 1024

        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        frames = []
        grabando = [True]

        def grabar():
            while grabando[0]:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)

        print("Max: Presiona ENTER para empezar a grabar...")
        input()
        print("Max: Grabando... habla con calma. Presiona ENTER cuando termines.")

        hilo = threading.Thread(target=grabar)
        hilo.start()
        input()
        grabando[0] = False
        hilo.join()

        stream.stop_stream()
        stream.close()
        p.terminate()

        archivo = "/tmp/voz_max.wav"
        wf = wave.open(archivo, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
        wf.close()

        print("Max: Procesando tu mensaje...")
        r = sr.Recognizer()
        with sr.AudioFile(archivo) as source:
            audio = r.record(source)
        texto = r.recognize_google(audio, language="es-ES")
        print(f"Tu (voz): {texto}")
        return texto

    except Exception as e:
        print(f"Max: Error: {e}")
        return None

# ─────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────

def crear_db():
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS registros (id INTEGER PRIMARY KEY, fecha TEXT, hora TEXT, tipo TEXT, contenido TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS resumenes (id INTEGER PRIMARY KEY, fecha TEXT, resumen TEXT)''')
    # NUEVO: tabla para guardar el historial del chat
    c.execute('''CREATE TABLE IF NOT EXISTS historial_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT, contenido TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def guardar_registro(tipo, contenido):
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d")
    hora = datetime.now().strftime("%H:%M")
    c.execute('INSERT INTO registros (fecha, hora, tipo, contenido) VALUES (?, ?, ?, ?)', (fecha, hora, tipo, contenido))
    conn.commit()
    conn.close()

def obtener_registros_hoy():
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d")
    c.execute('SELECT hora, tipo, contenido FROM registros WHERE fecha = ? ORDER BY hora', (fecha,))
    registros = c.fetchall()
    conn.close()
    return registros

def guardar_resumen(resumen):
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d")
    c.execute('INSERT INTO resumenes (fecha, resumen) VALUES (?, ?)', (fecha, resumen))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# LOGICA DEL AGENTE
# ─────────────────────────────────────────────

def generar_resumen():
    registros = obtener_registros_hoy()
    if not registros:
        return "No hay registros para hoy todavia."
    contenido = "\n".join([f"[{hora}] {tipo.upper()}: {c}" for hora, tipo, c in registros])
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": f"Eres mi agente personal. Analiza mis registros y dame un resumen motivador:\n{contenido}\n\nResume comidas, entrenamiento, tareas y da consejos para manana."}]
    )
    mostrar_costo(response)
    resumen = response.content[0].text
    guardar_resumen(resumen)
    return resumen

def chat_con_agente(mensaje, historial):
    registros = obtener_registros_hoy()
    contexto = ""
    if registros:
        contexto = "Registros de hoy:\n" + "\n".join([f"- [{h}] {t}: {c}" for h, t, c in registros])
    messages = historial + [{"role": "user", "content": mensaje}]
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=f"Eres Max, agente personal de bienestar. Registras comidas, ejercicios y tareas. Se amigable y motivador.\n{contexto}",
        messages=messages
    )
    mostrar_costo(response)
    return response.content[0].text

# ─────────────────────────────────────────────
# RUTAS FLASK
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/registros', methods=['GET'])
def get_registros():
    registros = obtener_registros_hoy()
    return jsonify([{"hora": h, "tipo": t, "contenido": c} for h, t, c in registros])

@app.route('/api/resumen', methods=['GET'])
def get_resumen():
    return jsonify({"resumen": generar_resumen()})

@app.route('/api/audio', methods=['POST'])
def audio():
    import wave
    import speech_recognition as sr
    try:
        audio_data = request.data
        webm_file = '/tmp/voz_web.webm'
        wav_file = '/tmp/voz_web.wav'
        with open(webm_file, 'wb') as f:
            f.write(audio_data)
        from pydub import AudioSegment
        audio_seg = AudioSegment.from_file(webm_file, format='webm')
        audio_seg.export(wav_file, format='wav')
        r = sr.Recognizer()
        with sr.AudioFile(wav_file) as source:
            audio = r.record(source)
        texto = r.recognize_google(audio, language='es-ES')
        return jsonify({'texto': texto})
    except sr.UnknownValueError:
        return jsonify({'error': 'No te escuche bien'})
    except Exception as e:
        return jsonify({'error': str(e)})

# NUEVO: endpoint para leer el historial guardado
@app.route('/api/historial_chat', methods=['GET'])
def get_historial_chat():
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    c.execute('SELECT rol, contenido FROM historial_chat ORDER BY fecha ASC LIMIT 100')
    mensajes = [{"rol": fila[0], "contenido": fila[1]} for fila in c.fetchall()]
    conn.close()
    return jsonify(mensajes)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    mensaje = data['mensaje']
    historial = data.get('historial', [])
    ml = mensaje.lower()
    if any(p in ml for p in ['comi', 'desayune', 'almorcé', 'cene', 'tome', 'bebi']):
        guardar_registro('comida', mensaje)
    elif any(p in ml for p in ['ejercite', 'entrene', 'hice', 'series', 'repeticiones', 'gym', 'corri']):
        guardar_registro('ejercicio', mensaje)
    elif any(p in ml for p in ['complete', 'termine', 'logre', 'tarea']):
        guardar_registro('tarea', mensaje)

    respuesta = chat_con_agente(mensaje, historial)

    # NUEVO: guardar el mensaje y la respuesta en la base de datos
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    c.execute('INSERT INTO historial_chat (rol, contenido) VALUES (?, ?)', ('user', mensaje))
    c.execute('INSERT INTO historial_chat (rol, contenido) VALUES (?, ?)', ('assistant', respuesta))
    conn.commit()
    conn.close()

    return jsonify({"respuesta": respuesta})

# ─────────────────────────────────────────────
# MODO TERMINAL
# ─────────────────────────────────────────────

def resumen_automatico():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Resumen automatico:")
    print(generar_resumen())

def iniciar_scheduler():
    schedule.every().day.at(HORA_RESUMEN).do(resumen_automatico)
    while True:
        schedule.run_pending()
        time.sleep(60)

def procesar_mensaje(entrada, historial):
    ml = entrada.lower()
    if any(p in ml for p in ['comi', 'desayune', 'almorcé', 'cene', 'tome', 'bebi']):
        guardar_registro('comida', entrada)
    elif any(p in ml for p in ['ejercite', 'entrene', 'hice', 'series', 'repeticiones', 'gym', 'corri']):
        guardar_registro('ejercicio', entrada)
    elif any(p in ml for p in ['complete', 'termine', 'logre', 'tarea']):
        guardar_registro('tarea', entrada)
    respuesta = chat_con_agente(entrada, historial)
    historial.append({"role": "user", "content": entrada})
    historial.append({"role": "assistant", "content": respuesta})
    print(f"Max: {respuesta}\n")
    return historial

def modo_terminal(usar_voz=False):
    crear_db()
    historial = []
    print("\n" + "="*50)
    print("  Max esta listo!")
    if usar_voz:
        print("  Escribe 'v' para hablar por voz")
    print("  Comandos: resumen, registros, salir")
    print("="*50 + "\n")
    while True:
        try:
            entrada = input("Tu: ").strip()
            if not entrada:
                continue
            if entrada.lower() == 'salir':
                print("Max: Hasta luego! Sigue con tus metas!")
                break
            elif entrada.lower() == 'resumen':
                print("\nMax: Generando tu resumen...")
                print(f"\n{generar_resumen()}\n")
            elif entrada.lower() == 'registros':
                registros = obtener_registros_hoy()
                if registros:
                    print("\nRegistros de hoy:")
                    for hora, tipo, contenido in registros:
                        print(f"  [{hora}] {tipo.upper()}: {contenido}")
                    print()
                else:
                    print("Max: Aun no tienes registros hoy.\n")
            elif usar_voz and entrada.lower() in ['v', 'voz']:
                texto = escuchar_voz()
                if texto:
                    historial = procesar_mensaje(texto, historial)
                else:
                    print("Max: No te escuche, intenta de nuevo.\n")
            else:
                historial = procesar_mensaje(entrada, historial)
        except KeyboardInterrupt:
            print("\nMax: Hasta luego!")
            break

# ─────────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    crear_db()
    threading.Thread(target=iniciar_scheduler, daemon=True).start()
    print("\n" + "="*50)
    print("  AGENTE PERSONAL - MAX")
    print("="*50)
    print("\nElige como usar tu agente:")
    print("  1 - Solo texto")
    print("  2 - Solo web")
    print("  3 - Ambos (texto + web)")
    print("  4 - Ambos con VOZ\n")
    opcion = input("Opcion (1/2/3/4): ").strip()
    if opcion == "1":
        modo_terminal(usar_voz=False)
    elif opcion == "2":
        print("\nWeb en: http://localhost:8888\n")
        app.run(debug=False, port=8888, host="0.0.0.0")
    elif opcion == "3":
        threading.Thread(target=lambda: app.run(debug=False, port=8888, host="0.0.0.0", use_reloader=False), daemon=True).start()
        modo_terminal(usar_voz=False)
    elif opcion == "4":
        print("\nWeb en: http://localhost:8888")
        print("Escribe 'v' para hablar por voz\n")
        threading.Thread(target=lambda: app.run(debug=False, port=8888, host="0.0.0.0", use_reloader=False), daemon=True).start()
        modo_terminal(usar_voz=True)
