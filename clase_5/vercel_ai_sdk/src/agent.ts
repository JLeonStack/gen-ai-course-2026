/**
 * Mini CLI agéntica con Vercel AI SDK (v7).
 *
 * Es el mismo agente de 01_agente_desde_cero.ipynb y coding_agent.py, en TypeScript:
 * - las tools se definen con tool() + un esquema Zod;
 * - ToolLoopAgent implementa el loop modelo → tools → modelo;
 * - la CLI guarda la conversación (multi-turno), muestra cada operación y pide permiso.
 *
 * Uso (desde clase_5/vercel_ai_sdk):
 *   python ../proyecto_demo.py      # resetea ../workspace con los 3 bugs
 *   bun start                       # chat interactivo
 *   bun start --yolo                # sin pedir permisos
 */
import { execFile } from "node:child_process";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { openai } from "@ai-sdk/openai";
import { isStepCount, type ModelMessage, ToolLoopAgent, tool } from "ai";
import { config } from "dotenv";
import { z } from "zod";

const here = path.dirname(fileURLToPath(import.meta.url));
config({ path: path.resolve(here, "../../../.env"), quiet: true }); // .env del root del repo

const WORKSPACE = path.resolve(here, "../../workspace");
const MODEL = process.env.OPENAI_MODEL ?? "gpt-6-luna";
const COMANDOS_PERMITIDOS = new Set(["python", "python3", "ls", "cat", "grep"]);

const run = promisify(execFile);
const rl = createInterface({ input: process.stdin });
const lines = rl[Symbol.asyncIterator]();

// Lee una línea del usuario (null si cerró la entrada con Ctrl+D).
async function ask(prompt: string): Promise<string | null> {
  process.stdout.write(prompt);
  const { value, done } = await lines.next();
  return done ? null : value.trim();
}
let yolo = process.argv.includes("--yolo");

// ---------------------------------------------------------------------------
// Colores y helpers de la UI
// ---------------------------------------------------------------------------

const color = (code: number) => (text: string) => `\u001b[${code}m${text}\u001b[0m`;
const [dim, bold, red, green, yellow, cyan, blue] = [2, 1, 31, 32, 33, 36, 94].map(color);

const show = (label: string, target: string) => console.log(`${cyan("●")} ${bold(label)}(${target})`);
const result = (text: string) => console.log(dim(`  ⎿ ${text}`));
const lastLines = (text: string, n = 8) => text.trim().split("\n").slice(-n).map((l) => `    ${l}`).join("\n");

const siempre = new Set<string>();

async function permitir(toolName: string): Promise<boolean> {
  if (yolo || siempre.has(toolName)) return true;
  const answer = (await ask(yellow("  ¿Permitir? [s]í / [n]o / [a] siempre: ")))?.toLowerCase();
  if (answer === "a") siempre.add(toolName);
  return answer === "s" || answer === "a";
}

// Sandbox de rutas: nada fuera del workspace.
function safePath(relative: string): string {
  const full = path.resolve(WORKSPACE, relative.replace(/^\/+/, ""));
  if (full !== WORKSPACE && !full.startsWith(WORKSPACE + path.sep)) {
    throw new Error(`Ruta fuera del workspace: ${relative}`);
  }
  return full;
}

async function runCommandRaw(command: string) {
  const [bin, ...args] = command.trim().split(/\s+/);
  if (!bin || !COMANDOS_PERMITIDOS.has(bin)) {
    return { error: `Comando no permitido. Permitidos: ${[...COMANDOS_PERMITIDOS].join(", ")}` };
  }
  const exe = bin === "python" ? "python3" : bin;
  try {
    const { stdout, stderr } = await run(exe, args, { cwd: WORKSPACE, timeout: 30_000 });
    return { exit_code: 0, output: (stderr + stdout).slice(-4000) };
  } catch (err) {
    const e = err as { code?: number; stdout?: string; stderr?: string };
    return { exit_code: e.code ?? 1, output: `${e.stderr ?? ""}${e.stdout ?? ""}`.slice(-4000) };
  }
}

