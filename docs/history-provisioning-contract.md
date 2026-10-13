# C3 — Contrato administrativo de provisionamiento histórico, versión 1

Estado: documentación y modelo OFFLINE. No es una herramienta operativa ni una
migración. No conecta a MongoDB, no ejecuta provisionamiento y no habilita controles.
Producción conserva sus escritores actuales; R4, escritura de claves y lecturas
indexadas permanecen desactivados. Los 23 experimentales anteriores no se modifican.

La autoridad técnica es `backend/history_keys.py`, versión 1, y su parser canónico
C3. La introducción histórica de `history-keys-contract.md` describe una etapa
anterior: actualmente existe mantenimiento funcional, pero esto no demuestra
cobertura del historial almacenado. No duplicar el parser experimental P2.

## Cuatro operaciones independientes

| Operación | Efecto permitido | Resultado |
|---|---|---|
| diagnose | Leer ámbito completo, sin escrituras | Informe por estados y plan propuesto; no certificación de una vista viva |
| apply | Bajo nueva autorización, modificar solo `_history_keys` y bitácora administrativa propia | Confirmación por documento o incertidumbre/conflicto |
| verify | Leer y recalcular cobertura íntegra | Certificado condicionado, o bloqueo de lectores indexados |
| revert | Bajo nueva autorización, restaurar solo el bloque privado anterior o quitarlo | Reversión por documento, conflicto o incertidumbre |

Ninguna operación invoca endpoints financieros, modifica balances, recibos,
obligaciones o journals R4/R6. El modelo solo transforma copias sintéticas en
memoria; no es evidencia de transacciones reales. `apply` no ejecuta `diagnose`,
`verify` ni `revert` automáticamente. Revertir no autoriza volver a pagar.

## Autorización y destino vinculantes

Una autorización externa verificable debe aprobar explícitamente:

- Operación, `run_id`, revisión completa del código, versión 1 y generación
  positiva BSON int32 (1–2147483647; bool no permitido).
- URI efectiva, topología/deployment esperado y base exacta. Credenciales se
  obtienen mediante un proveedor protegido, nunca por argumento/log/manifiesto.
  No guardar hash de contraseñas como identificador público del destino.
- Colección exacta y UUID físico BSON Binary subtipo 4. Una colección reemplazada
  con el mismo nombre invalida el plan; no aceptar solo nombre/namespace.
- UUID financiero R6 fijado independientemente del destino, metadata R6 válida,
  identidad efectiva `single_user/default-user` y configuración efectiva del
  servidor. No descubrir el pin confiando en una copia de la base.
- Ámbito: en este contrato, todos los movimientos del usuario efectivo dentro de
  esa colección, sin filtros por fecha/importe/tipo. Un ámbito parcial futuro
  requiere otro contrato y jamás certifica el historial global.
- Reemplazos concretos de bloques obsoletos, corruptos o incompatibles, si se
  autorizan; presupuesto de lotes, política de pausa y ventana de escritores.

Revalidar destino, UUID de colección, R6, usuario y alcance al abrir la operación,
al reanudar y dentro de cada transacción de modificación. PRIMARY, sesiones,
transacciones, readConcern snapshot y writeConcern majority serán precondiciones
operativas de apply/revert; no usar fallback sin transacciones. Errores de lectura
o metadatos ausentes bloquean, nunca equivalen a colección vacía.

El modelo comprueba pins y metadata R6 con sus validadores puros existentes;
recibe observaciones sintéticas. No verifica un PRIMARY real ni autentica la
aprobación humana. `approved=True` es un fixture, no un control de acceso.
La identidad default-user tampoco autentica: una herramienta operativa requiere
acceso administrativo real, aislado de los endpoints públicos.

## Diagnose: recorrido y clasificación

El adaptador futuro debe recorrer un cursor MongoDB de solo lectura ordenado por
`_id` físico con colación simple, nunca por fecha/importe editables. Conservar el
checkpoint como BSON de un único valor `_id`, con tipo/subtipo intactos y enlace
al destino, scope, revisión, versión/generación. Prohibir coerción JSON de Int64.

