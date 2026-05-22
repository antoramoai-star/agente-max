# AGENTE MAX - MEMORIA TÉCNICA

## INICIO RÁPIDO
cd ~/Downloads/agente_personal && python3 agente.py
# Elegir opción 4 → http://localhost:8888

## ARQUITECTURA
- agente.py → servidor Flask + API Claude
- templates/index.html → todo el frontend
- agente.db → base de datos SQLite
- Puerto: 8888 (HTTP)

## FUNCIONA
- Chat con Claude
- Micrófono con transcripción en vivo (SpeechRecognition)
- Toggle mic: presionar para iniciar/detener
- Sin auto-envío, el usuario envía manualmente (Ctrl+Enter)
- Textarea expandible min 80px max 400px
- 3 tabs: Chat / Registros / Resumen del Día
- Contador de registros

## PRÓXIMOS PASOS
1. Auto-inicio del servidor
2. Persistencia del historial en agente.db
3. Renderizar Markdown en respuestas
4. Usar mi_prompt_personalizado.txt
5. Organizar todo en una sola carpeta
