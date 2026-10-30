"""
Proyecto de juguete que usan todos los ejemplos de agentes de la clase 5.

Crea (o resetea) la carpeta workspace/ con una calculadora que tiene 3 bugs
y sus tests. La tarea de cada agente es encontrar los bugs y arreglarlos.

Uso desde la terminal:
    python proyecto_demo.py          # resetea clase_5/workspace/
"""
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent / "workspace"

ARCHIVOS_INICIALES = {
    "calculadora.py": '''
        """Funciones de estadística básica."""


        def promedio(numeros):
            return sum(numeros) / (len(numeros) - 1)


        def maximo(numeros):
            resultado = 0
            for n in numeros:
                if n > resultado:
                    resultado = n
            return resultado


        def es_par(n):
            return n % 2 == 1
    ''',
    "test_calculadora.py": '''
        import unittest

        from calculadora import es_par, maximo, promedio


        class TestCalculadora(unittest.TestCase):
            def test_promedio(self):
                self.assertEqual(promedio([2, 4, 6]), 4)

            def test_maximo_con_negativos(self):
                self.assertEqual(maximo([-5, -2, -9]), -2)

            def test_es_par(self):
                self.assertTrue(es_par(4))
                self.assertFalse(es_par(7))


        if __name__ == "__main__":
            unittest.main()
    ''',
    "README.md": '''
        # Mini proyecto: calculadora

        Correr los tests con:

            python -m unittest -v
    ''',
}


def reset_workspace(workspace: Path = WORKSPACE) -> Path:
    """Borra y vuelve a crear el workspace con los archivos iniciales (con bugs)."""
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    for name, content in ARCHIVOS_INICIALES.items():
        (workspace / name).write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return workspace


def run_tests(workspace: Path = WORKSPACE) -> str:
    """Corre los tests del workspace y devuelve la salida (para verificar a mano)."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "-v"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.stderr + proc.stdout


if __name__ == "__main__":
    path = reset_workspace()
    print("Workspace reseteado en:", path)
    print(run_tests(path))
