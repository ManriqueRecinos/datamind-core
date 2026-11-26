"""Entrenamiento estratificado por documento (hash determinista + 3-Fold Group CV), persistencia atómica y predicción singleton."""

import asyncio
import hashlib
import json
import math
import os
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.core.config import get_settings
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.ml.dataset import load_pgvector_training_dataset

_STORAGE_DIR = Path(__file__).resolve().parents[3] / "storage" / "neural_lab"
_MODEL_PATH = _STORAGE_DIR / "knowledge_classifier.keras"
_LABELS_PATH = _STORAGE_DIR / "labels.json"
_LOCK = threading.Lock()

# Snapshot atómico: bundle = (model, labels, meta, mtime)
_STATE: Dict[str, Any] = {
    "bundle": None,
}


def _set_reproducible_seeds(seed: int = 42) -> None:
    import tensorflow as tf
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def _filter_small_classes_by_doc(
    X: np.ndarray,
    y: np.ndarray,
    doc_ids: np.ndarray,
    labels: List[str],
    min_docs_per_class: int = 8,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str], List[str]]:
    """Excluye categorías con menos de min_docs_per_class documentos distintos."""
    valid_old_ids = []
    excluded = []
    for idx, lbl in enumerate(labels):
        mask_cls = (y == idx)
        n_docs = len(set(doc_ids[mask_cls].tolist()))
        if n_docs >= min_docs_per_class:
            valid_old_ids.append(idx)
        else:
            excluded.append(lbl)

    if not valid_old_ids:
        return X, y, doc_ids, labels, []

    id_map = {old_id: new_id for new_id, old_id in enumerate(valid_old_ids)}
    mask = np.isin(y, valid_old_ids)
    X_clean = X[mask]
    y_clean = np.array([id_map[int(v)] for v in y[mask]], dtype=np.int32)
    docs_clean = doc_ids[mask]
    clean_labels = [labels[old_id] for old_id in valid_old_ids]
    return X_clean, y_clean, docs_clean, clean_labels, excluded


