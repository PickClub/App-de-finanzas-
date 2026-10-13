# C3 — Modelo offline conservador de provisionamiento

Bloque 4B: planificación inmutable y validación de precondiciones únicamente.
No hay MongoClient, endpoint, CLI operativa, acceso a MongoDB, almacenamiento,
bitácora, APPLY, REVERT, índices ni activación. Los experimentos no se importan.
Este modelo no autoriza provisionamiento real ni certifica información financiera.

## Entrada y cobertura

`build_plan(reader, target, run_id, T, limits=Limits())` recibe un adaptador de
fixtures offline que cumple el protocolo de lectura del diagnóstico registrado.
No acepta un informe previo como sustituto del inventario, recorrido físico,
flujo global de duplicados y verificación final de identidad a un mismo T.
Las atestaciones del adaptador falso son un contrato de pruebas, no evidencia
operativa sobre un servidor o una colección real.

Target conserva destino local aprobado, base/colección/UUID físicos, UUID R6,
usuario efectivo, versión y generación. run_id es UUID v4 canónico explícito.
Su aprobación es exclusivamente de diagnóstico; nunca aprobación de APPLY.
`default-user` identifica el ámbito efectivo single_user del servidor, no una
identidad humana autenticada ni un permiso multiusuario.

El modelo reutiliza run_diagnosis, derive_history_keys y source_fingerprint;
la inspección canónica inspect_history_keys ocurre en run_diagnosis. No duplica
el parser ni modifica fechas, precisión, importes, identificadores o journals.

## Plan e intenciones inmutables

Plan contiene run_id, vínculo de destino, T, versión/generación, alcance completo,
estado, cobertura, conteos, duplicados, fuentes no verificables e intenciones.
Conteos e intenciones son tuplas; cada intención conserva `_id` físico como BSON
tipado inmutable, huella de las cuatro fuentes, precondición de campo ausente y
propuesta privada codificada como BSON. No hay coerción JSON de IDs/Decimal128.
El plan no conserva el documento financiero completo ni las fuentes literales.

El digest SHA-256 determinista incluye contexto, ejecución, T, estado, conteos,
intenciones en orden físico y sus precondiciones. Cambiar versión/generación,
destino, ejecución, T o contenido cambia el digest. No es firma, autenticación
ni autorización: alguien con el contenido puede calcular otro digest.
Los valores de intenciones son material privado; no imprimirlos ni persistirlos.

## Política de candidatos

| Situación | Resultado |
|---|---|
| `_history_keys` realmente ausente y derivación ready | Candidato |
| ready exacto | Sin intención de modificación |
| Campo existente null, objeto vacío u otra representación | Bloqueo, nunca tratar como ausencia |
| stale_or_corrupt, incompatible o unverifiable | Bloqueo sin reemplazo |
| Fuentes que no permiten derivación canónica ready | Bloqueo sin corregir fuentes |
| Duplicados lógicos, incluso con fechas diferentes | Bloqueo de todo el ámbito |
| `_id` físico no admitido, identidad inválida o cobertura no acreditada | Aborto/incompletitud |

Importe ausente/null/cadena vacía mantiene el fallback de orden del contrato
canónico: puede derivar cero ready, con huellas diferentes. Esto no declara
válido un importe financiero ni permite repararlo. No introducir aquí nuevas
reglas de negocio o validación de pagos. Integridad de claves y corrección del
documento financiero siguen siendo afirmaciones distintas.

Una colección vacía es completa únicamente después de terminar todos los pasos
del protocolo. Un presupuesto excedido invalida completitud. Un plan bloqueado,
incompleto o abortado descarta las intenciones capturadas y nunca es elegible.
Ningún plan devuelve apply_authorized=true o revert_authorized=true.

## Precondiciones de futura ejecución

`validate_intent(plan, intent, current, target)` es una comparación pura:

1. Comprobar integridad estructural y digest del plan completo.
2. Exigir el mismo vínculo de destino/UUID/R6/usuario/versión/generación.
3. Comprobar pertenencia de la intención y `_id` con su representación BSON.
4. Comparar fingerprint de id, user_id, date y amount, incluyendo ausente/null y
   tipos BSON. La igualdad numérica o de instantes no sustituye esta comparación.
5. Exigir que `_history_keys` siga ausente; incluso un bloque posterior idéntico
   es conflicto, no confirmación de esta ejecución.
6. Derivar nuevamente y comparar el bloque exacto.

`preconditions_match` no autoriza escribir, no acredita unicidad lógica actual,
no demuestra ausencia de ABA y no hace vigente el plan después de T. Una futura
transacción deberá releer y validar controles operativos bajo autorización aparte.
La verificación del digest completo debe organizarse una vez por ejecución en
un adaptador futuro: este modelo no promete rendimiento de validación masiva.

Cambios en fuentes invalidan precondiciones. Cambios en name/notes/revisión se
identifican como administrativos y se conservan; no se escribe ningún campo.
`classify_changes` identifica otros cambios por separado: cuenta, tipo y campos
desconocidos no se declaran administrativos ni financieros inocuos por defecto.
Su relación con reglas operativas futuras requiere revisión independiente.

## Idempotencia y reversión: solo contratos

ReceiptContract es evidencia suministrada por un fixture; no un journal o una
transacción simulada. Compara ejecución, contexto, plan e intención. Coincidencia
con estado confirmed produce original_confirmation, no confirmación financiera
real ni prueba de vigencia de claves actuales. Ausencia/uncertain permanece
uncertain; contradicciones producen conflict. Nunca generar otra clave para salir
de incertidumbre. No hay cambios de estado persistidos o modificaciones de datos.

`reversal_status` siempre bloquea por falta de evidencia operativa de escritores.
Igualdad de fuentes, claves deterministas o recibo coincidente no prueban que
nadie escribió entre medias. Se prueba ABA sin declarar una reversión segura.
El contador del modelo experimental no se traslada como garantía de producción.
No se agrega procedencia a `_history_keys`, cuya forma canónica permanece exacta.

## Recursos e informes

Se conservan límites máximos de diagnóstico: 100 documentos/1 MiB por respuesta,
10.000 documentos, 32 MiB procesados, 10.000 respuestas y 30 segundos. Se admite
reducirlos en fixtures, no ampliarlos. Bytes del plan y BSON del recorrido se
comprueban conjuntamente antes de declarar completitud; las intenciones tienen
además un presupuesto independiente durante captura. Memoria nativa y objetos
Python no equivalen a los bytes BSON contabilizados ni tienen garantía de RSS.
No hay set ilimitado de IDs: el diagnóstico verifica duplicados en flujo ordenado,
y el plan retiene únicamente intenciones dentro de sus presupuestos.

public_report devuelve solo contexto vinculado, T, digest, conteos, número de
candidatos/duplicados, estado y códigos. No devuelve IDs, fuentes, bloques,
importes, fechas de movimientos, URI ni secretos. Siempre financial_correctness_asserted,
certificate_issued e indexed_reads_allowed son false.

## Pruebas y siguiente paso

```bash
python3 -B -m unittest backend.tests.test_history_provisioning -v
```

Fixtures BSON pequeños; sin conexiones, archivos persistentes ni escrituras.
Antes de APPLY/REVERT quedan pendientes autorización operativa, almacenamiento
protegido del plan, bitácora propia, exclusión de escritores/DDL, transacciones,
conciliación de commits inciertos y validación sintética independiente. No aceptar
una comprobación offline como autorización o certificación de datos reales.
