"""
Mini CLI agéntica: un coding agent en la terminal, escrito desde cero.

Es el agente de 01_agente_desde_cero.ipynb con una interfaz para ver qué hace:
- cada operación del modelo (leer, editar, correr comandos) se muestra en vivo;
- las ediciones se muestran como diff ANTES de aplicarlas, y se pide permiso;
- al final de cada turno: pasos, tokens y tiempo;
- comandos con / para controlar la sesión (/help).

Uso:
    python proyecto_demo.py                       # resetea workspace/ con los bugs
    python coding_agent.py                        # trabaja sobre clase_5/workspace/
    python coding_agent.py --yolo                 # sin pedir permisos
    python coding_agent.py --workspace ../otro    # otro proyecto
    python coding_agent.py --model gpt-6-luna
"""
import argparse
import difflib
import itertools
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

import proyecto_demo

AGENT_DIR = Path(__file__).resolve().parent
# Busca el .env en clase_5/ y en el root del repo (el primero que define una variable gana).
load_dotenv(AGENT_DIR / ".env")
load_dotenv(AGENT_DIR.parent / ".env")

MAX_STEPS = 25  # tope de llamadas al modelo por turno: evita loops infinitos (y gastos)
COMANDOS_PERMITIDOS = {"python", "ls", "cat", "grep"}  # allowlist de run_command
TOOLS_SEGURAS = {"list_files", "read_file"}  # solo leen: nunca piden permiso

# El system prompt va en `instructions=` en cada llamada (no se guarda en la conversación).

SYSTEM_PROMPT = """Sos un coding agent que trabaja sobre un proyecto Python chico en un workspace.

Reglas:
- Antes de cada grupo de acciones, contá en una frase corta qué vas a hacer.
- Explorá antes de actuar: listá archivos y leé el código antes de editarlo.
- Usá edit_file con un old_str exacto que aparezca una sola vez.
- Después de cambiar código, corré los tests con `python -m unittest -v`.
- No modifiques los tests salvo que el usuario lo pida explícitamente.
- Si el usuario rechaza una acción, no la repitas: proponé otra cosa o preguntá.
- Cuando termines, explicá en pocas líneas qué cambiaste y por qué."""


# ---------------------------------------------------------------------------
# Colores ANSI (sin dependencias externas)
# ---------------------------------------------------------------------------

def _color(code: str):
    """Devuelve una función que pinta un texto con ese código ANSI. Ej: red("hola")."""
    return lambda text: f"\u001b[{code}m{text}\u001b[0m"


dim, bold = _color("2"), _color("1")
red, green, yellow, blue, magenta, cyan = (_color(c) for c in ("31", "32", "33", "94", "35", "36"))


# ---------------------------------------------------------------------------
# Tools: lo que el modelo puede hacer en el workspace.
# Son funciones de Python comunes que devuelven un dict; ese dict se serializa
# a JSON y es lo que el modelo "ve" como resultado de la tool.
# ---------------------------------------------------------------------------

WORKSPACE = proyecto_demo.WORKSPACE  # se puede cambiar con --workspace


def safe_path(path: str) -> Path:
    """
    Sandbox de rutas: convierte la ruta del modelo en absoluta DENTRO del workspace.

    Quitamos la "/" inicial (para que "/calculadora.py" sea relativa) y, tras
    resolver "..", verificamos que no se haya escapado. Si se escapa, ValueError:
    run_tool la convierte en un error que el modelo lee.
    """
    full = (WORKSPACE / path.lstrip("/")).resolve()
    if not full.is_relative_to(WORKSPACE):
        raise ValueError(f"Ruta fuera del workspace: {path}")
    return full


def list_files(path: str = ".") -> Dict[str, Any]:
    """Tool list_files: archivos y carpetas de un directorio (sin ocultos ni __pycache__)."""
    full = safe_path(path)
    files = [
        {"name": p.name, "type": "dir" if p.is_dir() else "file"}
        for p in sorted(full.iterdir())
        if not p.name.startswith((".", "__pycache__"))
    ]
    return {"path": path, "files": files}


