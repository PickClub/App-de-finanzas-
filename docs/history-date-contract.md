# C3 + R9 — Etapa 1: contratos propuestos y regresiones

Esta etapa añade únicamente especificaciones y pruebas. Ningún endpoint,
formato persistido, índice, zona efectiva ni journal se activa o modifica.
Las rutas siguientes son propuestas para autorización posterior.

## Consulta paginada aditiva

Propuesta: `GET /api/transactions/page`. Conservar `GET /api/transactions`
y su respuesta de array para consumidores antiguos hasta su sustitución
explícita. Declarar la ruta estática antes de una futura ruta `/{tid}`.

Parámetros:

- `account_id`, `category_id`: identificadores exactos opcionales.
- `type`: uno o varios de los seis tipos financieros actuales. Las agrupaciones
  visuales de ingreso/gasto deben expandirse explícitamente, sin cambiar reglas.
- `start`, `end`: instantes ISO con zona, ventana semiabierta `[start, end)`.
- `limit`: 1–100, por defecto 50.
- `order`: `recent` o `oldest`; cursor y filtros deben conservar el mismo orden.
- `cursor`: token opaco versionado, validado y ligado a filtros, orden y contexto
  efectivo. Nunca confiar en un usuario aportado por el token como autenticación.

Filtrar usuario efectivo, cuenta, categoría, tipo y ventana **antes** del límite.
Cuenta participa por `account_id`, o por `to_account_id` únicamente si el
movimiento es transferencia. Una transferencia con ambos extremos iguales se
cuenta una sola vez. Nunca deduplicar pagos distintos por importe.

Orden total por **instante normalizado de `date` y `id`**, ambos descendentes
para `recent`, ambos ascendentes para `oldest`. Comparación estricta de la tupla
del último resultado; consultar `limit + 1` para calcular `has_more`.
Fechas ISO con offsets distintos no pueden ordenarse como texto suponiendo
que ese orden representa tiempo real. La estrategia de consulta/indexación
compatible con datos heredados es una decisión previa a implementación.

Respuesta propuesta:

```json
{"items": [], "next_cursor": null, "has_more": false}
```

No incluir metadatos de coordinación ni cápsulas financieras en `items`.
Cursor inválido o cambiado de filtros: 422 sin reinterpretarlo como primera
página. Error de lectura: error recuperable, nunca página vacía ficticia.

### Garantías y límites de concurrencia

La primera versión propuesta es **vista viva**, no snapshot del historial.
Un nuevo movimiento anterior al cursor no desplaza filas ya recorridas; aparece
al refrescar desde el principio. Uno posterior al cursor puede aparecer en páginas
siguientes. Editar fecha o filtros de un registro durante el recorrido puede
repetirlo u omitirlo; eliminarlo también cambia el conjunto. El frontend combina
por `id` para evitar filas repetidas, pero esto no recupera omisiones ni constituye
snapshot. Mostrar/refrescar el conjunto actual y reiniciar al cambiar filtros.

No prometer lectura inmutable por congelar `created_at`: no protege ediciones ni
eliminaciones. Snapshot estable o exportación coherente requiere otro diseño y
autorización, no transacciones abiertas durante la navegación del usuario.
Los tests simulan intercalaciones deterministas; no prueban concurrencia MongoDB.

Orden por importe (`high`/`low`) existente: no ordenar solo una página y
presentarla como orden global. Requiere contrato e índice/estrategia adicionales
antes de conectar esa opción de la pantalla, o aplazar su integración explícita.

## Detalle y totales

Propuesta: `GET /api/transactions/{tid}` busca directamente el ID bajo el usuario
efectivo, devuelve el documento público o 404. No depende de las primeras 500
filas. Mantener formas y protección de movimientos vinculados existentes.

Totales/resúmenes/informes deben aplicar el mismo filtro al conjunto completo,
sin límites 500, 2.000 o 20.000 ni sumas de páginas cargadas en el dispositivo.
Conservar los tipos, redondeos y reglas actuales. Pagos/recibos compartidos no
se suman de nuevo si representan un mismo movimiento; mark no es dinero.
El contador total, si se incorpora, necesita consulta agregada aparte y no debe
afirmarse consistente con todas las páginas de una vista viva concurrente.

## R9: semántica temporal propuesta

- **Día contable**: día de clasificación de un instante en la zona financiera
  efectiva, calculado para lecturas. No añadir ni reescribir un campo histórico.