// ---------------------------------------------------------------------------
// Tools: cada una muestra en pantalla lo que hace
// ---------------------------------------------------------------------------

const listFiles = tool({
  description: "Lista archivos y carpetas de un directorio del workspace. '.' es la raíz.",
  inputSchema: z.object({ path: z.string().describe("Ruta relativa al workspace") }),
  execute: async ({ path: dir }) => {
    show("List", dir);
    const entries = await readdir(safePath(dir), { withFileTypes: true });
    const names = entries
      .filter((e) => !e.name.startsWith(".") && e.name !== "__pycache__")
      .map((e) => (e.isDirectory() ? `${e.name}/` : e.name));
    result(`${names.length} entradas: ${names.join(", ")}`);
    return names;
  },
});

const readFileTool = tool({
  description: "Devuelve el contenido completo de un archivo del workspace.",
  inputSchema: z.object({ path: z.string() }),
  execute: async ({ path: file }) => {
    show("Read", file);
    const content = await readFile(safePath(file), "utf-8");
    result(`leídas ${content.split("\n").length} líneas`);
    return content;
  },
});

const editFile = tool({
  description:
    "Reemplaza la única aparición de old_str por new_str en un archivo. " +
    "old_str debe copiarse exacto (incluida la indentación) y aparecer una sola vez. " +
    "Si old_str es vacío, crea o sobrescribe el archivo con new_str.",
  inputSchema: z.object({ path: z.string(), old_str: z.string(), new_str: z.string() }),
  execute: async ({ path: file, old_str, new_str }) => {
    show("Edit", file);
    const full = safePath(file);
    const original = old_str === "" ? "" : await readFile(full, "utf-8");
    const count = original.split(old_str).length - 1;
    if (old_str !== "" && count !== 1) {
      // Errores como datos: el modelo los lee y se corrige.
      const error = `old_str aparece ${count} veces. Tiene que aparecer exactamente una.`;
      console.log(red(`  ⎿ ${error}`));
      return { error };
    }
    // Mostramos el cambio ANTES de aplicarlo.
    for (const line of old_str.split("\n").filter(Boolean)) console.log(red(`    - ${line}`));
    for (const line of new_str.split("\n").filter(Boolean)) console.log(green(`    + ${line}`));
    if (!(await permitir("edit_file"))) {
      result("rechazado");
      return { error: "El usuario rechazó esta acción." };
    }
    await writeFile(full, old_str === "" ? new_str : original.replace(old_str, new_str), "utf-8");
    result(old_str === "" ? "archivo creado" : "archivo editado");
    return { action: "edited" };
  },
});

const runCommand = tool({
  description:
    "Ejecuta un comando en la raíz del workspace y devuelve exit_code y la salida. " +
    "Solo se permiten: python, ls, cat, grep. Para los tests: python -m unittest -v",
  inputSchema: z.object({ command: z.string() }),
  execute: async ({ command }) => {
    show("Bash", command);
    if (!(await permitir("run_command"))) {
      result("rechazado");
      return { error: "El usuario rechazó esta acción." };
    }
    const res = await runCommandRaw(command);
    if ("error" in res) {
      console.log(red(`  ⎿ ${res.error}`));
    } else {
      console.log(`  ⎿ ${res.exit_code === 0 ? green("✓ exit 0") : red(`✗ exit ${res.exit_code}`)}`);
      console.log(dim(lastLines(res.output)));
    }
    return res;
  },
});

// ---------------------------------------------------------------------------
// El agente
// ---------------------------------------------------------------------------

