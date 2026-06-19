"""Generic long-running task framework (registry + manager + lifecycle).

A task is a unit of work tied to a persisted `run` (tracked by the Rust host).
Each task type registers a factory via :func:`tasks.registry.register_task`, and
the :class:`tasks.manager.TaskManager` spawns/controls them, streaming progress
back to the host as bus events (``task.status``/``task.item``/``task.log`` ...).
"""
