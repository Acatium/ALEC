import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useCallback, useState } from "react";
import { get, post, patch, del } from "./client";
import type {
  Engagement,
  EngagementCreate,
  AnalyzeRequest,
  AnalyzeResponse,
  Entity,
  Relationship,
  Observation,
  GraphData,
  PaginatedResponse,
  ALECEvent,
  TaskItem,
  EngagementStats,
  ConsolidatedUnit,
  EntityDetail,
  SourceConfig,
  Annotation,
  Question,
  Snapshot,
  Report,
  SchemaEntry,
  SchemaProposal,
  EngagementTemplate,
} from "./types";

export function useEngagements() {
  return useQuery({
    queryKey: ["engagements"],
    queryFn: () => get<Engagement[]>("/engagements"),
    refetchInterval: 5000,
  });
}

export function useEngagement(id: string) {
  return useQuery({
    queryKey: ["engagement", id],
    queryFn: () => get<Engagement>(`/engagements/${id}`),
    refetchInterval: 3000,
  });
}

export function useCreateEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EngagementCreate) =>
      post<Engagement>("/engagements", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["engagements"] }),
  });
}

export function useAnalyzeEngagement() {
  return useMutation({
    mutationFn: (data: AnalyzeRequest) =>
      post<AnalyzeResponse>("/engagements/analyze", data),
  });
}

