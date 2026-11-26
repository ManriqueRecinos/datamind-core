"""Construcción de red neuronal multicapa en TensorFlow/Keras sobre embeddings de 768-dim."""

from typing import List, Optional
import tensorflow as tf


def build_knowledge_classifier(
    num_classes: int,
    learning_rate: float = 0.001,
    hidden_layers: Optional[List[int]] = None,
) -> tf.keras.Sequential:
    """Red neuronal multicapa para clasificar embeddings (768-dim) en conceptos/categorías."""
    layers_cfg = hidden_layers or [128, 64]
    layers = [tf.keras.layers.Input(shape=(768,))]
    for idx, units in enumerate(layers_cfg, start=1):
        layers.append(tf.keras.layers.Dense(units=units, activation="relu", name=f"oculta_{idx}"))
        layers.append(tf.keras.layers.Dropout(0.2, name=f"dropout_{idx}"))

    layers.append(tf.keras.layers.Dense(units=num_classes, activation="softmax", name="salida_clases"))

    model = tf.keras.Sequential(layers, name="clasificador_conocimiento")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model
