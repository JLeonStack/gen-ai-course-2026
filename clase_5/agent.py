"""
Primer agente: un coding agent mínimo, sin function calling nativo.

La idea es mostrar que un agente es solo un loop alrededor de un LLM:
    1. le explicamos al modelo (en el system prompt) qué tools existen;
    2. el modelo responde con una línea `tool: nombre({json})` cuando quiere usar una;
    3. nosotros parseamos ese texto A MANO, ejecutamos la función de Python
       y le devolvemos el resultado como un mensaje más;
    4. repetimos hasta que el modelo conteste sin pedir tools.

Es frágil a propósito: si el modelo escribe mal el formato, el parser no lo
reconoce. El notebook 01 resuelve eso con function calling nativo de la API.

Uso:
    python agent.py      # Ctrl+C o Ctrl+D para salir
"""
import inspect
import json
import os

from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Lee OPENAI_API_KEY (y opcionalmente OPENAI_MODEL) del .env del directorio actual.
load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
openai_client = OpenAI()

# El "protocolo" entre el modelo y nuestro código vive enteramente en este texto.
# {tool_list_repr} se reemplaza por la descripción de cada tool (ver get_full_system_prompt).
# Las llaves dobles {{ }} son llaves literales para .format().
SYSTEM_PROMPT = """
You are a coding assistant whose goal it is to help us solve coding tasks. 
You have access to a series of tools you can execute. Hear are the tools you can execute:

{tool_list_repr}

When you want to use a tool, reply with exactly one line in the format: 'tool: TOOL_NAME({{JSON_ARGS}})' and nothing else.
Use compact single-line JSON with double quotes. After receiving a tool_result(...) message, continue the task.
If no tool is needed, respond normally.
"""


# Códigos ANSI para colorear "You:" y "Assistant:" en la terminal.
YOU_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"

# Carpeta donde está este archivo: las rutas relativas se resuelven contra ella.
AGENT_DIR = Path(__file__).resolve().parent

def resolve_abs_path(path_str: str) -> Path:
    """
    Convierte la ruta que manda el modelo en una ruta absoluta.

    file.py -> .../clase_5/file.py
    Las rutas relativas se resuelven contra la carpeta de agent.py.
    Ojo: no hay sandbox; una ruta absoluta o con '..' puede salir de clase_5/.
    """
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (AGENT_DIR / path).resolve()
    return path

# ---------------------------------------------------------------------------
# Tools: funciones de Python comunes que el modelo puede pedir ejecutar.
# IMPORTANTE: su docstring es lo que ve el modelo (se inyecta en el system
# prompt vía tool.__doc__), así que funciona como la "descripción" de la tool.
# ---------------------------------------------------------------------------

def read_file_tool(filename: str) -> Dict[str, Any]:
    """
    Gets the full content of a file provided by the user.
    :param filename: The name of the file to read.
    :return: The full content of the file.
    """
    full_path = resolve_abs_path(filename)
    print(full_path)
    with open(str(full_path), "r") as f:
        content = f.read()
    return {
        "file_path": str(full_path),
        "content": content
    }

def list_files_tool(path: str) -> Dict[str, Any]:
    """
    Lists the files in a directory provided by the user.
    :param path: The path to a directory to list files from.
    :return: A list of files in the directory.
    """
    full_path = resolve_abs_path(path)
    all_files = []
    for item in full_path.iterdir():
        all_files.append({
            "filename": item.name,
            "type": "file" if item.is_file() else "dir"
        })
    return {
        "path": str(full_path),
        "files": all_files
    }

