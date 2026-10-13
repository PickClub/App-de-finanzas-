# C3 — Etapa 2: diagnóstico histórico BSON offline

Prototipo aislado de lectura. No incluye MongoClient, Motor, CLI conectable,
lectura de .env, archivos de ejecución persistentes ni operaciones apply/revert.
No modifica el contrato anterior ni los 23 experimentales previos. No cambia
backend funcional, frontend, journals o controles de activación.

## Entradas y contrato

`SyntheticBsonSource(documents, observation, revision=0, fixture_bytes=8388608)`
recibe un iterable de **documentos BSON sintéticos codificados**. Los copia como
bytes inmutables, comprueba `_id` y los ordena para simular un lector. Es un
oráculo pequeño de memoria, no un sustituto escalable de MongoDB. Límite de
fixture configurable hacia abajo, máximo 8 MiB de BSON; la memoria Python total
incluye envoltorios y ordenamiento, por lo que no se afirma un máximo RSS de 8 MiB.

`diagnose_bson(auth, source, token=None, max_documents=100, max_bytes=1048576,
max_batches=None)` devuelve dos objetos independientes:

1. Informe agregado compartible, sin fechas, importes, IDs, fingerprint por
   documento, URI, entorno o documentos financieros.
2. Checkpoint BSON **privado**, sin escribirlo a disco ni registrarlo en logs.

Reutiliza `derive_history_keys`, `inspect_history_keys` y `source_fingerprint` de
producción, y `Authorization.check('diagnose', observation)` del contrato offline.
No invoca el ledger de aplicación/reversión del contrato anterior. No crea una
bitácora administrativa ni un plan de escritura.

## Validación del destino

Se exige aprobación explícita para diagnose, scope `entire_effective_user`,
run_id, revisión de código, versión 1 y generación positiva BSON int32.
La observación debe coincidir con el destino aprobado: URI sintética, base,
colección, UUID físico Binary subtipo 4, UUID financiero R6 y usuario efectivo
`default-user`. Los validadores puros existentes comprueban metadata R6.

Revalidar antes de cada lote y después de leerlo. Reanudar con otro run_id,
revisión, generación, contexto o colección bloquea. Documento fuera del usuario
esperado también bloquea: el proveedor futuro debe filtrar por usuario efectivo
antes del recorrido, no presentar registros ajenos al diagnosticador.

No se comprueba topología real, PRIMARY ni acceso administrativo: todo proviene
del fixture. Los booleanos de autorización/exclusión no son controles de acceso.
`single_user/default-user` sigue sin autenticar al usuario. Una herramienta real
necesitará pins externos, permisos administrativos y protección de credenciales.

## Clasificación sin reparaciones

Conteos por estado almacenado:

- missing: bloque ausente.
- ready: bloque exacto de versión/generación aprobadas.
- stale_or_corrupt: bloque de versión/generación actuales que no coincide.
- unverifiable: marca vigente cuyo contenido coincide con derivación no verificable.
- incompatible: bloque inválido o versión/generación incompatible.

Además: número de fuentes no verificables, identidades lógicas inválidas y
bloques de generación incompatible. Así, una fila missing con fecha inválida
sigue missing pero informa fuente no verificable; no queda oculta ni se repara.

Preserva fechas ISO extendidas, básicas, de semana, offsets con segundos y
microsegundos, y Decimal128 conforme al parser canónico. Diferencia ausencia,
null e int32/Int64/double/string/Decimal128 sin normalización financiera.
El generador puede usar cero como fallback de orden cuando el importe no está
presente; eso no acredita validez financiera ni autorización para corregirlo.

Duplicados se detectan por huella BSON de `(user_id,id)`, sin usar importe/fecha.
Dos movimientos iguales con IDs diferentes siguen siendo dos movimientos.
Se conserva un conjunto de hasta **2.048 huellas** entre lotes/reanudaciones.
Superar el límite bloquea con `duplicate_detection_limit`, sin declarar cobertura
completa. SHA-256 no es autenticación ni una prueba matemática sin colisiones;
una futura detección exacta a gran escala requiere almacenamiento externo
protegido o una estrategia de lectura adicional autorizada. No se crea ahora.

## Orden físico, lotes y checkpoints

Orden simple por `_id` físico, no por `id` lógico, fecha o importe:

- int32 e Int64 por valor numérico; valores iguales no pueden ser dos identidades
  físicas distintas en este modelo.
- strings por UTF-8, con colación simple.
- Binary por longitud, subtipo y bytes.
- ObjectId por sus bytes.
- Entre esos tipos: números, strings, Binary, ObjectId.

Es un subconjunto explícito del orden BSON. Bool, null, double, objetos y arrays
como `_id` se rechazan; no extrapolar a todos los tipos MongoDB ni a colaciones
personalizadas. PyMongo decodifica Binary subtipo 0 como bytes: el prototipo
restaura únicamente su envoltorio de checkpoint, con idéntica codificación BSON.
No transforma documentos almacenados ni campos financieros.

