import { execFile } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { defineTool } from "eve/tools";
import { always } from "eve/tools/approval";
import { z } from "zod";

const run = promisify(execFile);
const ARCHIVOS = ["calculadora.py", "test_calculadora.py"];

export default defineTool({
  description:
    "Corre los tests del proyecto (python -m unittest -v) y devuelve exit_code y la salida. " +
    "Usala después de cada cambio en el código.",
  inputSchema: z.object({}),
  // Texto que muestra la TUI de eve mientras corre (y en el pedido de aprobación).
  label: { start: () => "Correr tests" },
  // Human-in-the-loop: cada ejecución pide aprobación en la terminal.
  approval: always(),
  async execute(_input, ctx) {
    // Las tools corren en el runtime de la app, no en el sandbox.
    // Copiamos el código del sandbox a una carpeta temporal y corremos Python acá.
    const sandbox = await ctx.getSandbox();
    const dir = await mkdtemp(path.join(tmpdir(), "eve-tests-"));
    try {
      for (const name of ARCHIVOS) {
        const content = await sandbox.readTextFile({ path: name });
        await writeFile(path.join(dir, name), content ?? "", "utf-8");
      }
      try {
        const { stdout, stderr } = await run("python3", ["-m", "unittest", "-v"], { cwd: dir, timeout: 30_000 });
        return { exit_code: 0, output: (stderr + stdout).slice(-4000) };
      } catch (err) {
        const e = err as { code?: number; stdout?: string; stderr?: string };
        return { exit_code: e.code ?? 1, output: `${e.stderr ?? ""}${e.stdout ?? ""}`.slice(-4000) };
      }
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  },
});
