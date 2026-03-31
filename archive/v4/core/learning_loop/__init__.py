"""ALEC Learning Loop - Event-driven learning from conversation signals.

v3 Architecture with 4 services:
- REFLECTOR: Turn analysis, attribution, counter updates, AKU extraction
- CURATOR: Quality gate and deduplication for AKUs
- CLUSTERER: Cluster management and solved_by edges
- ADVISOR: Bullet retrieval with Thompson Sampling

Import services directly from submodules to avoid circular dependencies:
    from core.learning_loop.reflector import ReflectorService
    from core.learning_loop.curator import CuratorService
    from core.learning_loop.clusterer import ClustererService
    from core.learning_loop.advisor import AdvisorService
"""

__version__ = "3.0.0"