def _hash_doc_split_70_15_15(
    X: np.ndarray, y: np.ndarray, doc_ids: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split estratificado por documento (70% train / 15% val / 15% test) ordenado por hash MD5 de doc_id.
    Garantiza que el conjunto de test sea fijo por document_id independientemente de la semilla.
    """
    doc_to_indices: Dict[str, List[int]] = {}
    doc_to_class: Dict[str, int] = {}
    for idx, (d_id, cls_id) in enumerate(zip(doc_ids.tolist(), y.tolist())):
        doc_to_indices.setdefault(d_id, []).append(idx)
        doc_to_class[d_id] = cls_id

    cls_to_docs: Dict[int, List[str]] = {}
    for d_id, cls_id in doc_to_class.items():
        cls_to_docs.setdefault(cls_id, []).append(d_id)

    train_idx, val_idx, test_idx = [], [], []
    for cls_id in sorted(cls_to_docs.keys()):
        docs = sorted(
            cls_to_docs[cls_id],
            key=lambda d: hashlib.md5(d.encode("utf-8")).hexdigest(),
        )
        n = len(docs)
        n_val = max(1, int(round(n * 0.15)))
        n_test = max(1, int(round(n * 0.15)))
        n_train = max(1, n - n_val - n_test)

        for d in docs[:n_train]:
            train_idx.extend(doc_to_indices[d])
        for d in docs[n_train:n_train + n_val]:
            val_idx.extend(doc_to_indices[d])
        for d in docs[n_train + n_val:]:
            test_idx.extend(doc_to_indices[d])

    return (
        X[train_idx], y[train_idx],
        X[val_idx], y[val_idx],
        X[test_idx], y[test_idx],
    )


def _compute_balanced_class_weights(y: np.ndarray, num_classes: int) -> Dict[int, float]:
    counts = np.bincount(y, minlength=num_classes)
    total = float(len(y))
    return {
        idx: round(total / (num_classes * max(1, int(cnt))), 4)
        for idx, cnt in enumerate(counts)
    }


def _per_class_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, labels: List[str]
) -> Tuple[Dict[str, Dict[str, Any]], List[List[int]], float]:
    cm = np.zeros((len(labels), len(labels)), dtype=int)
    for t, p in zip(y_true.tolist(), y_pred.tolist()):
        cm[int(t), int(p)] += 1

    out: Dict[str, Dict[str, Any]] = {}
    f1_list: List[float] = []
    for i, lbl in enumerate(labels):
        tp = int(cm[i, i])
        fp = int(cm[:, i].sum() - tp)
        fn = int(cm[i, :].sum() - tp)
        pr = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rc = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * pr * rc / (pr + rc)) if (pr + rc) > 0 else 0.0
        f1_list.append(f1)
        out[lbl] = {
            "precision": round(pr, 3),
            "recall": round(rc, 3),
            "f1": round(f1, 3),
            "support": int(cm[i, :].sum()),
        }
    macro_f1 = round(float(np.mean(f1_list)) * 100, 2) if f1_list else 0.0
    return out, cm.tolist(), macro_f1


def _run_grouped_cv(
    X: np.ndarray,
    y: np.ndarray,
    doc_ids: np.ndarray,
    labels: List[str],
    learning_rate: float,
    epochs: int,
    hidden_layers: Optional[List[int]],
    k_folds: int = 3,
) -> Dict[str, float]:
    """Ejecuta K-Fold estratificado agrupado por documento."""
    import tensorflow as tf
    from app.infrastructure.ml.builder import build_knowledge_classifier

    doc_to_indices: Dict[str, List[int]] = {}
    doc_to_class: Dict[str, int] = {}
    for idx, (d_id, cls_id) in enumerate(zip(doc_ids.tolist(), y.tolist())):
        doc_to_indices.setdefault(d_id, []).append(idx)
        doc_to_class[d_id] = cls_id

    cls_to_docs: Dict[int, List[str]] = {}
    for d_id, cls_id in doc_to_class.items():
        cls_to_docs.setdefault(cls_id, []).append(d_id)

    for cls_id in cls_to_docs:
        cls_to_docs[cls_id].sort(key=lambda d: hashlib.md5(d.encode("utf-8")).hexdigest())

    fold_f1s: List[float] = []
    fold_accs: List[float] = []
    num_classes = len(labels)

    for fold in range(k_folds):
        tr_idx, va_idx = [], []
        for cls_id, docs in cls_to_docs.items():
            for i, d in enumerate(docs):
                if i % k_folds == fold:
                    va_idx.extend(doc_to_indices[d])
                else:
                    tr_idx.extend(doc_to_indices[d])
        if not tr_idx or not va_idx:
            continue
        _set_reproducible_seeds(42 + fold)
        X_tr, y_tr = X[tr_idx], y[tr_idx]
        X_va, y_va = X[va_idx], y[va_idx]
        cw = _compute_balanced_class_weights(y_tr, num_classes)
        m = build_knowledge_classifier(num_classes=num_classes, learning_rate=learning_rate, hidden_layers=hidden_layers)
        cb = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)]
        m.fit(X_tr, y_tr, validation_data=(X_va, y_va), epochs=min(epochs, 35), batch_size=min(16, len(X_tr)), class_weight=cw, callbacks=cb, verbose=0)
        preds = np.argmax(m(X_va, training=False).numpy(), axis=1)
        _, _, mf1 = _per_class_metrics(y_va, preds, labels)
        acc = round(float(np.mean(preds == y_va)) * 100, 2)
        fold_f1s.append(mf1)
        fold_accs.append(acc)

    return {
        "cv_folds": k_folds,
        "cv_macro_f1_mean": round(float(np.mean(fold_f1s)), 2) if fold_f1s else 0.0,
        "cv_macro_f1_std": round(float(np.std(fold_f1s)), 2) if fold_f1s else 0.0,
        "cv_acc_mean": round(float(np.mean(fold_accs)), 2) if fold_accs else 0.0,
        "cv_acc_std": round(float(np.std(fold_accs)), 2) if fold_accs else 0.0,
    }


def _save_model_atomic(model, meta: Dict[str, Any]) -> float:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_model = _STORAGE_DIR / f"knowledge_classifier.{uuid.uuid4().hex[:8]}.tmp.keras"
    tmp_labels = _STORAGE_DIR / f"labels.{uuid.uuid4().hex[:8]}.tmp.json"

    model.save(tmp_model)
    tmp_labels.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    os.replace(tmp_model, _MODEL_PATH)
    os.replace(tmp_labels, _LABELS_PATH)
    return _LABELS_PATH.stat().st_mtime


def _get_or_load_bundle() -> Optional[Tuple[Any, List[str], Dict[str, Any]]]:
    settings = get_settings()
    with _LOCK:
        current = _STATE["bundle"]
        disk_mtime = _LABELS_PATH.stat().st_mtime if _LABELS_PATH.exists() else None
        if current is not None and (disk_mtime is None or current[3] == disk_mtime):
            return current[0], current[1], current[2]

        if _MODEL_PATH.exists() and _LABELS_PATH.exists():
            import tensorflow as tf
            meta = json.loads(_LABELS_PATH.read_text(encoding="utf-8"))
            if isinstance(meta, list):
                labels = meta
                emb_model = settings.embedding_model
                emb_dim = 768
                meta = {"labels": labels, "embedding_model": emb_model, "embedding_dim": emb_dim}
            else:
                labels = meta.get("labels", [])
                emb_model = meta.get("embedding_model")
                emb_dim = meta.get("embedding_dim", 768)

            if emb_model != settings.embedding_model or emb_dim != 768:
                return None

            model = tf.keras.models.load_model(_MODEL_PATH)
            if model.input_shape[-1] != 768:
                return None

            _STATE["bundle"] = (model, labels, meta, disk_mtime)
            return model, labels, meta
    return None


async def train_knowledge_model(
    learning_rate: float = 0.001,
    epochs: int = 50,
    hidden_layers: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Entrena con split determinista por hash de document_id, CV 3-fold y reglas estrictas de promoción."""
    import tensorflow as tf
    from app.infrastructure.ml.builder import build_knowledge_classifier

    _set_reproducible_seeds(42)
    X_raw, y_raw, raw_labels, doc_ids_raw, label_conflicts = await load_pgvector_training_dataset()
    X, y, doc_ids, labels, excluded_classes = _filter_small_classes_by_doc(
        X_raw, y_raw, doc_ids_raw, raw_labels, min_docs_per_class=8
    )
    num_classes = len(labels)

    X_train, y_train, X_val, y_val, X_test, y_test = _hash_doc_split_70_15_15(X, y, doc_ids)
    class_weights = _compute_balanced_class_weights(y_train, num_classes)

    def _fit_and_eval():
        _set_reproducible_seeds(42)
        model = build_knowledge_classifier(
            num_classes=num_classes,
            learning_rate=learning_rate,
            hidden_layers=hidden_layers,
        )
        callbacks = [
            tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6, restore_best_weights=True),
            tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5),
        ]
        t0 = time.perf_counter()
        history = model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=min(16, max(1, len(X_train))),
            class_weight=class_weights,
            callbacks=callbacks,
            verbose=0,
        )
        dt_ms = round((time.perf_counter() - t0) * 1000, 2)
        # Evaluación post-restore_best_weights
        val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
        test_loss, test_acc = model.evaluate(X_test, y_test, verbose=0)
        y_pred = np.argmax(model(X_test, training=False).numpy(), axis=1)
        cv_stats = _run_grouped_cv(X, y, doc_ids, labels, learning_rate, epochs, hidden_layers, k_folds=3)
        return model, history.history, dt_ms, float(val_loss), float(val_acc), float(test_loss), float(test_acc), y_pred, cv_stats

    model, hist, elapsed_ms, val_loss, val_acc, test_loss, test_acc, y_pred, cv_stats = await asyncio.to_thread(_fit_and_eval)

    per_class, confusion_matrix, macro_f1 = _per_class_metrics(y_test, y_pred, labels)
    # majority_baseline calculado sobre el conjunto de TEST (y_test)
    counts_test = np.bincount(y_test, minlength=num_classes)
    majority_baseline = round(float(np.max(counts_test)) / max(1, len(y_test)) * 100, 2)

    test_accuracy_pct = round(test_acc * 100, 2)
    val_accuracy_pct = round(val_acc * 100, 2)

    loss_history = [0.0 if (math.isnan(float(v)) or math.isinf(float(v))) else round(float(v), 4) for v in hist.get("loss", [])]
    acc_history = [0.0 if (math.isnan(float(v)) or math.isinf(float(v))) else round(float(v) * 100, 2) for v in hist.get("accuracy", [])]

    min_class_recall = min((m["recall"] for m in per_class.values()), default=0.0)
    prev_cv_f1 = 0.0
    if _LABELS_PATH.exists():
        try:
            old_meta = json.loads(_LABELS_PATH.read_text(encoding="utf-8"))
            if isinstance(old_meta, dict) and old_meta.get("labels") == labels:
                prev_cv_f1 = float((old_meta.get("cv") or {}).get("cv_macro_f1_mean", 0.0))
        except Exception:
            prev_cv_f1 = 0.0

    cv_f1_mean = float(cv_stats.get("cv_macro_f1_mean", 0.0))
    cv_acc_mean = float(cv_stats.get("cv_acc_mean", 0.0))
    # Promoción decidida por métricas de Cross-Validation (CV), dejando test solo para reporte
    promoted = bool(
        cv_f1_mean >= 70.0
        and min_class_recall >= 0.50
        and cv_acc_mean > majority_baseline
        and cv_f1_mean >= prev_cv_f1
    )

    train_id = uuid.uuid4().hex[:12]
    meta = {
        "train_id": train_id,
        "promoted": promoted,
        "labels": labels,
        "excluded_classes": excluded_classes,
        "embedding_model": get_settings().embedding_model,
        "embedding_dim": 768,
        "total_samples": int(len(X)),
        "val_loss": round(val_loss, 4),
        "val_accuracy": val_accuracy_pct,
        "test_loss": round(test_loss, 4),
        "test_accuracy": test_accuracy_pct,
        "macro_f1": macro_f1,
        "majority_baseline": majority_baseline,
        "cv": cv_stats,
        "confusion_matrix": confusion_matrix,
        "per_class": per_class,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    if promoted or not _MODEL_PATH.exists():
        with _LOCK:
            mtime = await asyncio.to_thread(_save_model_atomic, model, meta)
            _STATE["bundle"] = (model, labels, meta, mtime)

    warning = "Muestra pequeña (<100 chunks tras filtro): las métricas de validación tienen varianza alta." if len(X) < 100 else None

    return {
        "train_id": train_id,
        "promoted": promoted,
        "total_samples": int(len(X)),
        "split_sizes": {"train": int(len(X_train)), "val": int(len(X_val)), "test": int(len(X_test))},
        "classes": labels,
        "excluded_classes": excluded_classes,
        "label_conflicts": label_conflicts,
        "num_classes": num_classes,
        "total_params": int(model.count_params()),
        "epochs": len(loss_history),
        "learning_rate": learning_rate,
        "training_time_ms": elapsed_ms,
        "final_train_loss": loss_history[-1] if loss_history else None,
        "final_loss": loss_history[-1] if loss_history else None,
        "val_loss": round(val_loss, 4),
        "val_accuracy": val_accuracy_pct,
        "test_loss": round(test_loss, 4),
        "test_accuracy": test_accuracy_pct,
        "final_accuracy": test_accuracy_pct,
        "macro_f1": macro_f1,
        "majority_baseline": majority_baseline,
        "cv": cv_stats,
        "per_class": per_class,
        "confusion_matrix": confusion_matrix,
        "loss_history": loss_history,
        "accuracy_history": acc_history,
        "warning": warning,
    }


def predict_category_from_embedding(embedding: List[float]) -> Optional[Dict[str, Any]]:
    """Predice categoría y boost proporcional leyendo un snapshot atómico (model, labels)."""
    settings = get_settings()
    if not settings.enable_neural_category_boost:
        return None
    if len(embedding) != 768:
        return None

    bundle = _get_or_load_bundle()
    if bundle is None:
        return None
    model, labels, _ = bundle

    vec = np.array([embedding], dtype=np.float32)
    probs = model(vec, training=False).numpy()[0]
    best_idx = int(np.argmax(probs))
    confidence = float(probs[best_idx])

    if confidence < settings.neural_boost_min_confidence:
        return None

    return {
        "predicted_label": labels[best_idx],
        "confidence": round(confidence * 100, 2),
        "boost": round(settings.neural_boost_weight * confidence, 4),
    }


async def predict_knowledge_category(text: str) -> Dict[str, Any]:
    """Vectoriza una pregunta en lenguaje natural y predice su categoría/concepto."""
    bundle = _get_or_load_bundle()
    if bundle is None:
        raise ValueError("El modelo clasificador aún no ha sido entrenado. Ejecuta /train primero.")
    model, labels, _ = bundle

    ollama = OllamaAdapter()
    embedding = await ollama.generate_embedding(text)
    vec = np.array([embedding], dtype=np.float32)

    probs = await asyncio.to_thread(lambda: model(vec, training=False).numpy()[0])

    ranked = sorted(
        [{"label": labels[i], "confidence": round(float(probs[i]) * 100, 2)} for i in range(len(labels))],
        key=lambda item: item["confidence"],
        reverse=True,
    )

    return {
        "text": text,
        "predicted_label": ranked[0]["label"] if ranked else "desconocido",
        "confidence": ranked[0]["confidence"] if ranked else 0.0,
        "top_predictions": ranked[:5],
    }