Limitar cada lote por número de documentos **y** bytes BSON; incluir el coste del
buffer del driver y fijar un límite de manifiesto. Un documento superior al límite
no se omite silenciosamente: pausa/bloqueo con código de incidencia. El límite no
se resuelve reduciendo campos necesarios para comparar el original.

Checkpoint es avance de diagnóstico, no evidencia de que los documentos anteriores
sigan intactos. BSON tipos admitidos inicialmente: ObjectId, string, int32, Int64
y Binary. Otras identidades físicas requieren detenerse y ampliar pruebas; no
inferir un orden Python para imitar MongoDB. El modelo toma un iterador ordenado
por el futuro adaptador, no implementa ese cursor ni un reanudador real.

Informe mínimo: conteos `missing`, `ready`, `unverifiable`, `incompatible`,
`stale_or_corrupt`, identidad inválida y duplicados, último checkpoint protegido,
referencia no secreta del destino y errores por código. Una identidad lógica
`(user_id,id)` repetida bloquea certificación: dos pagos legítimos con diferentes
IDs no se deduplican por fecha o importe.

La detección exacta de duplicados requiere almacenamiento externo acotado de
huellas/identificadores protegidos o una estrategia de lectura verificada; no un
set ilimitado en RAM ni un filtro probabilístico que certifique ausencia. El set
del modelo es únicamente un oráculo de fixtures pequeños. No crear índices ni
colecciones auxiliares en esta etapa. Su diseño operativo necesitará autorización.

### Historial incompatible

- `ready` exacto, versión/generación aprobadas: no requiere aplicación.
- `missing` con derivación ready: candidato de un plan revisado.
- `stale_or_corrupt` o `incompatible`: registrar y exigir aprobación específica
  del reemplazo del bloque. Nunca convertir automáticamente generación o versión.
- Fuentes no verificables: no alterar la fecha/importe/identidad. En esta etapa el
  modelo no permite aplicar ni siquiera una nueva marca unverifiable; diagnostica
  las existentes y bloquea certificación. Marcar esos históricos necesitará una
  autorización separada, sin habilitar lecturas que los omitan.
- Falta/null/cadena vacía del importe mantiene el fallback de orden del contrato
  canónico, no demuestra validez financiera ni autoriza corregir el importe.

Conservar ISO extendido, básico y semana, offsets con segundos, microsegundos y
la interpretación UTC actual de fechas sin zona. No introducir R9 ni normalizar
las cadenas fuente. Decimal128 se conserva exacto; fingerprint diferencia BSON
int32/Int64/double/string/Decimal128 y campo ausente/null. El runtime/parser debe
ser el mismo validado al producir y verificar una generación.

## Apply: plan y comparación concurrente

Plan inmutable por documento: autorización vinculante, `_id` BSON tipado,
`source_sha256` aprobado, presencia/valor BSON exactos del bloque anterior,
bloque nuevo derivado y sello determinista de todos esos campos. El sello protege
contra cambios accidentales; **no es firma de autorización ni autenticación**.
La aprobación externa debe fijar también el digest del plan completo y el scope.

Dentro de una transacción corta:

1. Revalidar destino/autorización; releer el documento por `_id` y usuario.
2. Comparar fingerprint de las cuatro fuentes canónicas con el plan aprobado.
   La comparación conserva ausencia, null y representación BSON; no basta la
   igualdad numérica MongoDB (1, Int64(1) y 1.0 tienen huellas diferentes).
3. Comparar presencia y bytes BSON del bloque anterior; recalcular el nuevo
   mediante el módulo compartido a partir del documento vigente.
4. Hacer solo `$set: {_history_keys: bloque}` y registrar evidencia administrativa
   en la misma transacción/sesión. Nunca reemplazar el movimiento entero.
5. Confirmar con majority; persistir checkpoint de aplicación después de la
   confirmación/evidencia, no solo después de enviar la escritura.

La lectura dentro de la transacción y la escritura del mismo documento permiten
que MongoDB detecte una escritura intermedia. Conflicto transitorio requiere
relectura y comparación de todo el plan; no aprobación del estado nuevo de forma
implícita. Una edición administrativa anterior a esa lectura puede preservarse
si las fuentes/bloque no cambiaron. Una edición concurrente después provoca
conflicto transaccional; nunca usar una copia exterior para sobrescribirla.

