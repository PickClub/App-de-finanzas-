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

## Etapa 2 — Lecturas implementadas, sin integrar el frontend

Disponibles `GET /api/transactions/page` y `GET /api/transactions/{tid}`.
`GET /api/transactions` conserva literalmente su implementación anterior y sus
consumidores siguen utilizándolo. El límite global y los seis defectos esperados
de etapa 1 permanecen; no deben retirarse esas regresiones todavía.

Parámetros de la nueva página: los descritos arriba. Varios tipos se solicitan
repitiendo `type`, por ejemplo `?type=expense&type=debt_payment`. El tamaño puede
cambiar entre páginas; filtros y orden deben conservarse. `start == end` devuelve
una ventana vacía; `start > end`, fecha sin zona, filtro inválido o cursor incompatible
devuelven 422. La ruta estática `/page` se registra antes de `/{tid}`.

Estrategia de compatibilidad sin migración: filtrar usuario, cuenta (ambos extremos
de transferencias), categoría y tipo mediante `find`; recorrer candidatos con cursor
Motor, normalizar instantes **solo para comparar en el servidor**, aplicar ventana
y cursor antes de conservar resultados. Mantener como máximo `limit + 1` documentos.
Ordenar con precisión de microsegundos; no sustituirlo por `$toDate` y asumir que
la precisión BSON en milisegundos conserva todos los empates históricos.
Los valores de `date` públicos y almacenados permanecen literales. Fechas sin zona
siguen la convención UTC de `_parse_dt`; esto no configura una zona financiera R9.

Historial candidato con fecha/identificador no verificable produce 409; no se omite
silenciosamente. Un empate de fecha e ID duplicado detectado en la selección también
produce 409. Los IDs deben ser únicos conforme al contrato de movimientos existente;
esta lectura no repara corrupción histórica ni crea un índice de unicidad.
El detalle devuelve 404 bajo el usuario efectivo o 409 si el ID tiene varios documentos.
Errores PyMongo de lectura devuelven 503 sin presentar una página vacía como éxito.
No se devuelve texto interno del driver. Se reutiliza el saneador financiero existente.

Cursor v1: JSON base64url canónico con versión, huella de consulta/contexto, instante
normalizado e ID. La huella incluye el usuario efectivo, filtros, orden y configuración
de destino del servidor (URI, base e identidad esperada, cuando existe). No se incluyen
credenciales ni URI en claro. Cambiar esa configuración invalida cursores; reiniciar con
la misma configuración los conserva. No es token de autenticación ni firma criptográfica:
un cursor manipulado no concede acceso, porque `user_id` se impone desde el servidor.
No pretende sustituir las cabeceras de contexto financiero de operaciones de pago.

Rendimiento: cada página recorre N candidatos, retiene O(limit) documentos y tiene
coste de selección O(N * limit) con límite máximo 100. No descarga el historial completo
al teléfono, pero no garantiza latencia constante en historiales grandes. No se activa
`allowDiskUse`, no hay `$out`/`$merge`, ni escrituras de consulta. Índices de selección
recomendados para evaluar después: `(user_id, account_id)`,
`(user_id, type, to_account_id)`, `(user_id, category_id)`, `(user_id, type)` y
`(user_id, id)` para el detalle y la verificación de identificadores.
No se han creado. Un índice textual sobre `date` no garantiza orden de instantes con
offsets mixtos. El salto a una fecha normalizada indexable requiere decisión separada
de esquema/compatibilidad; no realizar backfill automático.

Pruebas nuevas: `python3 -B -m unittest backend.tests.test_transaction_history -v`.
Ejecutan rutas reales extraídas por AST y el lector de producción mediante ASGI en
memoria; no importan el arranque de FastAPI ni abren MongoDB. Incluyen 501, 2.001 y
10.001 movimientos, ambos órdenes, offsets/microsegundos, filtros, seis tipos, cursores,
lectura directa, saneado y errores. Inserciones/ediciones se intercalan entre peticiones
sintéticas: no constituyen evidencia de concurrencia real o rendimiento en MongoDB.
Las pruebas financieras existentes se ejecutan aparte, sin cambiar sus flujos.