def edit_file_tool(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
    """
    Replaces first occurrence of old_str with new_str in file. If old_str is empty,
    create/overwrite file with new_str.
    :param path: The path to the file to edit.
    :param old_str: The string to replace.
    :param new_str: The string to replace with.
    :return: A dictionary with the path to the file and the action taken.
    """
    full_path = resolve_abs_path(path)
    # old_str vacío = crear (o pisar) el archivo entero.
    if old_str == "":
        full_path.write_text(new_str, encoding="utf-8")
        return {
            "path": str(full_path),
            "action": "created_file"
        }
    original = full_path.read_text(encoding="utf-8")
    # Si no encuentra el texto, devolvemos el error como dato (no excepción):
    # el modelo lo lee en el tool_result y puede corregirse.
    if original.find(old_str) == -1:
        return {
            "path": str(full_path),
            "action": "old_str not found"
        }
    edited = original.replace(old_str, new_str, 1)
    full_path.write_text(edited, encoding="utf-8")
    return {
        "path": str(full_path),
        "action": "edited"
    }


# Nombre que usa el modelo -> función de Python que lo implementa.
# Agregar una tool = escribir la función y sumarla acá (y en el if/elif del loop).
TOOL_REGISTRY = {
    "read_file": read_file_tool,
    "list_files": list_files_tool,
    "edit_file": edit_file_tool
}

# ---------------------------------------------------------------------------
# System prompt: le describimos las tools al modelo en texto plano.
# ---------------------------------------------------------------------------

def get_tool_str_representation(tool_name: str) -> str:
    """
    Describe una tool para el modelo: nombre, docstring y firma.

    inspect.signature() da algo como "(path: str, old_str: str, new_str: str)",
    que le dice al modelo qué argumentos poner en el JSON.
    """
    tool = TOOL_REGISTRY[tool_name]
    return f"""
    Name: {tool_name}
    Description: {tool.__doc__}
    Signature: {inspect.signature(tool)}
    """

def get_full_system_prompt():
    """Arma el system prompt final con la descripción de todas las tools del registro."""
    tool_str_repr = ""
    for tool_name in TOOL_REGISTRY:
        tool_str_repr += "TOOL\n===" + get_tool_str_representation(tool_name)
        tool_str_repr += f"\n{'='*15}\n"
    return SYSTEM_PROMPT.format(tool_list_repr=tool_str_repr)

# ---------------------------------------------------------------------------
# Parser: convierte el texto del modelo en llamadas a tools.
# ---------------------------------------------------------------------------

def extract_tool_invocations(text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Busca líneas 'tool: nombre({...})' en la respuesta del modelo.

    Devuelve una lista de (nombre_tool, args). Lista vacía = el modelo no pidió
    ninguna tool, o sea que es su respuesta final.
    El JSON tiene que venir en una sola línea; cualquier línea mal formada se
    ignora en silencio (esta es la parte frágil del protocolo de texto).
    """
    invocations = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("tool:"):
            continue
        try:
            # "tool: edit_file({...})" -> name="edit_file", rest="{...})"
            after = line[len("tool:"):].strip()
            name, rest = after.split("(", 1)
            name = name.strip()
            if not rest.endswith(")"):
                continue
            json_str = rest[:-1].strip()
            args = json.loads(json_str)
            invocations.append((name, args))
        except Exception:
            continue
    return invocations

def execute_llm_call(conversation: List[Dict[str, str]]):
    """
    Una llamada al modelo con toda la conversación; devuelve solo el texto.

    Fijate que NO le pasamos `tools=` a la API: para OpenAI esto es un chat
    común. Las tools existen solo porque las describimos en el system prompt.
    """
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=conversation,
        max_output_tokens=2000,
    )
    return response.output_text

# ---------------------------------------------------------------------------
# El loop del agente.
# ---------------------------------------------------------------------------

def run_coding_agent_loop():
    """
    Chat en la terminal con dos loops anidados:

    - loop externo: un turno por cada mensaje del usuario;
    - loop interno: los pasos del agente. Llama al modelo, ejecuta las tools
      que pidió, le devuelve los resultados y vuelve a llamarlo, hasta que
      responde sin pedir tools.

    `conversation` es toda la memoria del agente: se reenvía completa en cada
    llamada (el modelo no recuerda nada entre llamadas).
    """
    print(get_full_system_prompt())  # para ver qué recibe el modelo
    conversation = [{
        "role": "system",
        "content": get_full_system_prompt()
    }]
    while True:
        # --- Loop externo: esperar el próximo pedido del usuario ---
        try:
            user_input = input(f"{YOU_COLOR}You:{RESET_COLOR}:")
        except (KeyboardInterrupt, EOFError):
            break
        conversation.append({
            "role": "user",
            "content": user_input.strip()
        })
        # --- Loop interno: el agente trabaja hasta tener una respuesta final ---
        # (no tiene límite de pasos: un modelo que nunca deja de pedir tools lo cuelga)
        while True:
            assistant_response = execute_llm_call(conversation)
            tool_invocations = extract_tool_invocations(assistant_response)
            # Sin tools pedidas => respuesta final: la mostramos y cerramos el turno.
            if not tool_invocations:
                print(f"{ASSISTANT_COLOR}Assistant:{RESET_COLOR}: {assistant_response}")
                conversation.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                break
            # Ejecutamos cada tool pedida.
            # Nota: el mensaje del asistente con el "tool: ..." no se guarda en la
            # conversación; el modelo solo ve el tool_result. Funciona, pero pierde
            # el registro de qué pidió (un buen ejercicio es agregarlo).
            for name, args in tool_invocations:
                tool = TOOL_REGISTRY[name]  # KeyError si el modelo inventa una tool
                resp = ""
                print(name, args)
                # Mapeo manual de los args del JSON a los parámetros de cada función.
                # Con function calling nativo esto lo resuelve el esquema JSON.
                if name == "read_file":
                    resp = tool(args.get("filename", "."))
                elif name == "list_files":
                    resp = tool(args.get("path", "."))
                elif name == "edit_file":
                    resp = tool(args.get("path", "."),
                                args.get("old_str", ""),
                                args.get("new_str", ""))
                # El resultado vuelve como un mensaje de "user" con formato tool_result(...),
                # tal como lo promete el system prompt.
                conversation.append({
                    "role": "user",
                    "content": f"tool_result({json.dumps(resp)})"
                })


if __name__ == "__main__":
    run_coding_agent_loop()
