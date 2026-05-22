import anthropic
import sqlite3
import schedule
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import os
import sys

# =====================
# CONFIGURACION
# =====================
API_KEY = "TU_API_KEY_AQUI"
HORA_RESUMEN = "06:00"

client = anthropic.Anthropic(api_key=API_KEY)
app = Flask(__name__)

# =====================
# VOZ
# =====================
def escuchar_voz():
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            print("Max: Escuchando... (habla ahora)")
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=8, phrase_time_limit=15)
        texto = r.recognize_google(audio, language="es-ES")
        print(f"Tu (voz): {texto}")
        return texto
    except ImportError:
        return None
    except Exception as e:
        print(f"Max: No te escuche bien, intenta de nuevo.")
        return None

# =====================
# BASE DE DATOS
# =====================
def crear_db():
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY,
            fecha TEXT,
            hora TEXT,
            tipo TEXT,
            contenido TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS resumenes (
            id INTEGER PRIMARY KEY,
            fecha TEXT,
            resumen TEXT
        )
    ''')
    conn.commit()
    conn.close()

def guardar_registro(tipo, contenido):
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d")
    hora = datetime.now().strftime("%H:%M")
    c.execute('INSERT INTO registros (fecha, hora, tipo, contenido) VALUES (?, ?, ?, ?)',
              (fecha, hora, tipo, contenido))
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

def obtener_resumenes():
    conn = sqlite3.connect('agente.db')
    c = conn.cursor()
    c.execute('SELECT fecha, resumen FROM resumenes ORDER BY fecha DESC LIMIT 7')
    resumenes = c.fetchall()
    conn.close()
    return resumenes

# =====================
# CLAUDE AI
# =====================
def generar_resumen():
    registros = obtener_registros_hoy()
    if not registros:
        return "No hay registros para hoy todavia."

    contenido = "\n".join([f"[{hora}] {tipo.upper()}: {c}" for hora, tipo, c in registros])

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""Eres mi agente personal de bienestar. Analiza mis registros de hoy y dame un resumen motivador.

Registros:
{contenido}

Por favor:
1. Resume lo que comi y si fue saludable
2. Analiza mi entrenamiento
3. Menciona las tareas completadas
4. Dame consejos para manana
5. Termina con una frase motivadora"""
        }]
    )
    resumen = response.content[0].text
    guardar_resumen(resumen)
    return resumen

def chat_con_agente(mensaje, historial):
    registros = obtener_registros_hoy()
    contexto = ""
    if registros:
        contexto = "Registros de hoy:\n"
        for hora, tipo, contenido in registros:
            contexto += f"- [{hora}] {tipo}: {contenido}\n"

    messages = historial + [{"role": "user", "content": mensaje}]

    system_prompt = f"""Eres un agente personal de bienestar llamado Max.
Ayudas a registrar comidas, ejercicios y tareas del dia.
Cuando el usuario mencione que comio, ejercito, o completo una tarea, confirma que lo registraste.
Se amigable, motivador y conciso.
{contexto}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=system_prompt,
        messages=messages
    )
    return response.content[0].text

# =====================
# RUTAS WEB
# =====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/registros', methods=['GET'])
def get_registros():
    registros = obtener_registros_hoy()
    return jsonify([{"hora": h, "tipo": t, "contenido": c} for h, t, c in registros])

@app.route('/api/guardar', methods=['POST'])
def guardar():
    data = request.json
    guardar_registro(data['tipo'], data['contenido'])
    return jsonify({"ok": True})

@app.route('/api/resumen', methods=['GET'])
def get_resumen():
    resumen = generar_resumen()
    return jsonify({"resumen": resumen})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    mensaje = data['mensaje']
    historial = data.get('historial', [])

    mensaje_lower = mensaje.lower()
    if any(p in mensaje_lower for p in ['comi', 'desayune', 'almorcé', 'cene', 'tome', 'bebi']):
        guardar_registro('comida', mensaje)
    elif any(p in mensaje_lower for p in ['ejercite', 'entrene', 'hice', 'series', 'repeticiones', 'gym', 'corri']):
        guardar_registro('ejercicio', mensaje)
    elif any(p in mensaje_lower for p in ['complete', 'termine', 'logre', 'tarea']):
        guardar_registro('tarea', mensaje)

    respuesta = chat_con_agente(mensaje, historial)
    return jsonify({"respuesta": respuesta})

@app.route('/api/resumenes', methods=['GET'])
def get_resumenes():
    resumenes = obtener_resumenes()
    return jsonify([{"fecha": f, "resumen": r} for f, r in resumenes])

# =====================
# RESUMEN AUTOMATICO
# =====================
def resumen_automatico():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Generando resumen automatico...")
    resumen = generar_resumen()
    print("\n" + "="*50)
    print("RESUMEN DE TU DIA")
    print("="*50)
    print(resumen)
    print("="*50 + "\n")

def iniciar_scheduler():
    schedule.every().day.at(HORA_RESUMEN).do(resumen_automatico)
    while True:
        schedule.run_pending()
        time.sleep(60)

# =====================
# TERMINAL (CLI)
# =====================
def modo_terminal(usar_voz=False):
    crear_db()
    historial = []

    print("\n" + "="*50)
    if usar_voz:
        print("  Max esta listo - MODO VOZ activado")
        print("  Escribe 'v' para hablar por voz")
        print("  O escribe normalmente con el teclado")
    else:
        print("  Max esta listo - MODO TEXTO")
    print("="*50)
    print("\nComandos: 'resumen', 'registros', 'voz', 'salir'\n")

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
                resumen = generar_resumen()
                print(f"\n{resumen}\n")

            elif entrada.lower() == 'registros':
                registros = obtener_registros_hoy()
                if registros:
                    print("\nRegistros de hoy:")
                    for hora, tipo, contenido in registros:
                        print(f"  [{hora}] {tipo.upper()}: {contenido}")
                    print()
                else:
                    print("Max: Aun no tienes registros hoy.\n")

            elif entrada.lower() == 'v' or entrada.lower() == 'voz':
                texto = escuchar_voz()
                if texto:
                    entrada = texto
                    # Detectar y guardar
                    entrada_lower = entrada.lower()
                    if any(p in entrada_lower for p in ['comi', 'desayune', 'almorcé', 'cene', 'tome', 'bebi']):
                        guardar_registro('comida', entrada)
                    elif any(p in entrada_lower for p in ['ejercite', 'entrene', 'hice', 'series', 'repeticiones', 'gym', 'corri']):
                        guardar_registro('ejercicio', entrada)
                    elif any(p in entrada_lower for p in ['complete', 'termine', 'logre', 'tarea']):
                        guardar_registro('tarea', entrada)

                    respuesta = chat_con_agente(entrada, historial)
                    historial.append({"role": "user", "content": entrada})
                    historial.append({"role": "assistant", "content": respuesta})
                    print(f"Max: {respuesta}\n")
                else:
                    print("Max: No te escuche, intenta de nuevo o escribe tu mensaje.\n")

            else:
                # Detectar y guardar automaticamente
                entrada_lower = entrada.lower()
                if any(p in entrada_lower for p in ['comi', 'desayune', 'almorcé', 'cene', 'tome', 'bebi']):
                    guardar_registro('comida', entrada)
                elif any(p in entrada_lower for p in ['ejercite', 'entrene', 'hice', 'series', 'repeticiones', 'gym', 'corri']):
                    guardar_registro('ejercicio', entrada)
                elif any(p in entrada_lower for p in ['complete', 'termine', 'logre', 'tarea']):
                    guardar_registro('tarea', entrada)

                respuesta = chat_con_agente(entrada, historial)
                historial.append({"role": "user", "content": entrada})
                historial.append({"role": "assistant", "content": respuesta})
                print(f"Max: {respuesta}\n")

        except KeyboardInterrupt:
            print("\nMax: Hasta luego!")
            break

# =====================
# INICIO
# =====================
if __name__ == "__main__":
    crear_db()

    scheduler_thread = threading.Thread(target=iniciar_scheduler, daemon=True)
    scheduler_thread.start()

    print("\n" + "="*50)
    print("  AGENTE PERSONAL - MAX")
    print("="*50)
    print("\nElige como usar tu agente:")
    print("  1 - Solo texto (Terminal)")
    print("  2 - Solo web (navegador)")
    print("  3 - Ambos (texto + web)")
    print("  4 - Ambos con VOZ\n")

    opcion = input("Opcion (1/2/3/4): ").strip()

    if opcion == "1":
        modo_terminal(usar_voz=False)

    elif opcion == "2":
        print("\nAbriendo en navegador...")
        print("Ve a: http://localhost:5000\n")
        app.run(debug=False, port=5000)

    elif opcion == "3":
        print("\nIniciando texto + web...")
        print("Web en: http://localhost:5000\n")
        web_thread = threading.Thread(target=lambda: app.run(debug=False, port=5000, use_reloader=False), daemon=True)
        web_thread.start()
        modo_terminal(usar_voz=False)

    elif opcion == "4":
        print("\nIniciando VOZ + web...")
        print("Web en: http://localhost:5000")
        print("Escribe 'v' cuando quieras hablar por voz\n")
        web_thread = threading.Thread(target=lambda: app.run(debug=False, port=5000, use_reloader=False), daemon=True)
        web_thread.start()
        modo_terminal(usar_voz=True)
