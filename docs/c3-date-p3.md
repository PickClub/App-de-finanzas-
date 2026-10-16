# C3 P3 — Equivalencia estricta offline, no integración MongoDB

Rama `conflict_280926_1750`, HEAD `1ca9972b748dee2ebf613fef1bea7b89e5537b4f`.
Se conservaron byte por byte los 14 archivos P1/P2. No se consultó ninguna base,
no se crearon bases/índices y no se modificó código funcional, frontend o configuración.

## Referencia exacta

El lector C3 actual utiliza `backend/transaction_history.py:parse_instant(value,
stored=True)`: exige cadena no vacía, aplica `value.replace("Z", "+00:00")`, llama a
`datetime.fromisoformat`, atribuye UTC a fechas sin zona y convierte a UTC las
que tienen zona. Errores de interpretación/overflow producen HTTP 409.

`backend/server.py:_parse_dt` emplea el mismo primitivo para cadenas, pero acepta
`str(value)`, conserva el offset original y devuelve None ante error. Las pruebas
extraen esa función real mediante AST, sin ejecutar arranque ni conexión a MongoDB,
y comparan instantes válidos de cadenas después de convertirlos a UTC. No se cambian
esas diferencias entre contratos; P3 tiene el contrato del **lector C3**.

## Causa de los tres defectos P2

1. Separadores de fecha opcionales e independientes en PATTERN admiten
   `2026-1001T120000Z`, aunque `fromisoformat` lo rechaza.
2. Separadores de hora opcionales e independientes admiten
   `2026-10-01T12:0000Z`, también rechazado por la referencia.
3. La regex P2 reconoce fechas gregorianas; no incluye fechas ISO de semana.
   `2026-W40-4T12:00:00Z` es válido y equivale a `2026-10-01T12:00:00Z`.

Se reprodujeron otra vez las tres discrepancias con las pruebas offline originales
P2. No se alteraron sus expected failures ni sus informes históricos MongoDB.

## Solución experimental y límite de alcance

`backend/experiments/c3_date_p3.py` reutiliza directamente el parser canónico C3.
No mantiene una segunda gramática ni intenta corregir fechas. Deriva una clave
entera UTC de microsegundos por aritmética de timedelta, sin timestamp float ni
reducción a milisegundos. Devuelve un objeto inmutable separado con texto original,
instante y clave; nunca añade campos al documento original ni guarda claves.

La equivalencia de interpretación está garantizada **por reutilización del parser**,
no por demostrar que otro parser independiente acepta exactamente su lenguaje.
Las pruebas verifican la adaptación a la clave, precisión, orden y manejo de errores.
Solo se usa el parser instalado en este entorno; no se prueba compatibilidad entre
versiones diferentes de Python. Una arquitectura futura deberá versionar semántica
y detectar cambios de runtime/parser antes de materializar o reutilizar claves.

**No es una corrección de la agregación MongoDB P2.** Sus archivos permanecen intactos
y su parser conserva los tres defectos documentados. Usar la equivalencia P3 en una
arquitectura indexada necesitaría aprobar un productor de claves con el parser
canónico, su mantenimiento transaccional y una política de historial. Una solución
exclusivamente de agregación seguiría necesitando un parser MongoDB equivalente
demostrado. No se ofrece fallback silencioso ni se adopta esa arquitectura aquí.

## Evidencia ejecutada ahora

- P3: 26 pruebas aprobadas, cero fallos esperados.
- Los 18 escenarios P2 se reprodujeron **offline**, incluyendo 14 fechas y cuatro
  escenarios de filtros/transferencias. Los tres escenarios denominados baseline,
  optimized y stored_keys comprueban sus entradas con el adaptador en memoria;
  **no vuelven a ejecutar aquellos tres planes MongoDB**.
- Ocho pruebas adicionales: reproducción P2/corrección P3; semana ISO y cambio de
  año; epoch negativa/offsets/microsegundos; límites e inválidos; orden relativo;
  conservación literal de documentos/cápsulas; fallo conservador de candidatos
  inválidos; 1.800 comparaciones generadas con semilla fija (300 fechas × 6 formatos).
- Regresiones offline P1/P2: 17 pruebas, 14 aprobadas y 3 fallos esperados P2,
  conservados porque aquellos archivos no fueron modificados.

Casos relevantes:

| Entrada | Resultado P3 |
|---|---|
| `2026-1001T120000Z` | HTTP 409, sin normalizar a otro formato |
| `2026-10-01T12:0000Z` | HTTP 409 |
| `2026-W40-4T12:00:00Z` | `2026-10-01T12:00:00+00:00` |
| `20261001T120000Z` | Mismo instante que ISO extendido |
| `2026-10-01T12:00:00.123456+01:02:03` | `2026-10-01T10:57:57.123456+00:00` |
| `1969-12-31T23:59:59.999999Z` | Clave -1, sin pérdida de precisión |
| `2020-W53-5` / `2020W535` | `2021-01-01` bajo la convención UTC existente |
| `2021-W53-1` | HTTP 409, semana 53 inválida |

Un candidato inválido no se omite silenciosamente. Dos registros con el mismo
instante conservan sus IDs distintos; la clave temporal no deduplica pagos.
El texto histórico y los payloads de intención permanecen literales. `date: null`
de un journal no se trata como fecha de un movimiento ni se sustituye por "hoy".
No se cambió el significado de vencimientos o días contables; R9 sigue pendiente.

La compilación AST de la función de referencia se cachea solo dentro de la prueba
para no repetir análisis de server.py en cada comparación. No es una caché de datos
financieros ni un benchmark de latencia de consultas.

## Riesgos y siguientes decisiones

APTO para equivalencia del **adaptador Python experimental**. NO APTO para declarar
resuelta la integración MongoDB o habilitar claves indexadas de producción.

Pendientes antes de esa arquitectura:

- Mantener claves de fecha/importe y versiones de forma atómica al crear/editar,
  sin alterar reglas C4/R1/R2/R3/R4/R6 ni payloads de recuperación.
- Resolver el tratamiento de documentos antiguos/invalidables sin repararlos ni
  migrarlos automáticamente; no hay autorización de backfill.
- Fijar versionado de parser/runtime y política de invalidación de claves.
- Conservar conteos coherentes y limitaciones de la vista viva y del cursor.
- Medir el plan que realmente se autorice; no trasladar resultados de P2 como si
  correspondieran a P3. La normalización Python cambia el lugar del trabajo si se
  conecta al sistema, pero P3 no lo ha conectado ni implementa ese plan.

No se repitieron benchmarks masivos: no hay consultas MongoDB ni plan nuevo que
medir en esta etapa. Si se exige equivalencia íntegra dentro de MongoDB sin un
productor canónico, ese bloqueo permanece y requiere diseño/validación aparte.

## Archivos y comandos

Nuevos: `backend/experiments/c3_date_p3.py`,
`backend/experiments/test_c3_date_p3.py`,
`backend/experiments/results/c3_date_p3_offline.json` y este documento.

```sh
python3 -B -m unittest backend.experiments.test_c3_date_p3 -v
python3 -B -m unittest backend.experiments.test_c3_numbered_prototype backend.experiments.test_c3_numbered_p2 -v
git diff --check
```

El informe offline registra runtime, huellas de parsers y resultados; no contiene
credenciales o datos reales. Sin staging, commit, push, índices ni activación R4.
