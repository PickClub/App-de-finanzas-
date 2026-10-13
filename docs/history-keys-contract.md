# C3 — Contrato propuesto de claves privadas, versión 1

Estado: documentación y modelo ejecutable OFFLINE. No existe integración de
producción, provisionamiento, índice, migración ni activación. R4 permanece
desactivado. P1/P2/P3 se conservan intactos. P3 no corrigió el parser MongoDB P2;
no reutilizar ese parser para generar estas claves.

## Fuentes y forma exacta

Propuesta de bloque embebido `_history_keys` en el movimiento, nunca en el
payload del cliente, en recibos ni en journals. Se deriva del documento efectivo
final, después de aplicar las reglas existentes sobre campos omitidos/explicitos.

`ready` contiene exactamente:

- `version`: entero 1, nunca booleano. Versiona parser, conversión, huella y orden.
- `generation`: entero 1 en este modelo offline. Una generación futura identifica
  un provisionamiento administrativo; no se asigna durante el arranque ni por
  URL, reinicio, fecha del dispositivo o cambio de contexto. El lector exige la
  generación autorizada. No se ha provisionado ninguna generación real.
- `state`: cadena `ready`.
- `source_sha256`: SHA-256 hexadecimal minúscula, 64 caracteres.
- `date_us`: BSON Int64 con microsegundos UTC desde 1970-01-01T00:00:00Z.
- `amount`: BSON Decimal128 finito, utilizado exclusivamente como clave de orden.

`unverifiable` contiene exactamente `version`, `generation`, `state`,
`source_sha256` y `reason`, sin claves numéricas parcialmente utilizables.
`reason` pertenece a `source`, `identity`, `date`, `amount`. No contiene valores
fuente, excepciones o datos de diagnóstico. La huella es null únicamente cuando
la representación fuente no puede codificarse bajo este contrato.

La ausencia de todo el bloque es historial `missing`, NO historial vacío ni
`ready`. Versión/generación incompatible, huella desactualizada o bloque corrupto
son resultados de inspección, no estados financieros. Nunca corregirlos al leer.

## Fecha canónica y límites

Reutilizar `backend.transaction_history.parse_instant(value, stored=True)`.
`datetime.fromisoformat` determina los formatos admitidos; las fechas sin zona
siguen siendo UTC. Se mantienen ISO básico, semana ISO, offsets con segundos y
microsegundos según el parser actual. No hacer strip, inferencias de zona o
parsing alternativo. La precisión inferior al microsegundo conserva exactamente
el comportamiento canónico; no introduce precisión inexistente.

Calcular mediante enteros:
`delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds`.
No usar timestamp float ni BSON Date con precisión de milisegundos. Validar rango
Int64 [-2^63, 2^63-1] mediante el encoder BSON. Todos los instantes representables
por el datetime canónico caben; un overflow al convertir offset a UTC sigue
siendo no verificable. No cambiar la cadena original ni clasificar el día
contable con una nueva zona R9.

Las reglas de datetime dependen del runtime: antes de cambiar Python, repetir
las pruebas de equivalencia y decidir si requiere nueva versión. No modificar
retroactivamente la interpretación de generaciones existentes.

## Importe exacto de lectura

No cuantizar a centavos ni usar estas claves para sumas, saldos o validación de
pagos. Para float finito, utilizar Decimal(str(value)), conforme a la adaptación
decimal ya utilizada por MoneyFlow, NO Decimal.from_float. Por ejemplo el valor
almacenado `0.1 + 0.2` produce `0.30000000000000004`, sin reparación a `0.3`.
Para enteros y cadenas numéricas utilizar Decimal(str(value)); para Decimal128
utilizar to_decimal. Se rechazan como clave booleanos, objetos, NaN e infinitos.

Ausente, null y cadena vacía producen cero SOLO para ordenación, conservando el
fallback visual existente. Sus huellas siguen siendo diferentes. Cero, negativo
y precisión adicional no son permisos financieros: la generación de claves no
sustituye la validación de importes existente ni altera datos históricos.

Construir Decimal128 con los traps estrictos del driver y comprobar igualdad
numérica de ida y vuelta. No autorizar redondeo, pérdida de precisión ni underflow
silencioso. La representación puede ajustar exponente o ceros sin cambiar valor;
la huella conserva el original. Probar 34 cifras significativas, `1E-6176`, máximo
finito, overflow e inexactitud. Una entrada fuera de rango queda unverifiable.

Limitación de compatibilidad: el contrato define orden decimal exacto. El frontend
actual resta números JavaScript; cadenas numéricas heredadas con precisión mayor
que Number pueden empatar en JavaScript y no en Decimal128. No afirmar equivalencia
universal de esos empates. Su integración exige inventario sintético y una
decisión explícita, sin transformar importes originales. Desempates históricos
sin criterio explícito pasan a tener el criterio determinista indicado abajo.

## Huella determinista y mantenimiento

Orden fijo de fuentes: `id`, `user_id`, `date`, `amount`. Cada entrada declara
`field`, `present`; si está presente añade `scalar_bson`, hexadecimal de
BSON.encode({value: valor original}). El envoltorio BSON contiene `contract: 1`
y el array `source`; SHA-256 se calcula sobre sus bytes. Se admiten fuentes
escalares null, string, int BSON representable, Int64, float, bool y Decimal128.
Tipos no definidos son unverifiable/source. No inventar serializaciones fallback.

