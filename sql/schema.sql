CREATE TABLE tickets (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
    CONSTRAINT chk_ticket_status
        CHECK (status IN ('OPEN', 'RESOLVED'))
);

CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    amount INT NOT NULL,
    purchase_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    refund_status VARCHAR(32) NOT NULL DEFAULT 'NONE',
    CONSTRAINT chk_order_refund_status
        CHECK (refund_status IN ('NONE', 'REFUNDED'))
);

CREATE TABLE refund_policy (
    id INT PRIMARY KEY,
    refund_window_days INT NOT NULL,
    auto_approval_limit INT NOT NULL
);

CREATE TABLE agent_runs (
    id VARCHAR(64) PRIMARY KEY,
    ticket_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NULL,
    intent VARCHAR(64) NULL,
    current_state VARCHAR(64) NOT NULL,
    policy_passed BOOLEAN NULL,
    approval_status VARCHAR(32) NULL,
    refund_id VARCHAR(64) NULL,
    idempotency_key VARCHAR(128) NULL UNIQUE,
    last_observation TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE refunds (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    amount INT NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    gateway_transaction_id VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT chk_refund_status
        CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED', 'UNKNOWN'))
);

CREATE TABLE gateway_transactions (
    transaction_id VARCHAR(128) PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    order_id VARCHAR(64) NOT NULL,
    amount INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT chk_gateway_transaction_status
        CHECK (status IN ('SUCCESS'))
);
