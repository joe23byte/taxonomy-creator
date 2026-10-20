-- Intent Studio initial schema

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_format TEXT NOT NULL,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL UNIQUE,
    import_id INTEGER REFERENCES imports(id),
    seq INTEGER NOT NULL,
    channel TEXT,
    segment TEXT,
    language TEXT,
    timestamp TEXT,
    queue TEXT,
    turns_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    -- pending | processing | processed | failed
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT,
    no_intent_reason TEXT,
    error TEXT,
    processed_at TEXT,
    processed_order INTEGER,
    batch_index INTEGER,
    review_flag INTEGER NOT NULL DEFAULT 0,
    review_unclassified INTEGER NOT NULL DEFAULT 0,
    reviewer_notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interactions_status ON interactions(status);

CREATE TABLE IF NOT EXISTS taxonomy_nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id TEXT REFERENCES taxonomy_nodes(id),
    level INTEGER NOT NULL,
    -- predefined | ai | manual
    source TEXT NOT NULL,
    -- active | proposed | rejected | merged | split | retired
    status TEXT NOT NULL DEFAULT 'active',
    merged_into TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_version INTEGER NOT NULL DEFAULT 1,
    support_at_description INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON taxonomy_nodes(parent_id);

CREATE TABLE IF NOT EXISTS taxonomy_versions (
    version INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL
);

-- Unified history of proposals and applied structural changes
CREATE TABLE IF NOT EXISTS taxonomy_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    node_id TEXT,
    -- create | update | refine | merge | split | retire | move
    change_type TEXT NOT NULL,
    previous_json TEXT,
    proposed_json TEXT NOT NULL,
    -- proposed | auto_accepted | accepted | rejected | superseded
    status TEXT NOT NULL,
    rationale TEXT,
    -- ai | user
    source TEXT NOT NULL,
    run_id INTEGER,
    decided_at TEXT,
    version INTEGER
);
CREATE INDEX IF NOT EXISTS idx_changes_status ON taxonomy_changes(status);

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(model, text_hash)
);

-- Atomic intents extracted from one interaction
CREATE TABLE IF NOT EXISTS intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    intent_text TEXT NOT NULL,
    evidence TEXT,
    evidence_verified INTEGER NOT NULL DEFAULT 0,
    reasoning TEXT,
    suggested_l2_id TEXT,
    embedding_id INTEGER REFERENCES embeddings(id),
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intents_interaction ON intents(interaction_id);

-- One assignment per extracted intent (many-to-many interaction <-> category)
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id INTEGER NOT NULL UNIQUE REFERENCES intents(id) ON DELETE CASCADE,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    l1_id TEXT,
    l2_id TEXT,
    l3_id TEXT,
    l4_id TEXT,
    similarity REAL,
    -- llm_extraction | embedding_match | cluster | llm_cluster_match | llm_outlier | proposal | manual
    method TEXT NOT NULL,
    -- pending | confirmed | corrected | unclassified
    review_status TEXT NOT NULL DEFAULT 'pending',
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reason TEXT,
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    ai_original_json TEXT,
    reviewer_notes TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assign_interaction ON assignments(interaction_id);
CREATE INDEX IF NOT EXISTS idx_assign_l4 ON assignments(l4_id);
CREATE INDEX IF NOT EXISTS idx_assign_l2 ON assignments(l2_id);

CREATE TABLE IF NOT EXISTS assignment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- running | paused | stopping | stopped | completed | failed | interrupted
    status TEXT NOT NULL,
    job TEXT NOT NULL DEFAULT 'analysis',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    settings_json TEXT NOT NULL,
    total_target INTEGER NOT NULL DEFAULT 0,
    processed_in_run INTEGER NOT NULL DEFAULT 0,
    current_interaction TEXT,
    current_step TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS batch_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    batch_index INTEGER NOT NULL,
    processed_total INTEGER NOT NULL,
    interactions_in_batch INTEGER NOT NULL,
    intents_extracted INTEGER NOT NULL,
    new_l3 INTEGER NOT NULL,
    new_l4 INTEGER NOT NULL,
    total_l3 INTEGER NOT NULL,
    total_l4 INTEGER NOT NULL,
    proposals_created INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    run_id INTEGER,
    kind TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    conversation_id TEXT,
    node_id TEXT,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}'
);