Cada lote: máximo configurable de documentos (tope 1.000) y bytes BSON (tope
4 MiB). Valores booleanos, cero y negativos se rechazan. Un documento demasiado
grande pausa con error, nunca se omite. Se comprueba también el lote devuelto por
el proveedor: orden creciente, presupuesto y progreso cuando declara más datos.
`max_batches` permite devolver avance parcial controlado.

El checkpoint contiene versión propia, binding de autorización, último `_id`
BSON tipado, conteos acumulados, huellas de duplicados, revisión inicial del
fixture, ventana inicial de escritores y estado completado. No contiene las
fechas/importes/documentos fuente. El `_id` y las huellas siguen siendo información
privada; nunca incluir el token en el informe público ni en Git.

El envoltorio BSON tiene checksum SHA-256, esquema validado y tope de **256 KiB**.
Detecta truncado/corrupción accidental y vinculación incorrecta; no está firmado
ni autoriza recibir checkpoints de terceros. Este prototipo trabaja con evidencia
interna confiable. Un adaptador operativo requerirá autenticidad/almacenamiento
protegido o rediagnóstico, nunca confiar en un checksum como firma.

Reanudar consulta solo `_id` posteriores y preserva el resto del estado. Un error
no publica checkpoint nuevo: reutilizar el último token devuelto exitosamente.
Un token completado devuelve los mismos conteos sin volver a sumar filas; no
supone que el historial actual siga igual. Para un nuevo diagnóstico completo,
comenzar sin token bajo autorización/alcance correspondientes.

## Vista viva frente a control de escritores

En vista viva los conteos representan **filas visitadas**, no una instantánea del
historial actual. Inserciones anteriores al checkpoint pueden quedar sin visitar;
ediciones/eliminaciones de filas visitadas dejan sus conteos anteriores. La
revisión simulada permite señalar `source_changed`; el modelo no ofrece un
snapshot global ni corrige esos conteos. Incluso sin detectar cambios, una vista
viva no es certificable.

Si el fixture declara una ventana exclusiva, reanudación y lotes exigen la misma
ventana, escritores detenidos y revisión inicial sin cambios. Una ventana nueva
no subsana el intervalo anterior. Solo tras agotar el recorrido, todos los
bloques ready, sin duplicados/identidades inválidas y con escritores posteriores
compatibles, el informe indica `certification_eligible_in_fixture=true`.

**Siempre** devuelve `certified=false` e `indexed_reads_allowed=false`.
`evidence=offline_synthetic` deja explícita la naturaleza de la prueba. Ninguna
observación sintética certifica una colección financiera ni habilita un lector.
El contador/revisión de fixtures no existe como garantía en producción.

## Pruebas y ejecución

`python3 -B -m unittest backend.experiments.test_c3_history_diagnosis_offline -v`

39 pruebas: cinco estados, generación/versión, fuentes no verificables, fechas
heredadas/Decimal128, tipos BSON, duplicados entre lotes y reanudaciones, orden
físico mixto, límites por documentos/bytes/memoria, errores BSON, tokens inválidos,
contexto/UUID/autorización, 2.001 filas, fallos de lectura, respuestas fuera de
orden, inserciones/ediciones/eliminaciones simuladas, ventana exclusiva y ausencia
de fuentes en informes. Comparan BSON antes/después para asegurar solo lectura.

La primera ejecución detectó el Binary subtipo 0 decodificado como bytes y una
expectativa sobre el tipo de BSON.encode. Se corrigió únicamente la representación
del nuevo prototipo, preservando su codificación BSON; los casos mixtos pasan.
No se cambió el contrato anterior ni ningún archivo funcional.

## Requisitos antes de un lector MongoDB

- Autorizar por separado destino/pins y conexión solo a base sintética nueva.
- Verificar read-only, UUID físico con listCollections, R6 y usuario efectivo.
- Implementar orden/reanudación en el servidor respetando tipos BSON mixtos;
  comprobar equivalencia real y no trasladar comparaciones Python sin pruebas.
- Acotar buffers del driver y red, cancelación, tiempos de espera y errores;
  medir memoria/latencia. Este prototipo no contiene mediciones MongoDB.
- Resolver detección exacta de duplicados a gran escala y protección del checkpoint
  sin nuevos índices/bitácoras persistentes hasta obtener autorización.
- Probar concurrencia sin un contador global ficticio; no certificar vistas vivas.
- Diseñar evidencia operacional de exclusión de todos los escritores externos e
  internos y recorrer de nuevo todo el ámbito para cualquier certificado real.
- Mantener bloqueadas lecturas indexadas ante cualquier error/cobertura desconocida.

No queda autorizado provisionamiento, apply/revert, migración, índices, cambios
financieros ni activación por terminar este prototipo.

## Resultado de validación de esta entrega

Ejecución conjunta: 223 pruebas, 217 aprobadas y seis fallos históricos esperados,
sin regresiones nuevas. Desglose: 39 pruebas nuevas y 184 del contrato administrativo,
claves/saneamiento, lector C3 y regresiones offline anteriores. Los seis fallos
esperados siguen siendo los tres C3/R9 y las tres discrepancias conservadas de P2.
Sintaxis, análisis de operaciones restringidas y comprobaciones de whitespace:
aprobados. No hubo MongoDB, benchmarks, datos reales ni certificados operativos.
