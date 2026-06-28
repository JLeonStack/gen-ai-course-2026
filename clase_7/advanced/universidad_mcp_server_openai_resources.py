from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

mcp = FastMCP(
    name="universidad-mcp",
    instructions=(
        "Servidor MCP educativo para una clase introductoria. "
        "Expone herramientas, recursos y prompts de una universidad ficticia. "
        "Las acciones de alto impacto deben producir borradores y requerir aprobación humana."
    ),
)

ALUMNOS: dict[str, dict[str, Any]] = {
    "A001": {
        "nombre": "Ana Torres",
        "carrera": "Ingeniería Informática",
        "email": "ana.torres@example.edu",
        "notas": [8, 9, 7],
        "entregas": {"TP1": True, "TP2": False, "TP3": True},
    },
    "A002": {
        "nombre": "Bruno López",
        "carrera": "Ingeniería Informática",
        "email": "bruno.lopez@example.edu",
        "notas": [6, 5, 7],
        "entregas": {"TP1": True, "TP2": True, "TP3": False},
    },
    "A003": {
        "nombre": "Carla Méndez",
        "carrera": "Ingeniería en Inteligencia Artificial",
        "email": "carla.mendez@example.edu",
        "notas": [10, 9, 10],
        "entregas": {"TP1": True, "TP2": True, "TP3": True},
    },
    "A004": {
        "nombre": "Diego Ruiz",
        "carrera": "Ingeniería Informática",
        "email": "diego.ruiz@example.edu",
        "notas": [3, 4, 5],
        "entregas": {"TP1": False, "TP2": False, "TP3": False},
    },
}

PROGRAMA_IA_GENERATIVA = {
    "materia": "IA Generativa",
    "codigo": "IA-402",
    "objetivos": [
        "Entender cómo se construyen aplicaciones con modelos de lenguaje.",
        "Diseñar herramientas, prompts y flujos de evaluación.",
        "Construir prototipos con APIs, RAG y MCP.",
    ],
    "unidades": [
        "Fundamentos de LLMs",
        "Prompting y evaluación",
        "RAG",
        "Agentes",
        "Model Context Protocol",
    ],
}

CALENDARIO_EXAMENES_2026 = {
    "parcial_1": "2026-05-12",
    "parcial_2": "2026-06-23",
    "recuperatorio": "2026-07-07",
    "entrega_final": "2026-07-14",
}

REGLAMENTO_APROBACION = """
# Reglamento simplificado de aprobación

Este documento es un recurso de lectura para la demo MCP.

## Condiciones

- La materia se aprueba con promedio final mayor o igual a 4.
- El estudiante debe tener al menos el 75% de asistencia.
- El estudiante debe entregar al menos 2 de los 3 trabajos prácticos.
- Si el promedio es menor a 4, el estudiante debe recuperar.
- Si adeuda más de un trabajo práctico, el equipo docente debe enviar un recordatorio personalizado.

## Reglas de comunicación

- Los recordatorios deben ser claros, respetuosos y accionables.
- No se deben enviar mails automáticos sin revisión humana.
- El asistente puede preparar borradores, pero una persona debe aprobar el envío.
""".strip()

RUBRICAS = {
    "TP1": {
        "criterios": [
            {"criterio": "claridad", "peso": 0.25},
            {"criterio": "corrección técnica", "peso": 0.35},
            {"criterio": "justificación", "peso": 0.20},
            {"criterio": "presentación", "peso": 0.20},
        ],
        "escala": "0 a 10",
    },
    "TP2": {
        "criterios": [
            {"criterio": "diseño de tools", "peso": 0.30},
            {"criterio": "validaciones", "peso": 0.25},
            {"criterio": "uso de resources", "peso": 0.25},
            {"criterio": "criterio de seguridad", "peso": 0.20},
        ],
        "escala": "0 a 10",
    },
    "TP3": {
        "criterios": [
            {"criterio": "integración con LLM", "peso": 0.30},
            {"criterio": "manejo de errores", "peso": 0.25},
            {"criterio": "experiencia de usuario", "peso": 0.25},
            {"criterio": "documentación", "peso": 0.20},
        ],
        "escala": "0 a 10",
    },
}


@mcp.tool
def buscar_alumno(legajo: str) -> dict[str, Any]:
    """
    Busca un alumno por legajo.

    Args:
        legajo: Identificador del alumno. Ejemplo: "A001".

    Returns:
        Datos públicos del alumno para la demo, incluyendo notas.
    """
    alumno = ALUMNOS.get(legajo)

    if alumno is None:
        return {
            "encontrado": False,
            "legajo": legajo,
            "mensaje": "No existe un alumno con ese legajo.",
        }

    return {
        "encontrado": True,
        "legajo": legajo,
        "nombre": alumno["nombre"],
        "carrera": alumno["carrera"],
        "email": alumno["email"],
        "notas": alumno["notas"],
        "entregas": alumno["entregas"],
    }