export function useDeleteEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => del(`/engagements/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["engagements"] }),
  });
}

export function useRestartEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      post<Engagement>(`/engagements/${id}/restart`, {}),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["engagements"] });
      qc.invalidateQueries({ queryKey: ["engagement", id] });
    },
  });
}

export function useEntities(engagementId: string, offset = 0, limit = 50) {
  return useQuery({
    queryKey: ["entities", engagementId, offset, limit],
    queryFn: () =>
      get<PaginatedResponse<Entity>>(
        `/engagements/${engagementId}/entities?offset=${offset}&limit=${limit}`,
      ),
    refetchInterval: 5000,
  });
}

export function useRelationships(
  engagementId: string,
  offset = 0,
  limit = 50,
) {
  return useQuery({
    queryKey: ["relationships", engagementId, offset, limit],
    queryFn: () =>
      get<PaginatedResponse<Relationship>>(
        `/engagements/${engagementId}/relationships?offset=${offset}&limit=${limit}`,
      ),
    refetchInterval: 5000,
  });
}

export function useObservations(
  engagementId: string,
  offset = 0,
  limit = 50,
) {
  return useQuery({
    queryKey: ["observations", engagementId, offset, limit],
    queryFn: () =>
      get<PaginatedResponse<Observation>>(
        `/engagements/${engagementId}/observations?offset=${offset}&limit=${limit}`,
      ),
    refetchInterval: 5000,
  });
}

export function useGraph(
  engagementId: string,
  entityTypes?: string,
  minObservations?: number,
) {
  const params = new URLSearchParams();
  if (entityTypes) params.set("entity_types", entityTypes);
  if (minObservations && minObservations > 0)
    params.set("min_observations", String(minObservations));
  const qs = params.toString();
  const url = `/engagements/${engagementId}/graph${qs ? `?${qs}` : ""}`;

  return useQuery({
    queryKey: ["graph", engagementId, entityTypes, minObservations],
    queryFn: () => get<GraphData>(url),
    refetchInterval: 5000,
  });
}

// --- New hooks ---

export function useTimeline(engagementId: string) {
  return useQuery({
    queryKey: ["timeline", engagementId],
    queryFn: () =>
      get<TaskItem[]>(`/engagements/${engagementId}/timeline`),
    refetchInterval: 5000,
  });
}

export function useStats(engagementId: string) {
  return useQuery({
    queryKey: ["stats", engagementId],
    queryFn: () =>
      get<EngagementStats>(`/engagements/${engagementId}/stats`),
    refetchInterval: 5000,
  });
}

export function useConsolidated(engagementId: string) {
  return useQuery({
    queryKey: ["consolidated", engagementId],
    queryFn: () =>
      get<ConsolidatedUnit[]>(`/engagements/${engagementId}/consolidated`),
    refetchInterval: 10000,
  });
}

export function useEntityDetail(
  engagementId: string,
  entityId: string | null,
) {
  return useQuery({
    queryKey: ["entityDetail", engagementId, entityId],
    queryFn: () =>
      get<EntityDetail>(
        `/engagements/${engagementId}/entities/${entityId}`,
      ),
    enabled: !!entityId,
  });
}

// --- Engagement editing ---

export function useUpdateEngagement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { name?: string; problem_statement?: string; summary?: string };
    }) => patch<Engagement>(`/engagements/${id}`, data),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["engagement", id] });
      qc.invalidateQueries({ queryKey: ["engagements"] });
    },
  });
}

// --- Source management ---

export function useSources(engagementId: string) {
  return useQuery({
    queryKey: ["sources", engagementId],
    queryFn: () =>
      get<SourceConfig[]>(`/engagements/${engagementId}/sources`),
    refetchInterval: 10000,
  });
}

export function useAddSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      source,
    }: {
      engagementId: string;
      source: string;
    }) =>
      post<SourceConfig>(`/engagements/${engagementId}/sources`, { source }),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["sources", engagementId] });
      qc.invalidateQueries({ queryKey: ["stats", engagementId] });
    },
  });
}

export function useUpdateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      sourceConfigId,
      data,
    }: {
      engagementId: string;
      sourceConfigId: string;
      data: { status?: string; priority?: number; trust_tier?: string };
    }) =>
      patch<SourceConfig>(
        `/engagements/${engagementId}/sources/${sourceConfigId}`,
        data,
      ),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["sources", engagementId] });
    },
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      sourceConfigId,
    }: {
      engagementId: string;
      sourceConfigId: string;
    }) => del(`/engagements/${engagementId}/sources/${sourceConfigId}`),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["sources", engagementId] });
      qc.invalidateQueries({ queryKey: ["stats", engagementId] });
    },
  });
}

// --- Annotations ---

export function useAnnotations(engagementId: string) {
  return useQuery({
    queryKey: ["annotations", engagementId],
    queryFn: () =>
      get<Annotation[]>(`/engagements/${engagementId}/annotations`),
    refetchInterval: 10000,
  });
}

export function useCreateAnnotation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      data,
    }: {
      engagementId: string;
      data: {
        entity_id: string;
        annotation_type: string;
        content?: string;
      };
    }) =>
      post<Annotation>(`/engagements/${engagementId}/annotations`, data),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["annotations", engagementId] });
    },
  });
}

export function useDeleteAnnotation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      annotationId,
    }: {
      engagementId: string;
      annotationId: string;
    }) =>
      del(`/engagements/${engagementId}/annotations/${annotationId}`),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["annotations", engagementId] });
    },
  });
}

// --- Entity corrections ---

export function useUpdateEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      entityId,
      data,
    }: {
      engagementId: string;
      entityId: string;
      data: { name?: string; entity_type?: string };
    }) =>
      patch<Entity>(
        `/engagements/${engagementId}/entities/${entityId}`,
        data,
      ),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["entities", engagementId] });
      qc.invalidateQueries({ queryKey: ["graph", engagementId] });
      qc.invalidateQueries({ queryKey: ["stats", engagementId] });
    },
  });
}

export function useMergeEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      targetEntityId,
      sourceEntityId,
    }: {
      engagementId: string;
      targetEntityId: string;
      sourceEntityId: string;
    }) =>
      post<Entity>(
        `/engagements/${engagementId}/entities/${targetEntityId}/merge`,
        { source_entity_id: sourceEntityId },
      ),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["entities", engagementId] });
      qc.invalidateQueries({ queryKey: ["graph", engagementId] });
      qc.invalidateQueries({ queryKey: ["stats", engagementId] });
    },
  });
}

// --- Manual directives ---

export function useCreateDirective() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      data,
    }: {
      engagementId: string;
      data: { directive: string; source_ref?: string; max_scope?: string };
    }) =>
      post<TaskItem>(`/engagements/${engagementId}/directives`, data),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["timeline", engagementId] });
    },
  });
}

// --- Questions ---

export function useQuestions(engagementId: string) {
  return useQuery({
    queryKey: ["questions", engagementId],
    queryFn: () =>
      get<Question[]>(`/engagements/${engagementId}/questions`),
    refetchInterval: 10000,
  });
}

export function useCreateQuestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      question_text,
    }: {
      engagementId: string;
      question_text: string;
    }) =>
      post<Question>(`/engagements/${engagementId}/questions`, {
        question_text,
      }),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["questions", engagementId] });
    },
  });
}

export function useUpdateQuestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      questionId,
      data,
    }: {
      engagementId: string;
      questionId: string;
      data: { status?: string; answer?: string };
    }) =>
      patch<Question>(
        `/engagements/${engagementId}/questions/${questionId}`,
        data,
      ),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["questions", engagementId] });
    },
  });
}

export function useDeleteQuestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      questionId,
    }: {
      engagementId: string;
      questionId: string;
    }) => del(`/engagements/${engagementId}/questions/${questionId}`),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["questions", engagementId] });
    },
  });
}

// --- Snapshots ---

export function useSnapshots(engagementId: string) {
  return useQuery({
    queryKey: ["snapshots", engagementId],
    queryFn: () =>
      get<Snapshot[]>(`/engagements/${engagementId}/snapshots`),
  });
}

export function useCreateSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      data,
    }: {
      engagementId: string;
      data: { name: string; description?: string };
    }) =>
      post<Snapshot>(`/engagements/${engagementId}/snapshots`, data),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["snapshots", engagementId] });
    },
  });
}

// --- Schema ---

export function useSchema(engagementId: string) {
  return useQuery({
    queryKey: ["schema", engagementId],
    queryFn: () =>
      get<SchemaEntry[]>(`/engagements/${engagementId}/schema`),
    refetchInterval: 30000,
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: () => get<EngagementTemplate[]>("/templates"),
  });
}

export function useAddSchemaEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      data,
    }: {
      engagementId: string;
      data: {
        kind: string;
        name: string;
        description?: string;
        examples?: string[];
        parent_category?: string;
      };
    }) =>
      post<SchemaEntry>(`/engagements/${engagementId}/schema`, data),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["schema", engagementId] });
    },
  });
}

export function useApplyTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      engagementId,
      templateId,
    }: {
      engagementId: string;
      templateId: string;
    }) =>
      post<SchemaEntry[]>(
        `/engagements/${engagementId}/schema/apply-template`,
        { template_id: templateId },
      ),
    onSuccess: (_data, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ["schema", engagementId] });
    },
  });
}

export function useProposeSchema() {
  return useMutation({
    mutationFn: (engagementId: string) =>
      post<SchemaProposal>(
        `/engagements/${engagementId}/schema/propose`,
        {},
      ),
  });
}

// --- Report ---

export function useReport(engagementId: string, enabled = false) {
  return useQuery({
    queryKey: ["report", engagementId],
    queryFn: () =>
      get<Report>(`/engagements/${engagementId}/report`),
    enabled,
  });
}

// --- WebSocket ---

export function useWebSocket(engagementId: string) {
  const [events, setEvents] = useState<ALECEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const qc = useQueryClient();

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/ws/${engagementId}`,
    );
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const event: ALECEvent = JSON.parse(e.data);
      setEvents((prev) => [...prev.slice(-99), event]);

      if (
        event.event_type === "worker.completed" ||
        event.event_type === "cycle.completed" ||
        event.event_type === "consolidation.completed"
      ) {
        qc.invalidateQueries({ queryKey: ["engagement", engagementId] });
        qc.invalidateQueries({ queryKey: ["entities", engagementId] });
        qc.invalidateQueries({ queryKey: ["relationships", engagementId] });
        qc.invalidateQueries({ queryKey: ["graph", engagementId] });
        qc.invalidateQueries({ queryKey: ["timeline", engagementId] });
        qc.invalidateQueries({ queryKey: ["stats", engagementId] });
        qc.invalidateQueries({ queryKey: ["consolidated", engagementId] });
      }
    };

    ws.onclose = () => {
      if (mountedRef.current) {
        timerRef.current = setTimeout(connect, 3000);
      }
    };
  }, [engagementId, qc]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events };
}