## Ampliación funcional del lector: importe, total y duplicados globales

GET /api/transactions/page acepta recent, oldest, high y low. recent/oldest
conservan el cursor v1 y su codificación exacta. high/low usan cursor v2, ligado
a filtros, contexto y orden, con importe Decimal textual, fecha normalizada e ID.
Se rechazan cursores cruzados entre órdenes o versiones sin reiniciar en silencio.

El orden global high es importe DESC, fecha DESC, ID DESC. low es importe ASC,
fecha DESC, ID DESC. Se compara Decimal sin convertir a float ni normalizar bajo
un contexto decimal que redondee. Decimal128 se lee mediante to_decimal. Valores
null/ausentes/vacíos conservan el fallback de orden cero; bool/no finitos/importe
ilegible producen 409 solo para high/low. Las lecturas cronológicas no introducen
rechazos nuevos por importe. No se cambian fuentes, fechas, tipos ni saldos.

La respuesta añade total: conteo de TODOS los candidatos que cumplen filtros,
antes del cursor, incluso en páginas posteriores o vacías. items/has_more/
next_cursor conservan sus nombres y significado. Decimal128 en amount se representa
como cadena decimal exacta en esta respuesta JSON; int, float y cadenas existentes
conservan su representación. No se cambia el listado legado ni lectura por ID.

Usuario/cuenta/categoría/tipo se filtran en find; fecha se compara con el parser
canónico antes de contar o seleccionar. Se recorre el conjunto candidato completo,
reteniendo como máximo limit+1 documentos, sin materializar un historial completo.
IDs físicos BSON heredados no se usan como identidad pública: el desempate y cursor
continúan usando id lógico string único por usuario. No se exige un _id string.

Se comprueba duplicación GLOBAL de id por user_id antes y después del recorrido
mediante match/group/match/limit/project; no se limita la entrada de group ni se
mantiene un conjunto ilimitado de IDs en Python. Fechas/cuentas/categorías distintas
no ocultan duplicados; otros usuarios no interfieren. La agregación no permite
disk spill y tiene maxTimeMS. Un duplicado produce 409, nunca deduplicación silenciosa.

Presupuestos por petición: 10 segundos de consulta completa, 100.000 documentos
candidatos recorridos y 32 MiB BSON procesados acumulados; find tiene batch_size=100
y max_time_ms, la agregación batchSize=1 y maxTimeMS. La selección nunca supera
limit+1 (limit máximo 100). El cierre de cada cursor se intenta con hasta 1 segundo
adicional. Agotamiento, timeout, error PyMongo/BSON o memoria de agregación excedida
produce 503 sin página parcial ni total etiquetado como completo. No se crean índices.
El group consume memoria del servidor sujeta al límite MongoDB sin spill; estos
presupuestos no equivalen a un límite exacto de RSS del proceso/driver ni de CPU.

Compleción y conteos son exactos para datos estables. Son lecturas de vista viva,
NO snapshot único: modificaciones durante o entre consultas pueden cambiar conteos,
orden o pertenencia; dos comprobaciones de duplicados no prueban ausencia de ABA.
No se promete recorrer una fotografía inmutable con los cursores. Reiniciar al
refrescar o cambiar filtros. El coste sigue siendo proporcional a candidatos por
petición, más agrupaciones globales; no se midió rendimiento MongoDB en esta etapa.

Quedan fuera páginas numeradas/salto arbitrario, integración frontend, totales de
Inicio/Informes/Presupuestos, índices, claves históricas persistidas y R9. No se
presentan sumas de páginas descargadas como totales financieros globales.

Validación offline:

```sh
python3 -B -m unittest backend.tests.test_transaction_history -q
```

Casos de cuatro órdenes y conteos con 501/2.001/10.001 movimientos, Decimal128 y
precisión más allá de float, empates, transferencias, filtros, IDs BSON físicos,
duplicados fuera de ventana/página, v1 exacto y v2 inválido, vacío y presupuestos.
El almacenamiento falso carece de métodos de escritura. No demuestra rendimiento
ni concurrencia real MongoDB; no se conecta a ninguna base para estas pruebas.
