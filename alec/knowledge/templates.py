"""Engagement schema templates — predefined ontologies for different use cases."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

TEMPLATES: dict[str, dict[str, Any]] = {
    "general_discovery": {
        "name": "General Discovery",
        "description": "Broad exploration of any knowledge domain.",
        "entity_types": [
            {
                "name": "concept",
                "description": "An abstract idea or notion",
                "examples": ["microservices", "GDPR compliance"],
            },
            {
                "name": "entity",
                "description": "A concrete named thing",
                "examples": ["Apple Inc.", "Python 3.12"],
            },
            {
                "name": "organization",
                "description": "A company, team, or institution",
                "examples": ["Engineering Team", "Anthropic"],
            },
            {
                "name": "policy",
                "description": "A rule, regulation, or guideline",
                "examples": [
                    "data retention policy",
                    "code review standards",
                ],
            },
            {
                "name": "process",
                "description": "A workflow or procedure",
                "examples": [
                    "CI/CD pipeline",
                    "onboarding process",
                ],
            },
            {
                "name": "document",
                "description": "A written artifact",
                "examples": ["API spec", "design doc"],
            },
            {
                "name": "role",
                "description": "A job function or responsibility",
                "examples": ["data steward", "product owner"],
            },
            {
                "name": "capability",
                "description": "A functional ability or feature",
                "examples": ["real-time processing", "SSO"],
            },
            {
                "name": "requirement",
                "description": "A constraint or must-have condition",
                "examples": ["99.9% uptime", "WCAG 2.1 AA"],
            },
            {
                "name": "system",
                "description": "A technical system or platform",
                "examples": ["payment gateway", "CRM"],
            },
        ],
        "relationship_types": [
            {
                "name": "relates_to",
                "description": "General association",
                "examples": ["X relates_to Y"],
                "parent_category": "structural",
            },
            {
                "name": "contains",
                "description": (
                    "Compositional: X contains Y as a part"
                ),
                "examples": ["system contains module"],
                "parent_category": "compositional",
            },
            {
                "name": "governs",
                "description": (
                    "X sets rules or constraints for Y"
                ),
                "examples": ["policy governs process"],
                "parent_category": "governance",
            },
            {
                "name": "implements",
                "description": "X realizes or executes Y",
                "examples": ["service implements API"],
                "parent_category": "realization",
            },
            {
                "name": "depends_on",
                "description": "X requires Y to function",
                "examples": ["service depends_on database"],
                "parent_category": "dependency",
            },
            {
                "name": "supports",
                "description": "X enables or assists Y",
                "examples": ["tool supports workflow"],
                "parent_category": "dependency",
            },
            {
                "name": "contradicts",
                "description": (
                    "X conflicts with or opposes Y"
                ),
                "examples": ["finding contradicts claim"],
                "parent_category": "epistemic",
            },
            {
                "name": "supersedes",
                "description": "X replaces or obsoletes Y",
                "examples": ["v2 supersedes v1"],
                "parent_category": "temporal",
            },
            {
                "name": "produces",
                "description": "X generates or creates Y",
                "examples": ["process produces artifact"],
                "parent_category": "realization",
            },
            {
                "name": "applies_to",
                "description": (
                    "X is relevant to or targets Y"
                ),
                "examples": ["regulation applies_to domain"],
                "parent_category": "governance",
            },
        ],
    },
    "enterprise_architecture": {
        "name": "Enterprise Architecture",
        "description": (
            "Software systems, teams, and technical"
            " infrastructure."
        ),
        "entity_types": [
            {
                "name": "service",
                "description": "A deployable software service",
                "examples": ["auth-service", "payment-api"],
            },
            {
                "name": "database",
                "description": "A data store",
                "examples": [
                    "PostgreSQL cluster",
                    "Redis cache",
                ],
            },
            {
                "name": "team",
                "description": (
                    "An engineering or business team"
                ),
                "examples": [
                    "Platform Team",
                    "Data Engineering",
                ],
            },
            {
                "name": "api",
                "description": "An interface or endpoint",
                "examples": [
                    "REST API v2",
                    "GraphQL gateway",
                ],
            },
            {
                "name": "platform",
                "description": (
                    "A foundational system or infrastructure"
                ),
                "examples": ["Kubernetes", "AWS"],
            },
            {
                "name": "capability",
                "description": (
                    "A business or technical capability"
                ),
                "examples": [
                    "payment processing",
                    "user authentication",
                ],
            },
            {
                "name": "domain",
                "description": (
                    "A bounded context or business domain"
                ),
                "examples": [
                    "billing domain",
                    "identity domain",
                ],
            },
            {
                "name": "process",
                "description": "A workflow or pipeline",
                "examples": [
                    "CI/CD pipeline",
                    "data ingestion",
                ],
            },
            {
                "name": "schema",
                "description": "A data schema or model",
                "examples": [
                    "user_events schema",
                    "order DDL",
                ],
            },
            {
                "name": "repository",
                "description": "A code repository",
                "examples": ["monorepo", "shared-libs"],
            },
            {
                "name": "document",
                "description": "Technical documentation",
                "examples": ["ADR-042", "runbook"],
            },
            {
                "name": "person",
                "description": "A named individual",
                "examples": ["tech lead", "SRE on-call"],
            },
        ],
        "relationship_types": [
            {
                "name": "depends_on",
                "description": "Runtime or build dependency",
                "examples": ["service depends_on database"],
                "parent_category": "dependency",
            },
            {
                "name": "owned_by",
                "description": "Ownership or stewardship",
                "examples": ["service owned_by team"],
                "parent_category": "governance",
            },
            {
                "name": "reads_from",
                "description": "Data consumption",
                "examples": ["service reads_from database"],
                "parent_category": "dependency",
            },
            {
                "name": "writes_to",
                "description": "Data production",
                "examples": ["service writes_to queue"],
                "parent_category": "dependency",
            },
            {
                "name": "calls",
                "description": "Synchronous invocation",
                "examples": [
                    "gateway calls auth-service",
                ],
                "parent_category": "dependency",
            },
            {
                "name": "governs",
                "description": "Sets rules or policies for",
                "examples": ["SLA governs service"],
                "parent_category": "governance",
            },
            {
                "name": "implements",
                "description": (
                    "Realizes a capability or spec"
                ),
                "examples": ["service implements API"],
                "parent_category": "realization",
            },
            {
                "name": "contains",
                "description": "Compositional containment",
                "examples": [
                    "platform contains service",
                ],
                "parent_category": "compositional",
            },
            {
                "name": "supersedes",
                "description": "Replaces or deprecates",
                "examples": ["v3 supersedes v2"],
                "parent_category": "temporal",
            },
            {
                "name": "related_to",
                "description": "General association",
                "examples": ["schema related_to domain"],
                "parent_category": "structural",
            },
        ],
    },
    "research_synthesis": {
        "name": "Research Synthesis",
        "description": (
            "Academic research, literature reviews,"
            " and evidence synthesis."
        ),
        "entity_types": [
            {
                "name": "concept",
                "description": (
                    "A theoretical concept or construct"
                ),
                "examples": [
                    "cognitive load",
                    "attention mechanism",
                ],
            },
            {
                "name": "theory",
                "description": (
                    "A formal theory or framework"
                ),
                "examples": [
                    "dual process theory",
                    "transformer architecture",
                ],
            },
            {
                "name": "finding",
                "description": "An empirical result",
                "examples": [
                    "scaling law observation",
                    "ablation result",
                ],
            },
            {
                "name": "methodology",
                "description": "A research method",
                "examples": ["RCT", "meta-analysis"],
            },
            {
                "name": "dataset",
                "description": "A data collection",
                "examples": ["ImageNet", "CommonCrawl"],
            },
            {
                "name": "researcher",
                "description": "A named researcher",
                "examples": ["Hinton", "Bengio"],
            },
            {
                "name": "institution",
                "description": "A research institution",
                "examples": ["DeepMind", "Stanford NLP"],
            },
            {
                "name": "publication",
                "description": "A paper or report",
                "examples": [
                    "Attention Is All You Need",
                    "GPT-4 tech report",
                ],
            },
            {
                "name": "claim",
                "description": "An asserted proposition",
                "examples": [
                    "LLMs can reason",
                    "scaling improves performance",
                ],
            },
            {
                "name": "evidence",
                "description": (
                    "Supporting or refuting data"
                ),
                "examples": [
                    "benchmark score",
                    "case study",
                ],
            },
            {
                "name": "framework",
                "description": (
                    "A conceptual or software framework"
                ),
                "examples": ["PyTorch", "BERT"],
            },
        ],
        "relationship_types": [
            {
                "name": "supports",
                "description": "Provides evidence for",
                "examples": ["finding supports claim"],
                "parent_category": "epistemic",
            },
            {
                "name": "contradicts",
                "description": "Provides counter-evidence",
                "examples": [
                    "finding contradicts claim",
                ],
                "parent_category": "epistemic",
            },
            {
                "name": "extends",
                "description": "Builds upon",
                "examples": [
                    "theory extends framework",
                ],
                "parent_category": "temporal",
            },
            {
                "name": "cites",
                "description": "References as prior work",
                "examples": ["paper cites paper"],
                "parent_category": "epistemic",
            },
            {
                "name": "derived_from",
                "description": (
                    "Originates from or based on"
                ),
                "examples": [
                    "method derived_from theory",
                ],
                "parent_category": "dependency",
            },
            {
                "name": "applied_in",
                "description": "Used or tested in context",
                "examples": ["method applied_in study"],
                "parent_category": "realization",
            },
            {
                "name": "measured_by",
                "description": "Evaluated using",
                "examples": [
                    "performance measured_by benchmark",
                ],
                "parent_category": "realization",
            },
            {
                "name": "challenges",
                "description": "Raises questions about",
                "examples": [
                    "evidence challenges assumption",
                ],
                "parent_category": "epistemic",
            },
            {
                "name": "synthesizes",
                "description": "Combines or integrates",
                "examples": [
                    "review synthesizes findings",
                ],
                "parent_category": "compositional",
            },
            {
                "name": "related_to",
                "description": "General thematic relation",
                "examples": [
                    "concept related_to concept",
                ],
                "parent_category": "structural",
            },
        ],
    },
    "regulatory_analysis": {
        "name": "Regulatory Analysis",
        "description": (
            "Legal frameworks, compliance requirements,"
            " and governance structures."
        ),
        "entity_types": [
            {
                "name": "regulation",
                "description": (
                    "A law, act, or regulatory instrument"
                ),
                "examples": [
                    "EU AI Act",
                    "GDPR Article 22",
                ],
            },
            {
                "name": "requirement",
                "description": (
                    "A specific obligation or mandate"
                ),
                "examples": [
                    "transparency obligation",
                    "impact assessment",
                ],
            },
            {
                "name": "obligation",
                "description": (
                    "A duty imposed on a party"
                ),
                "examples": [
                    "notify within 72 hours",
                    "maintain documentation",
                ],
            },
            {
                "name": "risk_category",
                "description": (
                    "A classification of risk level"
                ),
                "examples": [
                    "high-risk AI",
                    "minimal risk",
                ],
            },
            {
                "name": "governance_body",
                "description": (
                    "An authority or oversight entity"
                ),
                "examples": ["AI Board", "DPA"],
            },
            {
                "name": "enforcement_mechanism",
                "description": (
                    "A tool for compliance enforcement"
                ),
                "examples": ["fine", "market withdrawal"],
            },
            {
                "name": "compliance_process",
                "description": (
                    "A procedure for achieving compliance"
                ),
                "examples": [
                    "conformity assessment",
                    "audit",
                ],
            },
            {
                "name": "stakeholder_role",
                "description": (
                    "A role in the regulatory framework"
                ),
                "examples": [
                    "provider",
                    "deployer",
                    "importer",
                ],
            },
            {
                "name": "standard",
                "description": (
                    "A technical or process standard"
                ),
                "examples": [
                    "ISO 42001",
                    "harmonised standard",
                ],
            },
            {
                "name": "exemption",
                "description": "An exception to a rule",
                "examples": [
                    "research exemption",
                    "military exemption",
                ],
            },
            {
                "name": "penalty",
                "description": (
                    "A consequence for non-compliance"
                ),
                "examples": [
                    "35M EUR fine",
                    "ban from market",
                ],
            },
            {
                "name": "jurisdiction",
                "description": (
                    "A geographic or legal scope"
                ),
                "examples": [
                    "EU member states",
                    "third countries",
                ],
            },
        ],
        "relationship_types": [
            {
                "name": "governs",
                "description": "Sets rules for",
                "examples": [
                    "regulation governs domain",
                ],
                "parent_category": "governance",
            },
            {
                "name": "requires",
                "description": "Mandates compliance with",
                "examples": [
                    "regulation requires assessment",
                ],
                "parent_category": "governance",
            },
            {
                "name": "enforces",
                "description": "Has authority to enforce",
                "examples": [
                    "body enforces regulation",
                ],
                "parent_category": "governance",
            },
            {
                "name": "classifies",
                "description": "Categorizes or labels",
                "examples": [
                    "framework classifies system",
                ],
                "parent_category": "structural",
            },
            {
                "name": "exempts",
                "description": "Provides exception from",
                "examples": [
                    "clause exempts use case",
                ],
                "parent_category": "governance",
            },
            {
                "name": "applies_to",
                "description": (
                    "Is relevant to or targets"
                ),
                "examples": [
                    "rule applies_to provider",
                ],
                "parent_category": "governance",
            },
            {
                "name": "overlaps_with",
                "description": (
                    "Shares scope or requirements"
                ),
                "examples": [
                    "GDPR overlaps_with AI Act",
                ],
                "parent_category": "structural",
            },
            {
                "name": "contradicts",
                "description": "Conflicts with",
                "examples": [
                    "requirement contradicts exemption",
                ],
                "parent_category": "epistemic",
            },
            {
                "name": "implements",
                "description": "Realizes or satisfies",
                "examples": [
                    "process implements requirement",
                ],
                "parent_category": "realization",
            },
            {
                "name": "supersedes",
                "description": "Replaces or updates",
                "examples": [
                    "amendment supersedes clause",
                ],
                "parent_category": "temporal",
            },
            {
                "name": "delegates_to",
                "description": "Assigns authority to",
                "examples": [
                    "regulation delegates_to body",
                ],
                "parent_category": "governance",
            },
            {
                "name": "establishes",
                "description": "Creates or defines",
                "examples": ["act establishes body"],
                "parent_category": "realization",
            },
        ],
    },
}


def get_template(template_id: str) -> dict[str, Any] | None:
    """Get a template by ID."""
    return TEMPLATES.get(template_id)


def list_templates() -> list[dict[str, Any]]:
    """List all available templates with metadata."""
    return [
        {
            "template_id": tid,
            "name": t["name"],
            "description": t["description"],
            "entity_type_count": len(t["entity_types"]),
            "relationship_type_count": len(t["relationship_types"]),
        }
        for tid, t in TEMPLATES.items()
    ]


async def populate_schema(
    pool: asyncpg.Pool,
    engagement_id: UUID,
    template_id: str,
) -> int:
    """Populate engagement_schema from a template. Returns count of entries created."""
    template = TEMPLATES.get(template_id)
    if template is None:
        raise ValueError(f"Unknown template: {template_id}")

    count = 0
    async with pool.acquire() as conn:
        for et in template["entity_types"]:
            await conn.execute(
                """
                INSERT INTO engagement_schema
                    (engagement_id, kind, name, description, examples)
                VALUES ($1, 'entity_type', $2, $3, $4)
                ON CONFLICT (engagement_id, kind, name) DO NOTHING
                """,
                engagement_id,
                et["name"],
                et["description"],
                et.get("examples", []),
            )
            count += 1
        for rt in template["relationship_types"]:
            await conn.execute(
                """
                INSERT INTO engagement_schema
                    (engagement_id, kind, name, description, examples, parent_category)
                VALUES ($1, 'relationship_type', $2, $3, $4, $5)
                ON CONFLICT (engagement_id, kind, name) DO NOTHING
                """,
                engagement_id,
                rt["name"],
                rt["description"],
                rt.get("examples", []),
                rt.get("parent_category"),
            )
            count += 1
    return count
