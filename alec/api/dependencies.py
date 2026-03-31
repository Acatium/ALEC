"""FastAPI dependency injection helpers."""

from __future__ import annotations

import asyncpg
from fastapi import Request

from alec.config.settings import Settings
from alec.events.bus import EventBus
from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.relationships import RelationshipRepository


def get_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.pool
    return pool


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_event_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus


def get_entity_repo(request: Request) -> EntityRepository:
    return EntityRepository(get_pool(request))


def get_relationship_repo(request: Request) -> RelationshipRepository:
    return RelationshipRepository(get_pool(request))


def get_observation_repo(request: Request) -> ObservationRepository:
    return ObservationRepository(get_pool(request))
