---
description: Procedimiento para encontrar y arreglar bugs en código Python con tests que fallan.
---

1. Corré `run_tests` y anotá qué tests fallan y con qué mensaje.
2. Para cada test que falla, leé el test y la función que prueba.
3. Explicá en una línea cuál es el bug antes de tocar el código.
4. Hacé el cambio mínimo que lo arregla. No reescribas funciones enteras si no hace falta.
5. Volvé a correr `run_tests`. Repetí hasta que pasen todos.
6. Revisá casos borde que los tests no cubren (lista vacía, un solo elemento, negativos) y mencionalos en el resumen.