@mcp.tool
def calcular_promedio(notas: list[float]) -> dict[str, Any]:
    """
    Calcula el promedio de una lista de notas entre 0 y 10.

    Args:
        notas: Lista de notas numéricas. Ejemplo: [8, 7.5, 9].

    Returns:
        Promedio, cantidad de notas y estado de aprobación.
    """
    if not notas:
        raise ValueError("La lista de notas no puede estar vacía.")

    for nota in notas:
        if nota < 0 or nota > 10:
            raise ValueError("Todas las notas deben estar entre 0 y 10.")

    promedio = round(sum(notas) / len(notas), 2)

    return {
        "promedio": promedio,
        "cantidad_notas": len(notas),
        "estado": "aprobado" if promedio >= 4 else "desaprobado",
    }


@mcp.tool
def buscar_entregas_pendientes(materia: str, trabajo: str) -> dict[str, Any]:
    """
    Busca estudiantes que no entregaron un trabajo práctico.

    Args:
        materia: Nombre de la materia. En esta demo usar "IA Generativa".
        trabajo: Nombre del trabajo. Ejemplo: "TP2".

    Returns:
        Lista de estudiantes con entrega pendiente.
    """
    if materia.lower() != "ia generativa":
        raise ValueError("Esta demo solo tiene datos de la materia 'IA Generativa'.")

    pendientes = []

    for legajo, alumno in ALUMNOS.items():
        entrego = alumno["entregas"].get(trabajo)

        if entrego is False:
            pendientes.append(
                {
                    "legajo": legajo,
                    "nombre": alumno["nombre"],
                    "email": alumno["email"],
                }
            )

    return {
        "materia": materia,
        "trabajo": trabajo,
        "cantidad_pendientes": len(pendientes),
        "pendientes": pendientes,
    }


@mcp.tool
def crear_borrador_recordatorio_entrega(
    materia: str,
    trabajo: str,
    destinatarios: list[str],
    mensaje_base: str = "Les recordamos que tienen una entrega pendiente.",
) -> dict[str, Any]:
    """
    Crea un borrador de recordatorio de entrega. No envía emails.

    Esta tool está diseñada como una acción segura: prepara el texto,
    pero requiere revisión y aprobación humana antes de enviar.

    Args:
        materia: Nombre de la materia.
        trabajo: Nombre del trabajo pendiente.
        destinatarios: Lista de emails destinatarios.
        mensaje_base: Mensaje inicial para incluir en el borrador.

    Returns:
        Borrador listo para revisión humana.
    """
    if not destinatarios:
        raise ValueError("Debe haber al menos un destinatario.")

    asunto = f"Recordatorio de entrega pendiente: {trabajo} - {materia}"

    cuerpo = f"""Hola,

{mensaje_base}

Materia: {materia}
Trabajo: {trabajo}

Por favor, revisen la consigna y avísennos si tienen alguna dificultad.

Saludos,
Equipo docente
"""

    return {
        "tipo": "borrador",
        "requiere_aprobacion_humana": True,
        "asunto": asunto,
        "destinatarios": destinatarios,
        "cuerpo": cuerpo,
        "advertencia": "Este borrador NO fue enviado. Debe revisarlo una persona.",
    }


@mcp.resource(
    "programa://materias/{materia_slug}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def programa_materia(materia_slug: str) -> str:
    """
    Devuelve el programa de una materia.

    Args:
        materia_slug: Slug de la materia. Para esta demo usar "ia-generativa".
    """
    if materia_slug != "ia-generativa":
        raise ValueError("Materia no disponible en esta demo.")

    return json.dumps(PROGRAMA_IA_GENERATIVA, ensure_ascii=False, indent=2)


@mcp.resource(
    "calendario://examenes/2026",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def calendario_examenes_2026() -> str:
    """Devuelve el calendario de exámenes 2026."""
    return json.dumps(CALENDARIO_EXAMENES_2026, ensure_ascii=False, indent=2)


@mcp.resource(
    "reglamento://aprobacion",
    mime_type="text/markdown",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def reglamento_aprobacion() -> str:
    """Devuelve el reglamento simplificado de aprobación de la materia."""
    return REGLAMENTO_APROBACION


@mcp.resource(
    "rubrica://trabajos/{trabajo}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def rubrica_trabajo(trabajo: str) -> str:
    """
    Devuelve la rúbrica de evaluación de un trabajo práctico.

    Args:
        trabajo: Nombre del trabajo. Ejemplo: "TP2".
    """
    rubrica = RUBRICAS.get(trabajo.upper())

    if rubrica is None:
        raise ValueError(f"No hay rúbrica disponible para {trabajo}.")

    return json.dumps(
        {
            "trabajo": trabajo.upper(),
            **rubrica,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.prompt
def feedback_entrega_tp(
    nombre_estudiante: str,
    trabajo: str,
    observaciones: str,
    tono: str = "cercano, claro y riguroso",
) -> str:
    """
    Genera una plantilla de feedback para una entrega práctica.

    Args:
        nombre_estudiante: Nombre del estudiante.
        trabajo: Nombre del trabajo práctico.
        observaciones: Observaciones principales sobre la entrega.
        tono: Tono deseado para el feedback.
    """
    return f"""
Redactá feedback para {nombre_estudiante} sobre la entrega {trabajo}.

Tono: {tono}

Observaciones:
{observaciones}

Estructura obligatoria:
1. Empezá reconociendo algo positivo.
2. Señalá los problemas técnicos principales.
3. Explicá por qué esos problemas importan.
4. Proponé próximos pasos concretos.
5. Cerrá con una frase motivadora.
""".strip()


if __name__ == "__main__":
    mcp.run()