Antes de escribir, comprobar también unicidad lógica y requisitos de integridad
identificados por el diagnóstico aprobado. No planificar duplicados ni fuentes
ambiguas. El modelo no es un validador integral de referencias financieras R3/R4.

## Manifiesto y bitácora propios

Esquema lógico del manifiesto protegido:

- `contract_version`, `run_id`, operación, digest de autorización/plan, revisión
  de código y runtime/parser, version/generation de claves, scope exacto.
- Deployment no secreto/base/colección/UUID, environment_id R6/usuario efectivos.
- Límites de lotes, checkpoints BSON tipados, conteos por estado y cobertura.
- Por documento: referencia física protegida, fingerprint fuente, presencia/valor
  anterior del bloque, bloque posterior aprobado, sello y eventos de estado.

Estados: **preparado** (sin prueba de commit), **confirmado** (registro atómico
majority), **incierto** (confirmación desconocida), **conflicto** (plan no coincide;
no autoriza cambios), **revertido** (registro atómico de reversión). Distinguir
estado local incierto del estado servidor confirmado; una respuesta perdida no
cambia por sí misma el estado financiero. Conflictos no eliminan la evidencia.

Bitácora administrativa futura separada de journals R4/R6, con unicidad de
`(run_id,_id BSON tipado)`, destino/plan/fingerprint, bloques previo/posterior,
resultado y evidencia de control de escritores. Movimiento y registro confirmado
se publican juntos; reversión y marca revertido también. Su colección e índice
requerirán autorización independiente: no están creados ni provisionados ahora.

Commit incierto: consultar la misma entrada, mismo destino y mismo sello con
lectura majority coherente. Coincidencia íntegra confirma la aplicación original,
no garantiza que las claves actuales sigan vigentes. Entrada ausente sigue
incierta hasta descartar una transacción en vuelo; no repetir con otro run_id ni
inferir rollback. Sin evidencia suficiente, conservar bloqueo y detenerse.
El modelo simula publicación atómica y fallos antes/después; no modela red,
replicación, elección PRIMARY ni transacciones aún en vuelo.

No almacenar URI con credenciales, documentos financieros completos, journals
financieros, saldos o payloads de pagos. El bloque anterior corrupto podría
contener información sensible: tratarlo como material protegido, nunca imprimirlo.
Guardar manifiestos/bitácoras fuera de Git, con acceso mínimo, cifrado, integridad,
retención aprobada y respaldo; los ejemplos aquí son sintéticos. No crear archivos
reales de ejecución ni configurar exclusiones en esta etapa. Los informes
compartibles solo incluyen conteos y códigos; checkpoints/IDs también son privados.

## Revert: propiedad y ausencia de escrituras intermedias

Primero desactivar/bloquear los lectores indexados. Revertir exige autorización
específica y prueba de una ventana exclusiva **continua** desde apply hasta revert,
incluyendo escritores externos/restauraciones. Comparar destino, journal, fuentes,
metadatos actuales y pertenencia a la ejecución; devolver el bloque anterior con
su representación literal, o `$unset` si estaba ausente. No convertir null a
ausente ni reconstruir un bloque corrupto.

No recrear movimientos eliminados; no restaurar campos financieros ni documentos
completos. Una nueva transacción actualiza exclusivamente bloque y registro propio.
Fallo parcial/commit incierto se concilia igual que apply, sin dobles reversiones.

**Problema ABA:** claves deterministas iguales no demuestran que nadie escribió
entre medias. Ni fingerprint ni `_reference_revision` garantizan propiedad de las
claves. El modelo dispone de un contador total de escrituras del fixture para
reproducir este problema; tal contador **no existe** en el esquema de producción.
Sin exclusión operacional verificable de todos los escritores, bloquear reversión
automática, aunque los valores actuales coincidan. Abrir una nueva ventana no
prueba ausencia de cambios durante el intervalo previo. No añadir un marcador de
propiedad al movimiento ni modificar escritores financieros en este contrato.

## Verify y condiciones de certificado

Releer **todo el ámbito**, recalcular cada bloque y detectar duplicados, errores,
fuentes inválidas, incompatibilidad/versiones/generaciones, claves missing,
unverifiable o stale. No certificar solo páginas devueltas por un índice ni
consultar únicamente `state=ready`: eso invisibiliza registros excluidos.

