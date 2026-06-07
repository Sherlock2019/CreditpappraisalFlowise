CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    customer_type TEXT,
    industry TEXT,
    country TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    document_type TEXT,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT DEFAULT 'uploaded',
    source_type TEXT DEFAULT 'manual_upload',
    source_uri TEXT,
    external_document_id TEXT,
    source_metadata JSONB DEFAULT '{}'::jsonb,
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER,
    page_number INTEGER,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES chat_sessions(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_assessments (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    risk_level TEXT,
    score INTEGER,
    summary TEXT,
    strengths TEXT,
    weaknesses TEXT,
    missing_documents TEXT,
    human_review_required BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_appraisals (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    asset_name TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    description TEXT,
    appraised_value DOUBLE PRECISION NOT NULL,
    currency TEXT DEFAULT 'USD',
    valuation_method TEXT DEFAULT 'market_comparison',
    haircut_pct DOUBLE PRECISION DEFAULT 20,
    collateral_value DOUBLE PRECISION NOT NULL,
    confidence_score INTEGER DEFAULT 75,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    customer_id INTEGER,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS loan_policy_scores (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    assessment_id TEXT,
    dti_pct DOUBLE PRECISION,
    dti_band TEXT,
    ltv_pct DOUBLE PRECISION,
    ltv_band TEXT,
    base_rate_pct DOUBLE PRECISION,
    risk_spread_pct DOUBLE PRECISION,
    estimated_annual_rate_pct DOUBLE PRECISION,
    estimated_monthly_payment DOUBLE PRECISION,
    recommendation TEXT,
    committee_required BOOLEAN DEFAULT FALSE,
    fraud_severity INTEGER DEFAULT 0,
    reason_codes JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS approval_committee_cases (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    assessment_id TEXT,
    policy_score_id INTEGER,
    status TEXT DEFAULT 'submitted_to_committee',
    submitted_by TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS final_decisions (
    id SERIAL PRIMARY KEY,
    committee_case_id TEXT,
    customer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    approved_amount DOUBLE PRECISION,
    approved_rate_pct DOUBLE PRECISION,
    conditions JSONB DEFAULT '[]'::jsonb,
    decision_by TEXT NOT NULL,
    decision_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decision_email_drafts (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    decision_id TEXT,
    customer_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    send_allowed BOOLEAN DEFAULT FALSE,
    requires_human_approval BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual_upload';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_uri TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS external_document_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_documents_customer_id ON documents(customer_id);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_external_document_id ON documents(external_document_id);
CREATE INDEX IF NOT EXISTS idx_asset_appraisals_customer_id ON asset_appraisals(customer_id);
CREATE INDEX IF NOT EXISTS idx_asset_appraisals_asset_class ON asset_appraisals(asset_class);
CREATE INDEX IF NOT EXISTS idx_chunks_customer_id ON document_chunks(customer_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_loan_policy_scores_customer_id ON loan_policy_scores(customer_id);
CREATE INDEX IF NOT EXISTS idx_approval_committee_cases_customer_id ON approval_committee_cases(customer_id);
CREATE INDEX IF NOT EXISTS idx_final_decisions_customer_id ON final_decisions(customer_id);
CREATE INDEX IF NOT EXISTS idx_decision_email_drafts_customer_id ON decision_email_drafts(customer_id);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
ON document_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
