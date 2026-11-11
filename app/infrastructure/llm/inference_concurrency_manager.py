"""Gestor atómico de concurrencia y cancelación activa de inferencias del detector en Ollama."""

import asyncio
from typing import Dict, Optional


class InferenceConcurrencyManager:
    """
    Rastrea el número de inferencias interactivas en vuelo y cancela
    activamente las tareas del detector en background cuando entra una nueva consulta.
    """
    _instance: Optional['InferenceConcurrencyManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._active_user_queries = 0
            cls._instance._background_tasks: Dict[str, asyncio.Task] = {}
            cls._instance._cancellations_total = 0
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'InferenceConcurrencyManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_user_query_start(self, session_id: Optional[str] = None):
        """Registra el inicio de una consulta interactiva del usuario y aborta detectors en vuelo."""
        self._active_user_queries += 1
        self.cancel_all_background_detectors(reason="Nueva consulta de usuario interactiva recibida")

    def register_user_query_end(self):
        """Decrementa el contador de consultas interactivas."""
        if self._active_user_queries > 0:
            self._active_user_queries -= 1

    def is_ollama_busy(self) -> bool:
        """Determina si hay consultas interactivas activas compitiendo por CPU/Ollama."""
        return self._active_user_queries > 0

    def register_background_detector(self, task_id: str, task: asyncio.Task):
        """Registra una tarea del detector en segundo plano."""
        self._background_tasks[task_id] = task

    def unregister_background_detector(self, task_id: str):
        """Desregistra una tarea del detector completada o cancelada."""
        self._background_tasks.pop(task_id, None)

    def cancel_all_background_detectors(self, reason: str = "Interrupción"):
        """Cancela y aborta activamente todas las peticiones a Ollama del detector en background."""
        for task_id, task in list(self._background_tasks.items()):
            if not task.done():
                task.cancel()
                self._cancellations_total += 1
        self._background_tasks.clear()

    @property
    def cancellations_total(self) -> int:
        """Contador de cancelaciones del detector en background."""
        return self._cancellations_total