Certificar únicamente con:

- Identidad y colección verificadas, alcance completo y recorrido final terminado.
- Ventana sin escritores demostrada durante toda la verificación; no prometer
  snapshot global por usar varias transacciones snapshot cortas.
- Todos los escritores posteriores autorizados mantienen la misma versión y
  generación; escritores externos deshabilitados o controlados/verificables.
- Cero inconsistencias/duplicados/error de lectura; runtime compatible.

Una inserción con `_id` menor que el checkpoint, eliminación o edición durante una
vista viva puede invalidar el recorrido: reanudar checkpoint no resuelve cobertura.
Después de períodos con mantenimiento desactivado, repetir verificación íntegra.
Certificado debe expirar/inutilizarse ante cambio de destino/UUID/generación,
escritores, configuración, restauración de backup o incidente de integridad.

Cualquier incumplimiento mantiene **bloqueada** la lectura indexada; no mezclar
ready con registros omitidos ni devolver un conteo parcial como total. El modelo
solo calcula ese veredicto; no existe una integración nueva de lectores ni una
activación. El certificado tampoco acredita integridad de saldos o autenticación.

## Pruebas y límites de esta etapa

Ejecutar:

`python3 -B -m unittest backend.experiments.test_c3_history_provision_contract -v`

Casos: clasificación, formatos heredados/Decimal128, BSON tipado, duplicados,
límites por documentos/bytes, autorización/R6/destino/UUID, comparación concurrente,
planes alterados, fallos parciales, confirmación incierta y reanudación por documento,
reversión de ausencia/null/corrupción, ABA, eliminación, campos financieros idénticos
y saneamiento recursivo. No importar server.py, no leer .env ni abrir clientes.

El modelo llama al código puro de claves y validadores R6; no duplica sus reglas.
Las pruebas offline no demuestran compare-and-set real, majority, índices,
latencia, consumo del driver, almacenamiento protegido ni exclusión de escritores.

## Próximo prototipo autorizado por separado

1. Implementar solo un adaptador **diagnose** read-only, con pin externo/autorización,
   `listCollections` UUID, R6, observación administrativa PRIMARY/sesiones,
   proyección suficiente, límites de red/bytes, checkpoints BSON y cancelación.
2. Probar con fixtures falsos primero; diseñar detección exacta de duplicados y
   manifiesto protegidos sin RAM proporcional a todo el historial.
3. Solicitar autorización independiente antes de conectar a una base sintética
   nueva. Nunca reutilizar bases financieras ni experimentales previas.
4. Validar inserciones/ediciones durante recorrido, reanudación y cambio de contexto.
5. Medir memoria máxima, bytes de red, latencia por lote y crecimiento del informe.
6. Solo después diseñar/probar apply + journal, revert y certificación bajo ventana
   de escritores. Ningún provisionamiento real, índice o activación queda autorizado.

Riesgos pendientes: escaneo O(N), detección exacta de duplicados, volumen de bitácora,
16 MB BSON al añadir claves, cobertura tras reinicios, prueba externa de exclusión,
escritores fuera del repositorio y seguridad de manifiestos. Un lote pequeño no
implica latencia baja ni coste total acotado. No se inventan mediciones MongoDB.

## Evidencia offline de esta entrega

Ejecución final: 184 pruebas, 178 aprobadas y seis fallos históricos esperados,
sin fallos nuevos. Las 38 pruebas nuevas del contrato administrativo pasan.
Las restantes 146 cubren módulo público/claves (44), lector C3 (12), contrato
C3/R9 (13) y experimentos offline anteriores (77). Los seis expected failures
corresponden a los tres defectos históricos C3/R9 y las tres discrepancias del
parser experimental P2 conservado; no se eliminaron ni reclasificaron aquí.

No se ejecutaron pruebas MongoDB, benchmarks, operaciones financieras ni pruebas
físicas. Esta evidencia habilita revisar el contrato, no ejecutar provisionamiento
ni activar índices/lectores. Verificación SHA-256 de todos los archivos anteriores:
sin cambios; solo este documento y los dos archivos offline administrativos nuevos.
