with open('agente.py', 'r') as f:
    contenido = f.read()

tools_code = '''
# ─────────────────────────────────────────────
# TOOLS - CALCULADORA
# ─────────────────────────────────────────────

tools = [
    {
        "name": "calculadora",
        "description": "Realiza operaciones matematicas basicas",
        "input_schema": {
            "type": "object",
            "properties": {
                "operacion": {"type": "string", "enum": ["sumar", "restar", "multiplicar", "dividir"]},
                "a": {"type": "number"},
                "b": {"type": "number"}
            },
            "required": ["operacion", "a", "b"]
        }
    }
]

def calculadora(operacion, a, b):
    if operacion == "sumar":       return a + b
    if operacion == "restar":      return a - b
    if operacion == "multiplicar": return a * b
    if operacion == "dividir":
        if b == 0: return "Error: division por cero"
        return a / b

def ejecutar_herramienta(nombre, argumentos):
    if nombre == "calculadora":
        return calculadora(**argumentos)
    return f"Herramienta {nombre} no reconocida"

'''

nueva_funcion = '''def chat_con_agente(mensaje, historial):
    registros = obtener_registros_hoy()
    contexto = ""
    if registros:
        contexto = "Registros de hoy:\\n" + "\\n".join([f"- [{h}] {t}: {c}" for h, t, c in registros])
    messages = historial + [{"role": "user", "content": mensaje}]
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            system=f"Eres Max, agente personal de bienestar. Registras comidas, ejercicios y tareas. Se amigable y motivador.\\n{contexto}",
            tools=tools,
            messages=messages
        )
        mostrar_costo(response)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Tool] {block.name}({block.input})")
                    resultado = ejecutar_herramienta(block.name, block.input)
                    print(f"[Tool] Resultado: {resultado}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(resultado)
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            return response.content[0].text

'''

import re
contenido_sin_funcion = re.sub(
    r'def chat_con_agente\(mensaje, historial\):.*?(?=\ndef |\nif __name__)',
    nueva_funcion,
    contenido,
    flags=re.DOTALL
)

contenido_final = contenido_sin_funcion.replace(
    "def chat_con_agente(",
    tools_code + "def chat_con_agente(",
    1
)

with open('agente.py', 'w') as f:
    f.write(contenido_final)

print("Listo! Tools agregadas.")
