# Feature Specification: 012-single-neuron-feedback-reranker

## 1. Idea
Crear **una sola neurona** (regresión logística: `p = sigmoid(w·x + b)`) que aprenda, con los 👍/👎 de los usuarios, **qué tablas y reglas recuperadas del RAG suelen llevar a buenas respuestas**, y reordene (rerank) los candidatos antes de generar el SQL. Es el paso más pequeño posible de "IA que aprende con el uso": sin GPU, sin librerías pesadas y totalmente explicable (cada peso dice cuánto importa una señal).

## 2. Problema que resuelve
Hoy la recuperación de esquemas (`search_schema_with_relations`) ordena por similitud vectorial + coincidencia léxica con reglas fijas, y la decisión de pedir aclaración usa un umbral fijo (0.65). Si el sistema elige una tabla equivocada, no existe ninguna forma de que lo "aprenda": el usuario corrige pero la próxima vez ocurre igual.

## 3. Alcance (MVP)
- **Señal de aprendizaje**: botones 👍/👎 en cada respuesta del chat (hoy no existen) que guardan el voto.
- **Una neurona**: recibe un vector de características por cada tabla/regla candidata y devuelve una probabilidad de utilidad.
- **Uso**: reordenar los candidatos recuperados antes del Text-to-SQL; la salida se mezcla con la similitud vectorial (`score = α·similitud + (1-α)·neurona`) y `α` empieza en 1.0 (la neurona no influye hasta tener datos suficientes).
- **Fuera de alcance**: redes multicapa, fine-tuning del LLM, cambiar embeddings.

## 4. Características de entrada (x) por candidato
1. `similarity_score` (coseno del vector).
2. `rank_position` normalizada (posición en la recuperación inicial).
3. `name_in_prompt` (1 si el nombre exacto de la tabla aparece en la pregunta).
4. `is_graph_hop` (1 si entró por expansión de relaciones 1-hop, no por similitud directa).
5. `has_learned_rule` (1 si hay una regla/relación aprendida sobre esa tabla).
6. `in_verified_example` (1 si la tabla aparece en algún ejemplo SQL verificado que se le enseñó a la IA).
7. `table_prior`: tasa histórica de votos positivos de esa tabla (suavizada), 0.5 si no hay datos.

## 5. Etiqueta (y)
- 👍 en una respuesta → las tablas que realmente aparecieron en el SQL ejecutado = 1; las recuperadas pero no usadas = sin etiqueta.
- 👎 → las tablas del SQL ejecutado = 0.
- Una corrección del usuario ("no, me refería a X") que el sistema ya detecta como candidato de conocimiento (`detect_dialogue_correction`) cuenta como 0 para la tabla equivocada y 1 para la tabla corregida.

## 6. Requisitos funcionales
- FR-1: Tabla `neuron_training_examples` (features JSON, label, connection_id, message_id, created_at) y tabla `neuron_weights` (versión, pesos, sesgo, n_ejemplos, métricas, activa).
- FR-2: Endpoint `POST /api/v1/chat/messages/{id}/feedback` (`up|down`, comentario opcional); Laravel muestra 👍/👎 y reenvía.
- FR-3: Entrenamiento por SGD con regularización L2, ejecutado en lote (comando/endpoint admin) y también en línea de a un ejemplo; lectura de pesos con caché en memoria.
- FR-4: Arranque en frío: pesos iniciales que reproducen el comportamiento actual (`w_similarity=1`, resto 0) para no empeorar nada.
- FR-5: Activación gradual: la neurona solo influye si hay ≥ 50 ejemplos y la métrica de validación (AUC/precisión en un 20% reservado) supera al orden actual; `α` baja de 1.0 a 0.5 de forma controlada.
- FR-6: Vista admin en el Centro de Aprendizaje: pesos actuales, n de ejemplos, métrica y botón "restaurar pesos por defecto".
- FR-7: Explicabilidad: en el detalle de una respuesta se puede ver por qué una tabla subió o bajó (contribución por característica).

## 7. Criterios de aceptación
- Sin votos, el orden de resultados es idéntico al actual.
- Tras entrenar con ejemplos donde `name_in_prompt` conduce a buenas respuestas, ese peso es positivo y la tabla nombrada sube de posición en una pregunta de prueba.
- Un voto 👎 sobre una tabla reduce su `table_prior` y su probabilidad en la siguiente consulta similar.
- Se puede desactivar la neurona (flag `ENABLE_NEURON_RERANK=false`) sin tocar código.
- Pruebas unitarias: gradiente correcto, convergencia en datos sintéticos separables, y equivalencia con el orden actual con pesos por defecto.

## 8. Riesgos
- **Pocos datos al inicio**: por eso el arranque en frío neutral, `α=1` y el umbral de 50 ejemplos.
- **Sesgo por usuarios que votan poco o mal**: guardar `user_id` y poder filtrar/ponderar.
- **Privacidad**: los ejemplos guardan solo características numéricas e ids de tablas, no filas de datos.
- **Etiqueta ruidosa**: un 👎 puede deberse al formato y no a la tabla; el comentario opcional y la corrección explícita ayudan a separar.

## 9. Siguientes pasos naturales (después de esta feature)
Más neuronas por intención → red pequeña de 2 capas → reranker cruzado ajustado por conexión.
