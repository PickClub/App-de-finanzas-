# C3 — Consistencia, reanudación y certificación: diseño offline

No se conecta a MongoDB ni se modifica infraestructura. Las 17 pruebas MongoDB
previas son evidencia histórica: esta etapa no las repite. Replica set local
8.0.32 previamente verificado; parámetros actuales, retención efectiva y nuevas
garantías de snapshot no se comprobaron ahora contra el servidor.

## Garantías verificadas en documentación primaria

MongoDB 8.0 admite `find` y `aggregate` con readConcern snapshot fuera de una
transacción. Puede fijarse `atClusterTime` para leer el mismo instante; fuera de
transacciones esos datos son majority-committed. No usar una sesión causal con
atClusterTime. Si el instante ya no está retenido, la lectura falla; no elegir
otro T para continuar el mismo informe.
[MongoDB 8.0 snapshot](https://www.mongodb.com/docs/v8.0/reference/read-concern-snapshot/).

PyMongo documenta sesiones `snapshot=True`: el primer read fija el timestamp y
los siguientes lo reutilizan. Esa sesión no se serializa como un cursor durable.
Para reanudar después de perder el proceso se propone un nuevo read con el mismo
T explícito y filtro/checkpoint, condicionado a que el servidor aún lo soporte;
la API de comandos, captura del T y continuidad deben validarse realmente.
[PyMongo ClientSession](https://pymongo.readthedocs.io/en/stable/api/pymongo/client_session.html).

La retención mínima configurada por defecto es 300 segundos; solicitar un instante
antiguo puede producir SnapshotTooOld. Incrementarla aumenta uso de disco.
Es un parámetro de servidor, no una reserva durable por checkpoint. El límite
real de la instalación puede diferir y no se asume que 300 s garantice completar
un recorrido/reanudación.
[Parámetro MongoDB 8.0](https://www.mongodb.com/docs/v8.0/reference/parameters/#mongodb-parameter-param.minSnapshotHistoryWindowInSeconds).

Una transacción tiene por defecto duración inferior a un minuto y puede abortarse;
la presión de WiredTiger exige cuidado. No se propone mantener una transacción
financiera compartida abierta para un diagnóstico largo.
[Consideraciones de producción](https://www.mongodb.com/docs/v8.0/core/transactions-production-consideration/).

La expiración de sesión puede cerrar cursores incluso con noCursorTimeout. La
documentación indica 30 minutos de inactividad; refrescar sesión/cursor no extiende
por sí solo la retención del snapshot ni garantiza sobrevivir a reinicios.
[Sesiones y cursores](https://www.mongodb.com/docs/v8.0/reference/method/cursor.nocursortimeout/).

Conclusión documental: hay un mecanismo soportado para un punto temporal común,
pero **no** un snapshot perpetuo y reanudable indefinidamente. Majority aislado,
HMAC, generaciones o dos recorridos iguales no lo sustituyen.

## Comparación de arquitecturas

| Estrategia | Garantía | Escrituras de la aplicación | Reanudación | Coste y viabilidad local |
|---|---|---|---|---|
| A: exploración viva | Conteos de filas visitadas, sin instantánea | Continúan; pueden omitir inserciones previas al checkpoint y cambiar filas visitadas | Checkpoint tipado; informe siempre exploratorio | Baja sobrecarga de retención; scans/sort pueden impactar. Ya probado sintéticamente |
| B: snapshot común T | Todos los pasos a T, si cada read mantiene la garantía | Continúan sin mantenimiento exclusivo; no aparecen sus efectos posteriores a T | Mismo T, pins y checkpoint; abortar si deja de estar disponible | Historial/versiones, IO/cache y sort. Documentado en 8.0; pendiente de prueba real |
| C: copia consistente aislada | Vista fija de un origen/T o backup acreditado | Continúan tras captura; no afectan al análisis de copia | Duradera mientras copia/manifest permanezcan inmutables | Duplica datos sensibles/almacenamiento y coste de copia. No está provisionada ni probada |

### A — Explorar sin certificar

Usar particiones tipadas, inventario exhaustivo y duplicados streaming del diseño
anterior. Presupuesto de tiempo/bytes/documentos y cancelación. El cliente no
carga el historial entero; ordenar IDs lógicos sigue teniendo coste de servidor.
Con allowDiskUse=false, exceso de memoria bloquea, nunca crea un índice/fallback.

Estado exploratorio tanto con pocos como muchos resultados. Datos nuevos antes
del checkpoint, cambios de tipo físico/contexto o eliminaciones pueden invalidar
conteos acumulados. Reportar alcance visitado/error, sin afirmar salud completa.
No usarlo para habilitar lecturas indexadas ni autorizar provisionamiento.

### B — Snapshot común fuera de transacción: preferido para siguiente prueba

Capturar el T confirmado de la primera lectura snapshot mediante respuesta/API
soportada; no inventarlo con la fecha del dispositivo ni usar automáticamente un
clusterTime ajeno como si fuese el snapshot realmente seleccionado. Fijar ese
BSON Timestamp en todas las particiones, inventario, validación de fuentes,
conteos y paso de duplicados. Cada nuevo find/aggregate debe leer el mismo T;
getMore continúa el cursor original. Nuevas sesiones sin T no equivalen a retomarlo.

Si se usan comandos explícitos, controlar que cada paso envíe snapshot+T. No
reutilizar sesiones de payment_transaction ni añadir transacciones anidadas.
No realizar escrituras ni commits financieros. Sesiones/cursores se liberan al
terminar/abortar. Mantener read-only, maxTimeMS, deadlines y presupuestos explícitos.

Pins de destino y R6 actuales verifican dónde opera el administrador; metadata R6
leída al mismo T identifica la vista. UUID físico/DDL no se deduce de una lectura
histórica de documentos: controlar cambios de colección y revalidar identidad.
Si no puede probarse que el namespace corresponde a la colección aprobada,
abortar. Probar rename/drop/recreate solo en futuras bases nuevas autorizadas.

Cualquier SnapshotTooOld, cursor no recuperable, retención desconocida, error de
lectura/sort o cambio de identidad interrumpe el informe. Se conserva evidencia
incompleta y se inicia otra ejecución/T, sin sumar datos de ambas. Una firma válida
no obliga al servidor a conservar T.

La aplicación puede escribir, pero la historia de versiones y los scans compiten
por recursos. Programar fuera de picos, medir cache/IO y cancelar ante presupuesto;
no aumentar retención ni deshabilitar spill por cambios de configuración en esta
etapa. La viabilidad observada de un scan de ~7 s no demuestra snapshot soportado
ni garantiza margen de retención para historiales grandes.

Una transacción read-only corta puede servir de comparación en pruebas. No es
la opción principal para recorridos largos ni reanudación de un proceso perdido;
reiniciar una transacción produce otra vista si no existe mecanismo validado.

### C — Copia consistente e inmutable para análisis largo

Origen: backup compatible y acreditado, exportación completa bajo un snapshot
común verificable o captura con escritores controlados. Una copia hecha fila a
fila en vivo no es consistente. No copiar un volumen activo a mano ni atribuir
consistencia a un dump normal mientras se escribía.

MongoDB documenta mongodump con oplog y replay como mecanismo para replica sets;
requiere dump completo, no admite limitarlo con --db/--collection/--query. No
proponer ese comando contra el contenedor actual bajo permiso de una sola base:
podría copiar otras bases y datos sensibles. Necesitaría autorización separada
para todo su alcance, o una alternativa de captura limitada y demostrada.
[Documentación mongodump](https://www.mongodb.com/docs/database-tools/mongodump/).

Manifest de copia: procedencia, T/ventana y mecanismo, scope exacto, identidades
R6/UUID origen y destino, integridad/digests, herramientas/runtime, captura completa
y validación. Una restauración puede asignar otro UUID: vincular explícitamente
ambos, no aceptar los tokens del origen como autorización de otra base.

Aislar acceso, impedir escritores en la copia, cifrar almacenamiento y transporte,
retención/borrado solo autorizado, nunca Git. La copia conserva todos los datos
sensibles y representa un nuevo riesgo de exposición. Análisis con usuario
read-only y control de DDL; si copia/manifest cambia, abortar. Su costo incluye
almacenamiento de datos, índices existentes y captura/restauración, aunque el
cliente procese lotes. No se crea infraestructura ni copia ahora.

## Generaciones y detección de cambios: controles complementarios

Generación etiqueta claves, no versiones completas de movimientos. Una fila
modificada puede conservar generación; fuentes nuevas sin claves no se vuelven
visibles por consultar solo ready. Mantener flags no prueba cobertura histórica.

Recontar o repetir un hash detecta algunos cambios, pero hay inserciones/eliminaciones
compensadas y estados ABA. Sin una vista común, igualdad de resultados no prueba
que los pasos observaron un único instante. Change streams/resume tokens podrían
ayudar a detectar cambios, pero retención, eventos, bootstrap y escritores externos
necesitan otra arquitectura; no se implementan ni se consideran prueba suficiente.

## HMAC persistente: solo diseño

No se añade gestión de claves ni persistencia. Propuesta de almacén administrativo
externo protegido con actualización atómica del último digest/secuencia por run_id,
fuera de MongoDB financiero y Git. Persistir evidencia de lotes terminados antes
de emitir avance recuperable; un proceso perdido no autoriza avanzar al lote que
no fue confirmado en el manifest. No guardar documentos completos ni saldos.

Payload firmado: formato/algoritmo/key_id, run_id, destino fijado sin credenciales,
R6/usuario, base/UUID físico, scope, versión/generación/parser/revisión, política
de tipos/colación, partición/_id tipado, conteos, pasos terminados, consistencia,
T BSON Timestamp o digest de copia, timestamps de emisión/caducidad y secuencia.
Un digest de datos no sustituye identidad del deployment/colección.

Clave aleatoria >=256 bits en proveedor de secretos con permisos mínimos, nunca
.env nuevo, argumentos, resultados o tokens. HMAC autentica evidencia del emisor,
no al usuario de MoneyFlow ni al estado del servidor; tokens siguen siendo privados
porque HMAC no cifra. Añadir cifrado si se almacenan IDs/metadatos sensibles.

Rotación: key_id explícito; nueva clave para nuevos runs, verificación de anteriores
solo durante una ventana autorizada. Revocación/compromiso obliga a rechazar esos
tokens y rediagnosticar; no volver a firmar sin comprobar progreso/consistencia.
Un restart puede reanudar solo con manifest y clave verificables, pins iguales,
misma política y T disponible/copia intacta. Si falta evidencia, abortar.

Caducidad de token y snapshot son independientes. El cliente usa deadline
conservador; aunque no haya caducado el token, el servidor puede rechazar T.
Nunca extender automáticamente la expiración del snapshot al rotar claves o
renovar token. Copias tienen retención aprobada y checks de inmutabilidad.

## Estados y política de certificación

- exploratorio: vista viva, nunca certificable aunque todo aparezca ready.
- incompleto: faltan pasos/lotes, diagnóstico suspendido o evidencia pendiente.
- consistente: recorrido completo del mismo T/copia y evidencia de scope válida;
  puede describir defectos de forma fiable sin declarar claves sanas.
- certificable: además, condiciones de integridad/coverage aprobadas satisfechas.
- abortado: identidad/caducidad/recursos/checkpoint/integridad del recorrido fallan;
  no se continúa con otra vista dentro del mismo run.

Evidencia requerida: autorización y pins; inventario de tipos completo; todas las
particiones agotadas, conteos concordantes a T/copia; fuentes/fingerprints y BSON
literal verificados; duplicados e identidades inválidas ausentes; runtime/parser/
version/generación compatibles; pasos sin errores, manifest íntegro y reproducible.

missing, stale_or_corrupt, incompatible o unverifiable hacen que un informe estable
pueda ser consistente **pero no apto para lectura indexada**. No reparar ni ocultar
esas filas. Separar certificado de completitud del diagnóstico de declaración de
salud del historial. Reportar conteos, reason codes y contexto opaco, no fechas,
importes, IDs, credenciales, fuentes ni excepciones con documentos.

Un certificado snapshot acredita solo el ámbito **a T**. No garantiza el presente
ni filas insertadas después. Activar un lector actual exigiría procedimiento
independiente de cobertura vigente y todos los escritores mantenidos/controlados,
incluidos externos; ante intervalo sin control, nueva verificación. Ningún estado
del modelo activa flags ni emite certificados operativos.

## Infraestructura y pruebas todavía pendientes

Replica local es candidato a probar B porque ya es MongoDB 8.0 en replica set;
no implica snapshot verificado. Futuras pruebas exclusivamente en base sintética
nueva: T común entre inventario/particiones/duplicados, escritura concurrente,
getMore y reanudación tras proceso perdido, SnapshotTooOld real, elecciones/restarts,
DDL, errores sort, recursos, cancelación y reportes. No cambiar parámetros sin permiso.

Medir retención efectiva, latencia/IO/cache/RSS independientes y capacidad de terminar
con margen. Certificación de una copia exige probar captura/replay/proveniencia y
permisos read-only bajo autorización propia. Almacén durable de HMAC/manifests tampoco
existe; necesita alcance, permisos, respaldo, retención y pruebas de caída.

Recomendación: siguiente validación B acotada y sintética; A para exploración
explícita sin certificados; C como alternativa para recorridos mayores a retención.
No bloquear globalmente la aplicación para B ni detener escritores automáticamente.
Si no existe retención/copia suficiente, informar incompleto/abortado, no simular éxito.

## Modelo offline y evidencia

Nuevo `backend/experiments/test_c3_diagnosis_consistency_policy.py`: política pura y
fixtures BSON congelados. Evidencia de HMAC/retención se inyecta como booleanos;
no implementa criptografía persistente ni un snapshot real. No carga server.py,
clientes, .env o bases de datos. El set de identidades es un oráculo pequeño, no
la futura solución escalable de duplicados.

24 pruebas: inserciones previas/posteriores, ediciones/eliminaciones, reanudación,
caducidad, contexto/UUID/política, claves rotadas, evidencia manipulada, IDs mixtos,
duplicados y estados heredados, límites y reportes. Demuestran política, no garantías
del servidor ante una caída real. Los experimentos y archivos anteriores permanecen
intactos; esta etapa solo crea este documento y ese archivo offline.

Verificación final de esta etapa: 124 pruebas offline aprobadas (24 nuevas y 100
regresiones de diseño/diagnóstico/contrato administrativo), sin fallos. No se
repitieron suites financieras generales, benchmarks ni pruebas MongoDB. Sintaxis
y whitespace comprobados. No staging, commit, push, conexión o activación.