- **Vencimiento/período/fecha objetivo**: `YYYY-MM-DD`, sin hora ni offset.
  Validar calendario real, incluidos bisiestos; mostrar desde componentes.
- **Instante**: ISO con hora y zona. Normalizar a UTC para nuevas escrituras
  únicamente tras autorización; representación original de intenciones/journals
  permanece literal. `created_at`/`updated_at` son instantes.

Propuesta pendiente: preferencia IANA estable del contexto single_user,
eventualmente por usuario cuando exista autenticación. Elegirla expresamente,
no inferirla del idioma, IP, URL o último dispositivo. MoneyFlow hoy utiliza
`default-user`; esto NO es autenticación ni habilita multiusuario.

No cambiar automáticamente la zona al viajar. Las ventanas de días/meses se
construyen en IANA y sus extremos se convierten por separado a UTC; no usar el
offset actual para ambos extremos de meses con DST. Días de calendario se
incrementan por componentes, no mediante `n * 86400000`.

Compatibilidad: conservar lectura de ISO con `Z` y offset explícito; hoy
`_parse_dt` trata instantes sin zona como UTC. No reinterpretarlos como hora
local. Conservar fechas sin hora como días donde el contrato del campo lo define.
Fechas inválidas o ambiguas no deben convertirse silenciosamente ni omitirse de
totales presentados como completos; definir error/diagnóstico antes de activar.
Clientes con `tz_offset` siguen compatibles hasta introducir una política explícita
de precedencia. No aplicar retrospectivamente una nueva zona a identidades de
períodos R4 ni cambiar programación histórica.

## Journals R4/R6

No recalcular fecha, vencimiento, ID, payload, contexto ni fingerprint al reabrir
o cambiar zona/fecha del dispositivo. Reintento reutiliza la representación exacta
original (incluido `date: null` si fue enviado). Las proyecciones de lectura se
normalizan por separado. Conciliación confirma identidad completa, no fecha cercana.
Las suites existentes de journal son parte obligatoria de esta etapa y de etapas
posteriores; no modificar su semántica para corregir visualizaciones de fechas.

## Evidencia y comandos

```sh
python3 -B -m unittest backend.tests.test_history_date_contract -v
node frontend/scripts/test-history-date-contract.cjs
node frontend/scripts/test-account-transactions.cjs
node frontend/scripts/test-obligation-payment-journal.cjs
node frontend/scripts/test-debt-payment-idempotency.cjs
node frontend/scripts/test-payment-journal-v2.cjs
node frontend/scripts/test-payment-flow-v2.cjs
node frontend/scripts/test-r6-final-safety.cjs
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
git diff --check
```

Python: modelo de contrato con 501/2.001/10.001 movimientos, filtros antes del
límite, transferencias, empates, inserciones/ediciones intercaladas, detalle/totales
y calendario. No demuestra que la API futura exista. Tres `expectedFailure`
estrictos ejecutan funciones actuales AST con almacenamiento en memoria: truncado
de cuenta, gasto mensual posterior a 2.000 y offset histórico incorrecto. Un
unexpected success obliga a reclasificar la prueba, no se acepta silenciosamente.
La extracción y ejecución se realizan en `setUp`, fuera del alcance de
`expectedFailure`: errores de preparación o ejecución fallan el CI normalmente.
Solo las tres aserciones del comportamiento pendiente se clasifican como esperadas.

Frontend: expresiones actuales mediante AST/transpilación y TZ en procesos
independientes. Tres defectos esperados en Chicago: hoy UTC, vencimiento mostrado
un día antes y ventana de siete días al cambiar a DST. Controles sanos en UTC,
Chicago y UTC+14. Fallos de infraestructura no se clasifican como defectos esperados.
Sin conexión HTTP, MongoDB, arranque de servicios ni escritura de almacenamiento.

## Etapa 2 recomendada

Autorizar primero consulta paginada y detalle backend aditivos con pruebas reales
en memoria. Antes de implementarlos, resolver normalización/indexación de `date`
heredada y orden por importe. No modificar pagos, journals, escrituras financieras,
pantallas ni zona persistida todavía. Índices persistentes y pruebas MongoDB requieren
autorización separada. La integración frontend y los agregados completos son etapas
posteriores: añadir paginación sola no cierra C3 ni R9.