const agent = new ToolLoopAgent({
  model: openai(MODEL), // Responses API por defecto; lee OPENAI_API_KEY
  instructions: `Sos un coding agent que trabaja sobre un proyecto Python chico en un workspace.

Reglas:
- Explorá antes de actuar: listá archivos y leé el código antes de editarlo.
- Usá edit_file con un old_str exacto que aparezca una sola vez.
- Después de cambiar código, corré los tests con \`python -m unittest -v\`.
- No modifiques los tests salvo que el usuario lo pida explícitamente.
- Si el usuario rechaza una acción, no la repitas: proponé otra cosa o preguntá.
- Cuando termines, explicá en pocas líneas qué cambiaste y por qué.`,
  tools: {
    list_files: listFiles,
    read_file: readFileTool,
    edit_file: editFile,
    run_command: runCommand,
  },
  stopWhen: isStepCount(25), // nuestro max_steps
  toolCallConcurrency: 1, // de a una tool por vez, para poder pedir permiso por consola
});

// ---------------------------------------------------------------------------
// La CLI
// ---------------------------------------------------------------------------

const messages: ModelMessage[] = []; // la memoria: toda la conversación
const sesion = { input: 0, output: 0 };

async function turno(prompt: string) {
  messages.push({ role: "user", content: prompt });
  const start = Date.now();
  console.log(dim("  pensando…"));

  const res = await agent.generate({ messages });
  messages.push(...res.response.messages);

  const { inputTokens = 0, outputTokens = 0 } = res.totalUsage;
  sesion.input += inputTokens;
  sesion.output += outputTokens;

  console.log(`\n${blue("◆")} ${res.text}`);
  console.log(
    dim(`\n  ${res.steps.length} pasos · ${inputTokens} tokens entrada · ${outputTokens} salida · ` +
      `${((Date.now() - start) / 1000).toFixed(1)}s\n`),
  );
}

const HELP = `
  ${bold("/help")}     esta ayuda
  ${bold("/clear")}    borra la conversación (el agente olvida todo)
  ${bold("/reset")}    vuelve el proyecto demo a su estado inicial (con bugs)
  ${bold("/tests")}    corre los tests vos mismo, sin el agente
  ${bold("/tokens")}   tokens gastados en la sesión
  ${bold("/yolo")}     activa/desactiva los permisos
  ${bold("/exit")}     salir
`;

async function comando(cmd: string): Promise<boolean> {
  switch (cmd) {
    case "/exit":
    case "/salir":
      return false;
    case "/help":
      console.log(HELP);
      break;
    case "/clear":
      messages.length = 0;
      console.log(dim("  Conversación borrada."));
      break;
    case "/reset":
      await run("python3", [path.resolve(here, "../../proyecto_demo.py")]);
      messages.length = 0;
      console.log(dim("  Workspace reseteado (con los 3 bugs) y conversación borrada."));
      break;
    case "/tests": {
      const res = await runCommandRaw("python -m unittest -v");
      if (res.output) console.log(dim(lastLines(res.output)));
      break;
    }
    case "/tokens":
      console.log(dim(`  Sesión: ${sesion.input} tokens de entrada · ${sesion.output} de salida`));
      break;
    case "/yolo":
      yolo = !yolo;
      console.log(dim(`  Modo yolo ${yolo ? "activado: no pido permisos" : "desactivado"}.`));
      break;
    default:
      console.log(red(`  Comando desconocido: ${cmd}. Probá /help`));
  }
  return true;
}

console.log(`\n${bold("✻ coding agent")} ${dim(`· AI SDK · ${MODEL}`)}`);
console.log(dim(`  workspace: ${WORKSPACE}`));
console.log(dim("  /help para ver comandos · Ctrl+D o /exit para salir\n"));

while (true) {
  const input = await ask(`${bold("❯")} `);
  if (input === null) break;
  if (!input) continue;
  if (input.startsWith("/")) {
    if (!(await comando(input))) break;
    continue;
  }
  try {
    await turno(input);
  } catch (err) {
    messages.pop(); // descartamos el mensaje que falló
    console.log(red(`  Error: ${(err as Error).message}`));
  }
}
rl.close();
console.log();
