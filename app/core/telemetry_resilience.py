"""Módulo de Telemetría y Métricas en Memoria para Resiliencia de Consultas y Aclaraciones."""

import threading
from typing import Dict, Any


class ResilienceMetrics:
    """Contador atómico thread-safe para métricas de auto-reparación y aclaración."""

    def __init__(self):
        self._lock = threading.Lock()
        self.sql_repair_attempts_total = 0
        self.sql_repair_success_total = 0
        self.sql_repair_exhausted_total = 0
        self.clarifications_requested_total = 0
        self.clarifications_resolved_total = 0

    def inc_repair_attempts(self, count: int = 1):
        with self._lock:
            self.sql_repair_attempts_total += count

    def inc_repair_success(self, count: int = 1):
        with self._lock:
            self.sql_repair_success_total += count

    def inc_repair_exhausted(self, count: int = 1):
        with self._lock:
            self.sql_repair_exhausted_total += count

    def inc_clarifications_requested(self, count: int = 1):
        with self._lock:
            self.clarifications_requested_total += count

    def inc_clarifications_resolved(self, count: int = 1):
        with self._lock:
            self.clarifications_resolved_total += count

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            success_rate = 0.0
            if self.sql_repair_attempts_total > 0:
                success_rate = round((self.sql_repair_success_total / self.sql_repair_attempts_total) * 100, 2)

            return {
                "sql_repair_attempts_total": self.sql_repair_attempts_total,
                "sql_repair_success_total": self.sql_repair_success_total,
                "sql_repair_exhausted_total": self.sql_repair_exhausted_total,
                "sql_repair_success_rate_pct": success_rate,
                "clarifications_requested_total": self.clarifications_requested_total,
                "clarifications_resolved_total": self.clarifications_resolved_total,
            }

    def reset(self):
        with self._lock:
            self.sql_repair_attempts_total = 0
            self.sql_repair_success_total = 0
            self.sql_repair_exhausted_total = 0
            self.clarifications_requested_total = 0
            self.clarifications_resolved_total = 0


# Instancia singleton global
resilience_metrics = ResilienceMetrics()