def read_file(path: str) -> Dict[str, Any]:
    """Tool read_file: contenido completo de un archivo (todo entra al contexto del modelo)."""
    return {"path": path, "content": safe_path(path).read_text(encoding="utf-8")}


def preview_edit(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
    """
    Calcula cómo quedaría el archivo, sin escribirlo. Sirve para mostrar el diff.

    Devuelve {"before", "after"} o {"error"}. Exigimos que old_str aparezca
    EXACTAMENTE una vez: así el modelo no puede editar el lugar equivocado.
    """
    full = safe_path(path)
    before = full.read_text(encoding="utf-8") if full.exists() else ""
    if old_str == "":  # old_str vacío = crear o sobrescribir el archivo entero
        return {"before": before, "after": new_str}
    count = before.count(old_str)
    # Errores como datos: mensajes pensados para que el modelo sepa cómo corregirse.
    if count == 0:
        return {"error": "old_str no encontrado. Volvé a leer el archivo."}
    if count > 1:
        return {"error": f"old_str aparece {count} veces. Agregá contexto para que sea único."}
    return {"before": before, "after": before.replace(old_str, new_str, 1)}


def edit_file(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
    """Tool edit_file: aplica el cambio que calcula preview_edit (crea carpetas si hace falta)."""
    preview = preview_edit(path, old_str, new_str)
    if "error" in preview:
        return {"path": path, "error": preview["error"]}
    full = safe_path(path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(preview["after"], encoding="utf-8")
    return {"path": path, "action": "created" if old_str == "" else "edited"}


def run_command(command: str) -> Dict[str, Any]:
    """
    Tool run_command: corre un comando de la allowlist en el workspace.

    Seguridad básica (no es un sandbox real):
    - shlex.split + subprocess sin shell=True: no hay pipes, `;`, `&&` ni redirecciones;
    - solo binarios de COMANDOS_PERMITIDOS (ojo: `python` igual puede hacer cualquier cosa);
    - timeout de 30s y salida recortada a los últimos 4000 caracteres para no llenar el contexto.
    """
    args = shlex.split(command)
    if not args or args[0] not in COMANDOS_PERMITIDOS:
        return {"error": f"Comando no permitido. Permitidos: {sorted(COMANDOS_PERMITIDOS)}"}
    if args[0] == "python":
        args[0] = sys.executable  # el mismo Python del .venv que corre este script
    try:
        proc = subprocess.run(args, cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"error": "Timeout: el comando tardó más de 30 segundos."}
    return {"exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


# Nombre de la tool -> función que la ejecuta (lo usa run_tool para despachar).
TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "edit_file": edit_file,
    "run_command": run_command,
}

# Esquemas que se mandan a la API en `tools=` (formato Responses API).
# Es lo único que el modelo sabe de cada tool: nombre, descripción y JSON Schema
# de los argumentos. La description es prompt: cuanto más clara, mejor la usa.
TOOLS = [
    {
        "type": "function",
        "name": "list_files",
        "description": "Lista archivos y carpetas de un directorio del workspace.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Ruta relativa al workspace. '.' es la raíz."}},
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Devuelve el contenido completo de un archivo del workspace.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Ruta relativa al workspace."}},
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "edit_file",
        "description": (
            "Reemplaza la única aparición de old_str por new_str en un archivo. "
            "old_str debe copiarse exacto (incluida la indentación) y aparecer una sola vez. "
            "Si old_str es vacío, crea o sobrescribe el archivo con new_str."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "type": "function",
        "name": "run_command",
        "description": (
            "Ejecuta un comando en la raíz del workspace y devuelve exit_code, stdout y stderr. "
            "Solo se permiten: python, ls, cat, grep. Para los tests: python -m unittest -v"
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]


# ---------------------------------------------------------------------------
# UI: cómo mostramos lo que hace el modelo
# ---------------------------------------------------------------------------

# Nombre corto que se muestra en pantalla para cada tool (estilo Claude Code).
TOOL_LABELS = {"list_files": "List", "read_file": "Read", "edit_file": "Edit", "run_command": "Bash"}


class Spinner:
    """
    Muestra '⠋ pensando…' mientras esperamos al modelo (solo en una terminal real).

    Se usa como context manager (`with Spinner(...)`): al entrar arranca un thread
    que redibuja la línea cada 80ms; al salir lo frena y borra la línea.
    """

    def __init__(self, text: str):
        self.text = text
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        start = time.time()
        for frame in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{magenta(frame)} {dim(f'{self.text} {time.time() - start:.0f}s')}")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r\u001b[2K")
        sys.stdout.flush()

    def __enter__(self):
        if sys.stdout.isatty():
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()


def indent(text: str, prefix: str = "    ") -> str:
    """Agrega una sangría a cada línea del texto."""
    return "\n".join(prefix + line for line in text.splitlines())


def print_call(name: str, args: Dict[str, Any]) -> None:
    """Encabezado de una operación: ● Read(calculadora.py)."""
    target = args.get("command") or args.get("path") or ""
    print(f"{cyan('●')} {bold(TOOL_LABELS.get(name, name))}({target})")


def print_diff(before: str, after: str) -> None:
    """Imprime un diff unificado coloreado (+ verde, - rojo), máximo ~60 líneas."""
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=1)
    for line in itertools.islice(lines, 2, 60):  # saltamos los encabezados --- / +++
        if line.startswith("@@"):
            print(dim(f"    {line}"))
        elif line.startswith("+"):
            print(green(f"    {line}"))
        elif line.startswith("-"):
            print(red(f"    {line}"))
        else:
            print(dim(f"    {line}"))


def print_result(name: str, result: Dict[str, Any]) -> None:
    """
    Resumen corto del resultado, como lo vería un humano.

    Solo es para la pantalla: el modelo recibe el resultado completo en JSON.
    """
    if "error" in result:
        print(red(f"  ⎿ {result['error']}"))
    elif name == "list_files":
        names = [f["name"] + ("/" if f["type"] == "dir" else "") for f in result["files"]]
        print(dim(f"  ⎿ {len(names)} entradas: {', '.join(names)}"))
    elif name == "read_file":
        print(dim(f"  ⎿ leídas {len(result['content'].splitlines())} líneas"))
    elif name == "edit_file":
        print(dim(f"  ⎿ {'archivo creado' if result['action'] == 'created' else 'archivo editado'}"))
    elif name == "run_command":
        ok = result["exit_code"] == 0
        status = green("✓ exit 0") if ok else red(f"✗ exit {result['exit_code']}")
        print(f"  ⎿ {status}")
        output = (result["stderr"] + result["stdout"]).strip().splitlines()
        if output:
            print(dim(indent("\n".join(output[-8:]))))


# ---------------------------------------------------------------------------
# Harness: el loop del agente
# ---------------------------------------------------------------------------

class CodingAgent:
    """
    El harness: todo lo que rodea al modelo para convertirlo en un agente.

    - conversation: la memoria. Se manda entera en cada llamada; el modelo no
      recuerda nada por su cuenta. Crece con cada turno (y con ella los tokens).
    - always_allowed: tools que no piden permiso (las de lectura + las que el
      usuario aprobó con "a").
    - turn(): el loop agéntico modelo → tools → modelo.
    """

    def __init__(self, model: str, yolo: bool):
        self.client = OpenAI()  # lee OPENAI_API_KEY del entorno
        self.model = model
        self.yolo = yolo  # True = no pedir permisos
        self.conversation: List[Any] = []
        self.always_allowed = set(TOOLS_SEGURAS)
        self.session_tokens = {"input": 0, "output": 0}

    def ask_permission(self, name: str) -> bool:
        """Human-in-the-loop: pregunta en la terminal si se puede ejecutar la tool."""
        if self.yolo or name in self.always_allowed:
            return True
        answer = input(yellow("  ¿Permitir? [s]í / [n]o / [a] siempre para esta tool: ")).strip().lower()
        if answer == "a":
            self.always_allowed.add(name)
            return True
        return answer in ("s", "si", "sí", "y")

    def run_tool(self, call) -> Dict[str, Any]:
        """
        Ejecuta UNA function_call del modelo y devuelve el resultado (siempre un dict).

        Pasos: parsear args → mostrar la operación → (si es edit) mostrar el diff
        → pedir permiso → ejecutar → mostrar el resumen. Nunca lanza excepciones:
        cualquier falla vuelve como {"error": ...} para que el modelo la lea.
        """
        try:
            # call.arguments es un string JSON generado por el modelo.
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError as exc:
            return {"error": f"Argumentos inválidos: {exc}"}

        print_call(call.name, args)
        if call.name not in TOOL_FUNCTIONS:
            result = {"error": f"Tool desconocida: {call.name}"}
            print_result(call.name, result)
            return result

        # Las ediciones se muestran como diff antes de pedir permiso.
        if call.name == "edit_file":
            try:
                preview = preview_edit(**args)
            except Exception as exc:
                preview = {"error": f"{type(exc).__name__}: {exc}"}
            if "error" in preview:
                result = {"path": args.get("path"), "error": preview["error"]}
                print_result(call.name, result)
                return result
            print_diff(preview["before"], preview["after"])

        if not self.ask_permission(call.name):
            # El rechazo también es un resultado: el modelo se entera y cambia de plan.
            result = {"error": "El usuario rechazó esta acción."}
        else:
            try:
                result = TOOL_FUNCTIONS[call.name](**args)
            except Exception as exc:  # errores como datos: el modelo los lee y se corrige
                result = {"error": f"{type(exc).__name__}: {exc}"}
        print_result(call.name, result)
        return result

    def turn(self, user_input: str) -> None:
        """
        Un turno: el modelo trabaja (varios pasos) hasta responder sin pedir tools.

        Cada paso es una llamada a la API:
            1. mandamos toda la conversación + los esquemas de las tools;
            2. guardamos lo que devolvió el modelo (texto, razonamiento y function_calls);
            3. si pidió tools, las ejecutamos y agregamos un function_call_output por cada una;
            4. si no pidió ninguna, es la respuesta final y cortamos.
        """
        checkpoint = len(self.conversation)  # para poder deshacer el turno con Ctrl+C
        self.conversation.append({"role": "user", "content": user_input})
        tokens = {"input": 0, "output": 0}
        start = time.time()

        try:
            for step in range(1, MAX_STEPS + 1):
                with Spinner("pensando…"):
                    response = self.client.responses.create(
                        model=self.model,
                        instructions=SYSTEM_PROMPT,
                        input=self.conversation,
                        tools=TOOLS,
                    )
                # input_tokens incluye TODA la conversación reenviada: crece en cada paso.
                tokens["input"] += response.usage.input_tokens
                tokens["output"] += response.usage.output_tokens
                # Guardamos la salida tal cual (incluye los items de razonamiento y las
                # function_call). La API exige que cada function_call tenga su output.
                self.conversation += response.output

                calls = [item for item in response.output if item.type == "function_call"]
                if response.output_text:
                    # Con tools: es la narración del modelo. Sin tools: la respuesta final.
                    print(f"\n{blue('◆')} {response.output_text}" if not calls else dim(f"\n{response.output_text}"))
                if not calls:
                    break
                print()
                for call in calls:
                    result = self.run_tool(call)
                    # El call_id une este resultado con la function_call que lo pidió.
                    self.conversation.append({
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    })
            else:
                # for/else: este bloque corre solo si el for terminó sin `break`,
                # o sea, si se agotaron los pasos sin una respuesta final.
                print(red(f"\n⛔ Llegué a {MAX_STEPS} pasos sin terminar."))
        except KeyboardInterrupt:
            # Deshacemos el turno: una function_call sin su output rompe la próxima llamada.
            del self.conversation[checkpoint:]
            print(red("\n⏹ Turno interrumpido."))
            return

        self.session_tokens["input"] += tokens["input"]
        self.session_tokens["output"] += tokens["output"]
        print(dim(
            f"\n  {step} pasos · {tokens['input']:,} tokens entrada · "
            f"{tokens['output']:,} salida · {time.time() - start:.1f}s"
        ))


# ---------------------------------------------------------------------------
# Comandos de la sesión
# ---------------------------------------------------------------------------

HELP = f"""
  {bold('/help')}       esta ayuda
  {bold('/clear')}      borra la conversación (el agente olvida todo)
  {bold('/reset')}      vuelve el proyecto demo a su estado inicial (con bugs)
  {bold('/tests')}      corre los tests vos mismo, sin el agente
  {bold('/tokens')}     tokens gastados en la sesión
  {bold('/history')}    qué hay en el contexto del modelo
  {bold('/yolo')}       activa/desactiva los permisos
  {bold('/exit')}       salir (o Ctrl+D)
"""


def handle_command(agent: CodingAgent, command: str) -> bool:
    """Ejecuta un /comando. Devuelve False si hay que salir."""
    if command in ("/exit", "/quit", "/salir"):
        return False
    if command == "/help":
        print(HELP)
    elif command == "/clear":
        agent.conversation.clear()
        print(dim("  Conversación borrada."))
    elif command == "/reset":
        if WORKSPACE != proyecto_demo.WORKSPACE:
            print(red("  /reset solo funciona con el workspace del proyecto demo."))
        else:
            proyecto_demo.reset_workspace()
            agent.conversation.clear()
            print(dim("  Workspace reseteado (con los 3 bugs) y conversación borrada."))
    elif command == "/tests":
        print_result("run_command", run_command("python -m unittest -v"))
    elif command == "/tokens":
        t = agent.session_tokens
        print(dim(f"  Sesión: {t['input']:,} tokens de entrada · {t['output']:,} de salida"))
    elif command == "/history":
        # Los items pueden ser objetos del SDK (response.output) o dicts nuestros.
        kinds = [getattr(item, "type", None) or item.get("type") or item.get("role") for item in agent.conversation]
        counts = {k: kinds.count(k) for k in dict.fromkeys(kinds)}
        print(dim(f"  {len(kinds)} items en el contexto: {counts}"))
    elif command == "/yolo":
        agent.yolo = not agent.yolo
        print(dim(f"  Modo yolo {'activado: no pido permisos' if agent.yolo else 'desactivado'}."))
    else:
        print(red(f"  Comando desconocido: {command}. Probá /help"))
    return True


def main() -> None:
    """
    Punto de entrada: lee los flags, crea el agente y corre el REPL.

    Cada línea del usuario es un /comando (lo maneja handle_command) o un
    pedido para el agente (un turno completo con agent.turn).
    """
    global WORKSPACE  # las tools leen WORKSPACE, así que --workspace lo cambia para todas

    parser = argparse.ArgumentParser(description="Mini CLI agéntica para programar.")
    parser.add_argument("--workspace", type=Path, default=proyecto_demo.WORKSPACE)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-6-luna"))
    parser.add_argument("--yolo", action="store_true", help="no pedir permiso para editar o ejecutar")
    opts = parser.parse_args()

    WORKSPACE = opts.workspace.resolve()
    if not WORKSPACE.is_dir():
        print(f"No existe {WORKSPACE}. Para el proyecto demo corré: python proyecto_demo.py")
        return

    agent = CodingAgent(model=opts.model, yolo=opts.yolo)
    print(f"\n{bold('✻ coding agent')} {dim('· ' + opts.model)}")
    print(dim(f"  workspace: {WORKSPACE}"))
    print(dim("  /help para ver comandos · Ctrl+C corta un turno · Ctrl+D sale\n"))

    while True:
        try:
            user_input = input(f"{bold('❯')} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not user_input:
            continue
        if user_input.startswith("/"):
            if not handle_command(agent, user_input):
                break
            continue
        agent.turn(user_input)
        print()


if __name__ == "__main__":
    main()
