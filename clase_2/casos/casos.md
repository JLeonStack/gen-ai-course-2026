# Caso de estudio: F1 Fan Intelligence Assistant

## Contexto

Franco Colapinto generó una fuerte conversación pública en Argentina tras su vínculo con Alpine y su presencia en Buenos Aires en un evento de Fórmula 1.

La marca ficticia **Río Plate Sponsors** quiere aprovechar el momento para entender mejor qué dicen los fans, periodistas y potenciales sponsors.

Para eso contrata a **PitWall AI**, una startup argentina que desarrolla soluciones de inteligencia artificial para deportes, entretenimiento y marketing.

## Quiénes son ustedes

Ustedes son **Software Engineers en IA** en **PitWall AI**.

Su equipo debe construir un prototipo funcional usando la **OpenAI API con Python**.

El prototipo será usado por equipos de:

- marketing,
- soporte,
- prensa,
- sponsorship,
- reputación de marca.

## Problema

Después de un evento de Fórmula 1 en Buenos Aires, la marca recibe muchos mensajes desde redes sociales, email y formularios.

Los mensajes incluyen:

- fans consultando por merchandising,
- reclamos por accesos o entradas,
- periodistas pidiendo entrevistas,
- empresas interesadas en patrocinar,
- quejas públicas sobre la organización,
- comentarios positivos sobre Colapinto.

El equipo humano no puede revisar todo manualmente en tiempo real.

## Objetivo

Construir un sistema llamado:

**F1 Fan Intelligence Assistant**

El sistema debe leer mensajes, clasificarlos, priorizarlos y proponer una acción concreta.

---

## Dataset inicial

```python
mensajes = [
    {
        "id": "msg_001",
        "canal": "twitter",
        "texto": "Increíble ver a Colapinto en Palermo. ¿Van a vender merchandising oficial en Argentina?"
    },
    {
        "id": "msg_002",
        "canal": "email",
        "texto": "Compré dos entradas VIP para el evento y nunca me llegó el QR. Necesito ayuda urgente."
    },
    {
        "id": "msg_003",
        "canal": "instagram",
        "texto": "Soy periodista deportivo. Quiero coordinar una entrevista sobre el impacto de Colapinto en la F1."
    },
    {
        "id": "msg_004",
        "canal": "linkedin",
        "texto": "Represento a una fintech argentina interesada en patrocinar activaciones de F1 para jóvenes."
    },
    {
        "id": "msg_005",
        "canal": "twitter",
        "texto": "La organización fue un caos. Mucha gente, poca señalización y no se entendía por dónde entrar."
    }
]
```

## Lo que deben construir

Implementar una función principal:

```python
def analizar_mensajes(mensajes: list[dict]) -> list:
    ...
```

La función debe:

1. recorrer todos los mensajes,
2. clasificarlos usando OpenAI API,
3. validar la salida con Pydantic,
4. asignar prioridad,
5. recomendar una acción,
6. devolver datos estructurados.

## Modelo esperado

Crear un modelo Pydantic:

```python
from typing import Literal
from pydantic import BaseModel

class MensajeClasificado(BaseModel):
    id: str
    canal: str
    categoria: Literal[
        "fan_engagement",
        "soporte_evento",
        "prensa",
        "sponsorship",
        "reputacion",
        "otro"
    ]
    prioridad: Literal["baja", "media", "alta", "critica"]
    sentimiento: Literal["positivo", "neutral", "negativo"]
    resumen: str
    accion_recomendada: str
```

## Reglas de negocio

El sistema debe seguir estas reglas:

- Reclamos de entradas, QR, pagos o accesos → `soporte_evento`.
- Mensajes de periodistas → `prensa`.
- Propuestas comerciales o sponsors → `sponsorship`.
- Quejas públicas sobre organización o marca → `reputacion`.
- Fans contentos o consultas generales → `fan_engagement`.
- Si hay urgencia operativa → prioridad `alta` o `critica`.
- Si el mensaje puede escalar públicamente → prioridad mínima `alta`.

## Ejemplo de salida esperada

```json
[
  {
    "id": "msg_002",
    "canal": "email",
    "categoria": "soporte_evento",
    "prioridad": "alta",
    "sentimiento": "negativo",
    "resumen": "El usuario compró entradas VIP pero no recibió el QR.",
    "accion_recomendada": "Escalar a soporte_eventos y responder con prioridad dentro del SLA."
  }
]
```


## Requisito técnico 1: OpenAI API

Usar `client.responses.create()` o `client.responses.parse()`.

Recomendado:

- usar `responses.parse()` para salida estructurada,
- usar Pydantic para validar,
- no parsear JSON manualmente si no es necesario.

## Requisito técnico 2: Instrucciones

El modelo debe recibir instrucciones claras.

Ejemplo:

```python
instructions = '''
Sos un asistente de inteligencia para eventos deportivos.
Clasificá mensajes relacionados con Fórmula 1, Colapinto, Alpine y sponsors.
No inventes datos.
Devolvé una salida estructurada según el esquema indicado.
'''
```

## Requisito técnico 3: Function calling

Implementar al menos una función externa.

Ejemplo:

```python
def buscar_estado_ticket(id_mensaje: str):
    tickets = {
        "msg_002": {
            "estado": "abierto",
            "equipo": "soporte_eventos",
            "sla_horas": 2
        }
    }

    return tickets.get(
        id_mensaje,
        {
            "estado": "no_creado",
            "equipo": None,
            "sla_horas": None
        }
    )
```

Uso esperado:

- Si el mensaje es de soporte, consultar estado del ticket.
- Si no existe ticket, recomendar crear uno.
- Si existe ticket abierto, incluir SLA en la acción recomendada.

## Requisito técnico 4: Manejo de errores

Agregar manejo básico de errores.

El sistema debe contemplar:

- error de API,
- respuesta inválida,
- mensaje vacío,
- categoría no esperada,
- reintentos simples.

## Entregables

Cada equipo debe entregar:

1. notebook funcionando,
2. modelo Pydantic,
3. función `analizar_mensajes`,
4. ejemplo de function calling,
5. manejo básico de errores,
6. output estructurado,
7. resumen ejecutivo,
8. propuesta breve de arquitectura.

## Resultado esperado

Al finalizar, el equipo debe tener un prototipo capaz de convertir mensajes desordenados en información accionable para un equipo real de marketing, prensa y operaciones.
