export interface PortalUser {
    id: string;
    email: string;
    display_name: string;
    timezone: string;
    role: "admin" | "user";
}
export interface PortalProfile {
    version: number;
    recipient_email: string;
    reminder_time: string;
    timezone: string;
    email_enabled: boolean;
    ai_billing_approved: boolean;
    review_preferences?: {
        strategy?: "fsrs" | "ebbinghaus";
        intervals_days?: number[];
        learning_goal?: string;
        learning_preference?: string;
    };
    onboarding_step: number;
    onboarding_completed_at: string | null;
    email_settings: {
        provider?: string;
        host?: string;
        username?: string;
        port?: number;
        security?: string;
    };
}
export interface PortalSource {
    subject_id: string;
    id: string;
    name: string;
    external_source_id: string;
    source_type: string;
    status_property: string;
    status_mapping: Record<string, string>;
    last_sync_at: string | null;
}
export interface WorkspaceData {
    user: PortalUser;
    profile: PortalProfile;
    notion_configured: boolean;
    smtp_configured: boolean;
    model_key_configured: boolean;
    sources: PortalSource[];
    model: {
        provider: string;
        model_name: string;
        base_url: string | null;
    } | null;
    channels: {
        id: string;
        name: string;
        available: boolean;
    }[];
    subjects: {
        id: string;
        name: string;
        count: number;
    }[];
    chapters: {
        id: string;
        title: string;
        subject_id: string;
        status: string;
        content: string;
        source_url: string | null;
        version: number;
    }[];
    knowledge_total: number;
    mail_history: {
        id: string;
        title: string;
        status: string;
        attempts: number;
        error_code: string | null;
        sent_at: string | null;
        created_at: string;
    }[];
    sync_history: {
        id: string;
        status: string;
        imported: number;
        created_at: string;
        error: string | null;
    }[];
}
export interface DiscoveredSource {
    id: string;
    name: string;
    properties: {
        name: string;
        type: string;
        options: string[];
    }[];
}
export interface ReviewTask {
    id: string;
    knowledge_point_id: string;
    status: string;
    version: number;
    knowledge_title?: string;
    subject_id?: string | null;
    scheduled_due_at?: string;
}
export interface ProcessingProgress {
    automatic_processing_enabled: boolean;
    notes: {
        chapter_id: string;
        title: string;
        source_url: string | null;
        notion_archived_at: string | null;
        learning_status: string;
        status: string | null;
        error_code: string | null;
        next_attempt_at: string | null;
        note_summary: string | null;
        information_sufficient: boolean | null;
        limitations: string[];
        knowledge_point_ids: string[];
        evidence: {
            knowledge_point_id: string;
            source_quote: string;
            source_start: number;
            source_end: number;
            concepts: string[];
            terms: string[];
            relationships: string[];
            prerequisites: string[];
            pitfalls: string[];
            key_points: string[];
            applications: string[];
            review_suggestion: string;
        }[];
    }[];
    sync_runs: {
        id: string;
        source_id: string;
        status: string;
        imported: number;
        attempt: number;
        finished_at: string | null;
        next_retry_at: string | null;
        error_code: string | null;
    }[];
}
export interface WorkspaceInsights {
    timezone: string;
    today: string;
    from_date: string;
    to_date: string;
    metrics: {
        knowledge_total: number;
        chapter_total: number;
        chapter_completed: number;
        today_study_seconds: number;
        today_review_seconds: number;
        today_reviews: number;
        today_tasks: number;
        today_completed_tasks: number;
        pending_reviews: number;
        overdue_reviews: number;
        learning_days: number;
        streak_days: number;
        recall_rate: number | null;
        review_total: number;
    };
    activity: {
        date: string;
        study_seconds: number;
        review_seconds: number;
        reviews: number;
        recalled: number;
    }[];
    subjects: {
        id: string;
        name: string;
        knowledge_count: number;
        chapter_count: number;
        completed_chapters: number;
    }[];
    memory: {
        key: string;
        name: string;
        count: number;
    }[];
    scheduled: {
        date: string;
        count: number;
        fsrs: number;
        ebbinghaus: number;
    }[];
    upcoming: {
        date: string;
        count: number;
        fsrs: number;
        ebbinghaus: number;
    }[];
}
export interface PortalPoint {
    id: string;
    subject_id: string;
    title: string;
    body: string;
    summary: string;
    source_url: string | null;
    manual_revision: boolean;
    status?: string;
    tags?: string[];
}
export interface ReviewContent {
    task: ReviewTask;
    knowledge: {
        title: string;
        body: string;
        source_url: string | null;
    };
    review_item: {
        question: string;
        answer: string;
        explanation: string;
    } | null;
    schedule: {
        review_count: number;
        strategy: string;
        interval_index: number;
        due_at: string;
    } | null;
}
export function learningDestination(value: string | null): string {
    if (!value)
        return "/app";
    try {
        const url = new URL(value, "https://memory.local");
        if (url.origin === "https://memory.local" && url.pathname === "/app")
            return url.pathname + url.search;
    }
    catch {
        // Invalid destinations fall back to the signed-in learning space.
    }
    return "/app";
}
export async function webApi<T = unknown>(path: string, options: {
    method?: string;
    body?: unknown;
    version?: number;
    key?: string;
} = {}): Promise<T> {
    const method = options.method || "GET";
    const headers: Record<string, string> = {
        Accept: "application/json",
        "X-Memory-Client": "web",
    };
    if (options.body !== undefined)
        headers["Content-Type"] = "application/json";
    if (method === "POST")
        headers["Idempotency-Key"] = options.key || crypto.randomUUID();
    if (options.version !== undefined)
        headers["If-Match"] = `"${options.version}"`;
    const response = await fetch("/api/v1" + path, {
        method,
        headers,
        credentials: "include",
        cache: "no-store",
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
    if (!response.ok) {
        const result = await response.json().catch(() => null);
        throw new Error(result?.error?.message || "请求失败，请稍后重试");
    }
    return response.status === 204 ? (undefined as T) : response.json();
}