Esto diferencia ausente/null, entero/Int64/double/string/Decimal128 y diferentes
cadenas que representan el mismo instante o importe. El orden de propiedades
del movimiento no afecta. La huella NO es autenticación, firma financiera ni
fingerprint de idempotencia. Los IDs de usuario son los efectivos del servidor;
`single_user/default-user` NO autentica a nadie.

Recalcular al insertar o modificar efectivamente cualquiera de esas cuatro
fuentes. Identidad inmutable bajo el contrato actual: el detector cubre cambios
para identificar corrupción, sin autorizar ediciones de identidad.

No recalcular por enlaces de factura/recurrencia/meta, notas, revisiones internas,
recibos, request_fingerprint ni cápsulas _shared_intent. Cuenta, destino, tipo y
categoría se filtran por los campos originales vigentes; no son duplicados en el
bloque. Sus cambios deben actualizar índices MongoDB normales en el futuro, pero
no cambian las claves de fecha/importe. Una retirada mantiene las claves si
permanece el movimiento; una anulación elimina claves con el documento financiero.
Restaurar seguimiento no crea movimiento ni dinero.

## Orden total y exposición pública

- recent: date_us DESC, id DESC.
- oldest: date_us ASC, id ASC.
- high: amount DESC, date_us DESC, id DESC.
- low: amount ASC, date_us DESC, id DESC.

Colación simple para IDs, unicidad de ID dentro del usuario efectivo verificada.
Dos pagos legítimos iguales con IDs diferentes permanecen dos filas. No usar
importe/fecha para deduplicar. Cursor futuro ligado a filtros, contexto, orden,
versión y generación; mantener el contrato de cursores antiguos de C3.

Antes de integrar, excluir `_history_keys` en proyecciones Y aplicar saneamiento
recursivo de todo el namespace `_history*` a respuestas públicas: listas, detalles,
resúmenes, documentos anidados y recuperaciones de idempotencia. Errores públicos
deben ser genéricos y no incluir bloques, fuentes o excepciones. El modelo de test
prueba la regla propuesta, NO afirma que los serializadores actuales la apliquen.
No admitir campos privados aportados por clientes. No cambiar formas públicas.

## Invalidación, historial y seguridad financiera

Unverifiable no añade una prohibición financiera nueva. Las reglas existentes
deciden si la operación financiera es válida. El futuro mantenimiento deberá
almacenar la marca junto a la escritura aceptada; un fallo real de escritura
abortará la transacción existente, sin transacciones anidadas. Bugs inesperados
del generador no deben ocultarse como fechas inválidas.

No omitir registros missing/unverifiable/incompatibles para devolver conteos
supuestamente completos. Bloquear la lectura optimizada afectada con error claro,
o emplear explícitamente una lectura canónica completa que pueda verificarla.
Nunca mezclar solo registros ready con un historial parcialmente provisionado.

Un procedimiento administrativo separado hará diagnóstico, autorización,
provisionamiento por lotes con comparación concurrente y verificación completa.
Se mantiene el original literal. La lectura no adopta/migra ni repara nada.
La inspección offline recalcula para comparar; esa comprobación exhaustiva no
equivale a una consulta indexada eficiente. Verificar solo filas devueltas no
detecta corrupción que las haya excluido: activación requiere cobertura completa,
todos los escritores compatibles y auditorías separadas.

Ninguna modificación de payload, clave de idempotencia, fingerprint, fechas,
vencimientos, movimientos compartidos ni journals R4/R6. Derivar únicamente del
documento final después de aplicar las reglas financieras originales.

## Requisitos del futuro prototipo atómico y rollback

1. Autorizar por separado incorporación a todas las rutas de escritura inventariadas.
2. Insertar/editar claves con el movimiento en su misma escritura y sesión;
   recalcular desde datos frescos en cada reintento. No cambiar manejadores.
3. Probar creación, edición, eliminación, transferencias, pagos, metas,
   desvinculación/restauración, rollback, concurrencia y commits inciertos.
4. Verificar que claves privadas no entren en ningún cálculo de idempotencia,
   journal, respuesta pública ni payload frontend.
5. Diagnosticar datos históricos sin escrituras antes de autorizar provisionamiento.
6. Probar índices, conteos, cursor, páginas profundas y cobertura solo en bases
   nuevas autorizadas. No existe garantía de coste constante para conteo/skip.
7. Activar lectura solo por entorno/generación verificados, sin mezcla de escritores
   antiguos. Ante corrupción no reparar datos automáticamente.
8. Desactivar lectores optimizados antes de volver a un backend sin mantenimiento.
   Revertir solo metadatos con comparación del estado vigente, nunca documentos
   financieros completos ni cambios legítimos posteriores.

## Verificación disponible

`python3 -B -m unittest backend.experiments.test_c3_history_keys_contract -v`

Usa el encoder BSON y Decimal128 instalados, sin MongoClient ni conexión MongoDB.
No importa server.py, no lee .env ni instala dependencias. No prueba atomicidad,
serializadores actuales ni índices: esas son etapas futuras. Comprobar también
P3 y suites offline anteriores sin editar sus 18 archivos.

Ejecución de esta etapa: 93 tests, 87 aprobados y 6 fallos esperados, sin fallos
nuevos. Desglose: contrato de claves 25/25; P3 26/26; P1 7/7; P2 7 aprobados y
3 fallos esperados del parser no modificado; lector C3 12/12; contratos anteriores
C3/R9 10 aprobados y 3 fallos esperados (historial por cuenta truncado, resumen
limitado a 2.000 y uso de offset actual en lugar de IANA histórica).
Estas ejecuciones son offline; no constituyen evidencia de MongoDB real,
mantenimiento atómico o ausencia de filtraciones en serializadores actuales.
