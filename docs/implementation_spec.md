# Autonomous Refund Operator — Implementation Specification

## 1. Goal

Build a narrow CLI-based autonomous refund operator.

The system receives a customer support ticket and attempts to resolve the requested refund end-to-end.

The system must demonstrate this lifecycle:

```text
Goal
→ Understand
→ Plan
→ Execute
→ Observe
→ Adapt
→ Verify
→ Complete
```

The system must be stateful, resumable, deterministic around high-risk actions, and safe against duplicate refunds.

Do not overengineer.

Do not introduce:

- LangGraph
- LangChain agent orchestration
- ORM
- vector databases
- RAG
- multi-agent systems
- browser automation
- Slack
- email
- background workers
- distributed queues
- event buses
- complex dependency injection frameworks
- web UI

Use:

```text
Python
MySQL
Pydantic
CLI
Raw SQL
LLM API abstraction
YAML configuration
.env secrets
```

---

# 2. Main architectural principle

The LLM is used only where natural-language reasoning is useful.

The LLM must NOT control security-critical workflow transitions.

The deterministic Python orchestration layer is authoritative.

Conceptually:

```text
Customer Ticket
      ↓
Raw Python Orchestrator
      ↓
Load persisted workflow state
      ↓
Execute allowed state handler
      ↓
LLM only where useful
      ↓
Database / refund gateway functions
      ↓
Observe result
      ↓
Persist checkpoint
      ↓
Determine deterministic next state
```

Important rule:

```text
LLM reasons within the workflow.

Python controls the workflow.
```

Critical decisions such as:

- whether approval is required
- whether refund execution is allowed
- whether a timed-out refund should be retried
- whether the ticket may be marked resolved
- what state is resumed after a crash

must be implemented in deterministic Python.

---

# 3. Project structure

Keep the project small and semantic.

Suggested structure:

```text
refund_operator/
│
├── app/
│   ├── __init__.py
│   │
│   ├── cli.py
│   │
│   ├── orchestrator.py
│   │
│   ├── states.py
│   │
│   ├── exceptions.py
│   │
│   ├── config.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── tickets.py
│   │   ├── orders.py
│   │   ├── refund_policy.py
│   │   ├── agent_runs.py
│   │   ├── refunds.py
│   │   └── gateway_transactions.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── ticket.py
│   │   ├── order.py
│   │   ├── refund.py
│   │   ├── agent_run.py
│   │   ├── policy.py
│   │   └── llm.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── factory.py
│   │   ├── base.py
│   │   ├── openrouter.py
│   │   └── gemini.py
│   │
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── understand.py
│   │   ├── planning.py
│   │   ├── policy_check.py
│   │   ├── approval.py
│   │   ├── refund_execution.py
│   │   ├── refund_verification.py
│   │   └── completion.py
│   │
│   └── gateway/
│       ├── __init__.py
│       └── mock_payment_gateway.py
│
├── config/
│   └── settings.yaml
│
├── sql/
│   ├── schema.sql
│   └── seed.sql
│
├── tests/
│   └── ...
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── main.py
```

Do not create additional layers unless needed.

---

# 4. Naming

Use semantic, self-explanatory names.

Prefer:

```python
load_agent_run()
update_agent_run_state()
find_refund_by_idempotency_key()
determine_refund_eligibility()
determine_approval_requirement()
verify_refund_with_gateway()
```

Avoid vague names such as:

```python
process()
handle()
do_work()
run_step()
func1()
data()
result2()
```

Variables should communicate meaning.

Prefer:

```python
customer_ticket
refund_policy
approval_required
gateway_transaction
idempotency_key
```

instead of:

```python
t
p
x
r
obj
```

---

# 5. Database

Use MySQL.

Use raw SQL.

Do not use SQLAlchemy or another ORM.

Use parameterized SQL queries everywhere.

Never create SQL queries by interpolating user input directly.

Example:

```python
cursor.execute(
    """
    SELECT id, order_id, message, status
    FROM tickets
    WHERE id = %s
    """,
    (ticket_id,),
)
```

---

# 6. Tables

Use only the tables required by the agreed design.

There are six tables:

```text
tickets
orders
refund_policy
agent_runs
refunds
gateway_transactions
```

---

# 7. tickets table

Purpose:

Store the customer-facing support ticket.

The customer message is untrusted input.

Schema:

```sql
CREATE TABLE tickets (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
    CONSTRAINT chk_ticket_status
        CHECK (status IN ('OPEN', 'RESOLVED'))
);
```

Valid ticket statuses:

```text
OPEN
RESOLVED
```

Meaning:

```text
OPEN
= requested customer outcome has not yet been verified complete

RESOLVED
= requested customer outcome has been verified complete
```

The ticket remains `OPEN` during:

```text
understanding
planning
policy checking
waiting for approval
refund execution
refund timeout
refund verification
human review
```

Only after refund success is verified may the ticket become:

```text
RESOLVED
```

Do not put workflow statuses into this table.

For example, do not use:

```text
WAITING_APPROVAL
REFUNDING
VERIFYING
PROCESSING
```

Those belong in `agent_runs.current_state`.

---

# 8. orders table

Purpose:

Trusted company-side order information.

Schema:

```sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    amount INT NOT NULL,
    purchase_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    refund_status VARCHAR(32) NOT NULL DEFAULT 'NONE'
);
```

For this POC, keep values minimal.

Order status required by the demo:

```text
DELIVERED
```

Refund status:

```text
NONE
REFUNDED
```

Example:

```text
ORD456
amount = 7500
purchase_date = 2026-09-25
status = DELIVERED
refund_status = NONE
```

The order amount must always come from this trusted table.

Never trust an amount mentioned by the customer.

---

# 9. refund_policy table

Purpose:

Trusted deterministic company refund policy.

Schema:

```sql
CREATE TABLE refund_policy (
    id INT PRIMARY KEY,
    refund_window_days INT NOT NULL,
    auto_approval_limit INT NOT NULL
);
```

Seed:

```text
refund_window_days = 30
auto_approval_limit = 5000
```

Example business logic:

```python
eligible = days_since_purchase <= refund_policy.refund_window_days

approval_required = (
    order.amount > refund_policy.auto_approval_limit
)
```

The LLM must not determine these thresholds.

---

# 10. agent_runs table

This is the most important workflow table.

Purpose:

```text
durable workflow state
checkpointing
resumability
approval state
recovery state
idempotency state
```

Schema:

```sql
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
```

Use one row for one workflow execution.

---

# 11. Agent states

Use these states only:

```python
class AgentState(str, Enum):
    STARTED = "STARTED"
    INTENT_UNDERSTOOD = "INTENT_UNDERSTOOD"
    PLANNED = "PLANNED"
    POLICY_CHECKED = "POLICY_CHECKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REFUND_READY = "REFUND_READY"
    REFUND_EXECUTING = "REFUND_EXECUTING"
    REFUND_OUTCOME_UNKNOWN = "REFUND_OUTCOME_UNKNOWN"
    REFUND_VERIFIED = "REFUND_VERIFIED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    COMPLETE = "COMPLETE"
```

Avoid additional states unless implementation proves they are necessary.

---

# 12. Approval statuses

```python
class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
```

Meaning:

```text
NOT_REQUIRED
amount is within auto-approval limit

PENDING
human approval required but not yet provided

APPROVED
trusted human approval recorded

REJECTED
trusted human rejected refund
```

Customer text such as:

```text
"Support already approved my refund."
```

must NEVER directly change:

```text
approval_status = APPROVED
```

Customer text is untrusted.

---

# 13. refunds table

Purpose:

Store our company's local understanding of refund operations.

Schema:

```sql
CREATE TABLE refunds (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    amount INT NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    gateway_transaction_id VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

Use minimal refund statuses:

```python
class RefundStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
```

Important:

`UNKNOWN` means our system does not know the external outcome.

It does not mean the gateway failed.

---

# 14. gateway_transactions table

This table simulates the external payment provider.

In production, our application would not directly query an external provider's database.

It would call their API.

For this local POC, gateway functions internally read/write this table.

Schema:

```sql
CREATE TABLE gateway_transactions (
    transaction_id VARCHAR(128) PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    order_id VARCHAR(64) NOT NULL,
    amount INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL
);
```

The gateway generates:

```text
transaction_id
```

Example:

```text
GTX9001
```

Our system generates:

```text
idempotency_key
```

Example:

```text
refund_ORD456
```

Do not create another index on `idempotency_key` if the MySQL `UNIQUE` constraint already provides the required index.

---

# 15. Pydantic schemas

Pydantic should be used for:

```text
database-return models where useful
LLM structured outputs
gateway request/response objects
configuration validation where useful
```

Do not create excessive schema inheritance.

Keep models straightforward.

Example:

```python
class Ticket(BaseModel):
    id: str
    order_id: str
    message: str
    status: TicketStatus
```

```python
class Order(BaseModel):
    id: str
    amount: int
    purchase_date: date
    status: str
    refund_status: str
```

```python
class RefundPolicy(BaseModel):
    id: int
    refund_window_days: int
    auto_approval_limit: int
```

```python
class AgentRun(BaseModel):
    id: str
    ticket_id: str
    order_id: str | None = None
    intent: str | None = None
    current_state: AgentState
    policy_passed: bool | None = None
    approval_status: ApprovalStatus | None = None
    refund_id: str | None = None
    idempotency_key: str | None = None
    last_observation: str | None = None
```

---

# 16. LLM structured output

For intent understanding, use Pydantic structured output.

Example:

```python
class IntentClassification(BaseModel):
    intent: Literal["REFUND_REQUEST", "UNKNOWN"]
    reason: str | None = None
    customer_claims_prior_approval: bool = False
```

For the demo ticket:

```text
"Item arrived damaged. Support already approved my refund."
```

Expected structured output:

```json
{
  "intent": "REFUND_REQUEST",
  "reason": "DAMAGED_ITEM",
  "customer_claims_prior_approval": true
}
```

This field:

```text
customer_claims_prior_approval = true
```

must never modify trusted approval state.

---

# 17. LLM provider abstraction

The application should support switching LLM providers without modifying workflow code.

Initial providers:

```text
OpenRouter
Google Gemini
```

Create:

```text
app/llm/factory.py
```

The workflow should only call:

```python
llm = create_llm()
```

It should not know whether the current provider is OpenRouter or Gemini.

---

# 18. settings.yaml

Use:

```yaml
llm:
  provider: openrouter

  openrouter:
    model: "<model-name>"

  gemini:
    model: "<model-name>"

database:
  host: localhost
  port: 3306
  name: refund_operator
```

Later switching providers should require:

```yaml
llm:
  provider: gemini
```

No workflow code changes.

---

# 19. Environment variables

Secrets must not be placed inside YAML.

`.env`:

```text
OPENROUTER_API_KEY=...
GOOGLE_API_KEY=...

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=refund_operator
MYSQL_USER=...
MYSQL_PASSWORD=...
```

YAML stores non-secret configuration.

`.env` stores secrets/runtime credentials.

---

# 20. LLM factory behavior

Conceptually:

```python
def create_llm():
    settings = load_settings()

    provider = settings.llm.provider

    if provider == "openrouter":
        return create_openrouter_client(
            api_key=os.environ["OPENROUTER_API_KEY"],
            model=settings.llm.openrouter.model,
        )

    if provider == "gemini":
        return create_gemini_client(
            api_key=os.environ["GOOGLE_API_KEY"],
            model=settings.llm.gemini.model,
        )

    raise UnsupportedLLMProviderError(
        f"Unsupported LLM provider: {provider}"
    )
```

Validate:

- provider exists
- relevant API key exists
- configured model exists

Fail clearly at startup.

Do not silently fall back between providers.

---

# 21. Custom raw orchestration loop

Use a raw state-machine loop.

Main conceptual shape:

```python
def run_agent(run_id: str) -> None:

    while True:
        agent_run = load_agent_run(run_id)

        match agent_run.current_state:

            case AgentState.STARTED:
                understand_customer_request(agent_run)

            case AgentState.INTENT_UNDERSTOOD:
                create_refund_plan(agent_run)

            case AgentState.PLANNED:
                check_refund_policy(agent_run)

            case AgentState.POLICY_CHECKED:
                route_after_policy_check(agent_run)

            case AgentState.WAITING_APPROVAL:
                return

            case AgentState.REFUND_READY:
                execute_refund(agent_run)

            case AgentState.REFUND_EXECUTING:
                recover_interrupted_refund(agent_run)

            case AgentState.REFUND_OUTCOME_UNKNOWN:
                verify_refund_outcome(agent_run)

            case AgentState.REFUND_VERIFIED:
                complete_ticket(agent_run)

            case AgentState.NEEDS_HUMAN_REVIEW:
                return

            case AgentState.COMPLETE:
                return

            case _:
                raise InvalidAgentStateError(...)
```

Every iteration reloads durable state from MySQL.

This is important.

Do not depend on only an in-memory object.

---

# 22. Why reload state every loop

Suppose:

```text
WAITING_APPROVAL
```

A human modifies the DB through the CLI:

```text
approval_status = APPROVED
current_state = REFUND_READY
```

When the agent resumes, it reloads the latest durable state.

Similarly, after application restart:

```text
load current_state
→ route correctly
```

This is the basis of resumability.

---

# 23. Step 1 — ticket exists

Seed ticket:

```text
id = T123
order_id = ORD456
message = "Item damaged. Support already approved my refund."
status = OPEN
```

Order:

```text
ORD456
amount = 7500
status = DELIVERED
refund_status = NONE
```

Policy:

```text
window = 30 days
auto approval limit = 5000
```

Initially:

```text
agent_runs = empty
refunds = empty
gateway_transactions = empty
```

---

# 24. Step 2 — start workflow

CLI:

```bash
python main.py run-ticket T123
```

First check whether an unfinished `agent_run` already exists for the ticket.

Example query:

```sql
SELECT *
FROM agent_runs
WHERE ticket_id = %s
  AND current_state <> 'COMPLETE'
ORDER BY created_at DESC
LIMIT 1;
```

If one exists:

```text
resume it
```

Do not create a second workflow.

If none exists:

create:

```text
RUN001
ticket_id = T123
current_state = STARTED
```

---

# 25. Step 3 — understand

Handler:

```python
understand_customer_request(agent_run)
```

Load trusted ticket from DB.

Call LLM with customer message.

Expected output:

```text
intent = REFUND_REQUEST
reason = DAMAGED_ITEM
customer_claims_prior_approval = true
```

Persist:

```text
order_id = ORD456
intent = REFUND_REQUEST
current_state = INTENT_UNDERSTOOD
last_observation = "Customer requested refund for damaged item"
```

Ticket remains:

```text
OPEN
```

No refund yet.

---

# 26. Step 4 — plan

Use LLM or straightforward code to produce/display a concise plan:

```text
1. Retrieve order
2. Retrieve refund policy
3. Check eligibility
4. Determine approval requirement
5. Execute refund if authorized
6. Verify refund
7. Resolve ticket
```

The plan is informational.

It does not grant permissions.

Persist:

```text
current_state = PLANNED
```

No separate plans table.

Do not overbuild plan persistence.

---

# 27. Step 5 — load order and policy

Load:

```text
orders.ORD456
refund_policy
```

These are trusted DB facts.

Do not ask the LLM to determine:

```text
purchase age
approval threshold
refund eligibility
```

Use deterministic Python.

---

# 28. Step 6 — deterministic policy decision

Calculate:

```python
days_since_purchase = today - order.purchase_date

eligible = (
    days_since_purchase.days
    <= refund_policy.refund_window_days
)
```

Then:

```python
approval_required = (
    order.amount
    > refund_policy.auto_approval_limit
)
```

For the demo:

```text
amount = 7500
limit = 5000
```

Therefore:

```text
eligible = true
approval_required = true
```

Persist:

```text
policy_passed = true
approval_status = PENDING
current_state = POLICY_CHECKED
```

Then deterministic routing changes state to:

```text
WAITING_APPROVAL
```

---

# 29. Policy failure

If refund is outside policy:

```text
policy_passed = false
```

Do not execute refund.

Do not mark refund successful.

The ticket should remain `OPEN` unless the chosen business semantics explicitly define a rejection as resolving the support ticket.

For this POC, keep it simple:

```text
current_state = NEEDS_HUMAN_REVIEW
ticket.status = OPEN
```

Do not invent automatic rejection workflows beyond this.

---

# 30. Step 7 — waiting for human approval

State:

```text
current_state = WAITING_APPROVAL
approval_status = PENDING
```

Ticket:

```text
OPEN
```

The main agent loop returns.

It is intentionally paused.

CLI should print something like:

```text
Human approval required.

Ticket: T123
Order: ORD456
Refund amount: ₹7500
Auto-approval limit: ₹5000
```

---

# 31. Human approval CLI

Provide a small command such as:

```bash
python main.py approve RUN001
```

or:

```bash
python main.py reject RUN001
```

Approval command must verify:

```text
run exists
current_state == WAITING_APPROVAL
approval_status == PENDING
```

Then:

```text
approval_status = APPROVED
current_state = REFUND_READY
```

Then optionally invoke:

```python
run_agent(run_id)
```

to resume.

---

# 32. Rejection

If human rejects:

```text
approval_status = REJECTED
current_state = NEEDS_HUMAN_REVIEW
```

Do not expose/call the refund function.

Ticket stays:

```text
OPEN
```

---

# 33. Step 8 — create idempotency key

Before executing any financial side effect, create and persist the idempotency key.

Example:

```python
idempotency_key = f"refund_{order.id}"
```

For:

```text
ORD456
```

produce:

```text
refund_ORD456
```

Persist it to `agent_runs` before calling the gateway.

Also create/update local refund row as appropriate.

Example local refund:

```text
id = RF001
order_id = ORD456
amount = 7500
idempotency_key = refund_ORD456
gateway_transaction_id = NULL
status = PENDING
```

The idempotency key must not be regenerated when retrying or recovering.

---

# 34. Step 9 — checkpoint before side effect

Immediately before calling the payment gateway:

```text
current_state = REFUND_EXECUTING
```

Persist this before the function call.

This checkpoint is critical.

Sequence:

```text
persist REFUND_EXECUTING
→ commit DB transaction
→ call payment gateway
```

Not:

```text
call gateway
→ later save REFUND_EXECUTING
```

---

# 35. Mock payment gateway

Use a plain Python function.

No localhost API required.

Example conceptual interface:

```python
def issue_refund(
    order_id: str,
    amount: int,
    idempotency_key: str,
) -> GatewayRefundResult:
    ...
```

The mock gateway internally reads and writes:

```text
gateway_transactions
```

---

# 36. Gateway idempotency behavior

First query:

```sql
SELECT *
FROM gateway_transactions
WHERE idempotency_key = %s;
```

If existing transaction exists:

return the existing transaction.

Do not create another one.

If none exists:

generate:

```text
transaction_id = GTX...
```

Insert:

```text
transaction_id
idempotency_key
order_id
amount
status = SUCCESS
```

This simulates the external provider processing the refund.

---

# 37. Simulated ambiguous timeout

The important demo failure is:

```text
Gateway commits refund successfully
BUT
our application does not receive confirmation
```

Implementation may deliberately raise a timeout after gateway transaction creation.

For example:

```python
gateway_transaction = create_gateway_transaction(...)

if simulate_timeout:
    raise PaymentGatewayTimeoutError(
        "Gateway response timed out after refund commit"
    )

return gateway_transaction
```

Do not simulate timeout by waiting first and only then creating the transaction.

The desired failure is:

```text
side effect succeeded
response failed
```

---

# 38. Refund timeout handling

When `PaymentGatewayTimeoutError` occurs:

Do not mark:

```text
FAILED
```

because the real outcome is unknown.

Instead:

```text
refund.status = UNKNOWN
agent_runs.current_state = REFUND_OUTCOME_UNKNOWN
agent_runs.last_observation =
    "Gateway timed out after refund request; actual outcome is unknown."
```

Ticket remains:

```text
OPEN
```

Do not immediately execute `issue_refund()` again.

---

# 39. Step 10 — verify unknown outcome

Call:

```python
get_refund_status(idempotency_key)
```

This gateway function queries:

```text
gateway_transactions
```

by:

```text
idempotency_key
```

If found:

```text
transaction_id = GTX9001
status = SUCCESS
```

Then update local state.

---

# 40. Verification success

Update local `refunds`:

```text
gateway_transaction_id = GTX9001
status = SUCCESS
```

Update order:

```text
refund_status = REFUNDED
```

Update agent run:

```text
refund_id = RF001
current_state = REFUND_VERIFIED
last_observation = "Refund verified with gateway transaction GTX9001"
```

Ticket is still `OPEN` until completion handler runs.

---

# 41. Verification retries

If gateway status cannot be retrieved:

perform at most three status verification attempts.

Important:

These are status queries.

Not three new refund attempts.

Conceptually:

```python
for attempt_number in range(1, 4):
    try:
        gateway_transaction = get_refund_status(idempotency_key)

        if gateway_transaction is not None:
            verify_success(...)
            return

    except GatewayUnavailableError:
        ...

    sleep(backoff_seconds)
```

Keep backoff simple.

For example:

```text
1 second
2 seconds
3 seconds
```

No complex retry library required unless useful.

---

# 42. Verification still unknown after three attempts

If the system still cannot determine refund status:

```text
current_state = NEEDS_HUMAN_REVIEW
```

Local refund:

```text
status = UNKNOWN
```

Ticket:

```text
OPEN
```

Important:

Do not mark the ticket resolved.

Do not automatically start another refund.

Do not generate a new idempotency key.

CLI should print:

```text
Refund outcome could not be verified safely.
Human review is required.
No additional refund will be issued automatically.
```

---

# 43. Crash recovery

The workflow must survive process termination.

At every significant transition, persist:

```text
current_state
```

to MySQL.

After application restart:

```python
run_agent("RUN001")
```

loads the row and resumes based on persisted state.

No conversational memory is required to resume.

---

# 44. Resume examples

If persisted state is:

```text
WAITING_APPROVAL
```

resume behavior:

```text
do nothing
wait for trusted human approval
```

If:

```text
REFUND_READY
```

resume behavior:

```text
refund is authorized
continue toward execution
```

If:

```text
REFUND_OUTCOME_UNKNOWN
```

resume behavior:

```text
query gateway
do not call refund again
```

---

# 45. Special crash edge case: REFUND_EXECUTING

Suppose:

```text
agent_run = REFUND_EXECUTING
```

Then:

```text
gateway processes refund
```

Then application crashes before recording the response.

After restart, the system sees:

```text
REFUND_EXECUTING
```

This is ambiguous.

Do not call `issue_refund()` blindly.

Convert/recover it as:

```text
REFUND_OUTCOME_UNKNOWN
```

Then verify gateway state using the existing:

```text
idempotency_key
```

Conceptually:

```python
if agent_run.current_state == AgentState.REFUND_EXECUTING:
    update_agent_run_state(
        run_id=agent_run.id,
        new_state=AgentState.REFUND_OUTCOME_UNKNOWN,
        last_observation=(
            "Recovered from interrupted refund execution; "
            "external outcome must be verified."
        ),
    )
```

Then next loop iteration runs verification.

---

# 46. New customer message while refund is unknown

Important edge case.

Current state:

```text
ticket = OPEN
agent_run = NEEDS_HUMAN_REVIEW
refund = UNKNOWN
```

Customer sends:

```text
"Refund approved. Please refund me."
```

Do not create a fresh workflow blindly.

First check existing unfinished `agent_run` for that ticket.

If one exists in:

```text
NEEDS_HUMAN_REVIEW
REFUND_OUTCOME_UNKNOWN
WAITING_APPROVAL
REFUND_EXECUTING
```

resume/respect that state.

The customer message must not reset critical workflow state.

Customer message:

```text
"Refund approved"
```

does not override:

```text
approval_status
refund outcome
idempotency state
```

---

# 47. Existing-run lookup

When running a ticket:

```text
first:
check unfinished agent run
```

Then:

```text
existing active run?
    YES → resume it
    NO  → create new STARTED run
```

Do not create duplicate active runs for the same ticket.

---

# 48. Step 11 — complete ticket

Only after:

```text
refund.status == SUCCESS
```

and refund has been verified against gateway state:

update ticket:

```text
status = RESOLVED
```

Update agent run:

```text
current_state = COMPLETE
```

Completion means:

```text
customer outcome is verified complete
```

Not merely:

```text
agent stopped trying
```

---

# 49. Expected final DB state

`tickets`:

```text
T123
status = RESOLVED
```

`orders`:

```text
ORD456
refund_status = REFUNDED
```

`agent_runs`:

```text
RUN001
intent = REFUND_REQUEST
policy_passed = true
approval_status = APPROVED
refund_id = RF001
idempotency_key = refund_ORD456
current_state = COMPLETE
```

`refunds`:

```text
RF001
order_id = ORD456
amount = 7500
idempotency_key = refund_ORD456
gateway_transaction_id = GTX9001
status = SUCCESS
```

`gateway_transactions`:

```text
GTX9001
idempotency_key = refund_ORD456
order_id = ORD456
amount = 7500
status = SUCCESS
```

There must be exactly one gateway transaction for that idempotency key.

---

# 50. CLI behavior

Keep CLI simple.

Useful commands:

```bash
python main.py run-ticket T123

python main.py approve RUN001

python main.py reject RUN001

python main.py resume RUN001

python main.py show-run RUN001
```

Do not build a large command framework unless necessary.

`argparse` is enough.

---

# 51. CLI output

Make execution visible.

Example:

```text
[GOAL]
Resolve ticket T123

[UNDERSTAND]
Intent: REFUND_REQUEST
Customer claim: prior approval
Trust level: untrusted customer input

[PLAN]
1. Retrieve order
2. Check policy
3. Obtain approval if required
4. Execute refund
5. Verify refund
6. Resolve ticket

[ORDER]
ORD456
Amount: ₹7500

[POLICY]
Refund window: 30 days
Auto approval limit: ₹5000
Eligible: YES
Human approval required: YES

[STATE]
WAITING_APPROVAL
```

After approval:

```text
[APPROVAL]
APPROVED

[EXECUTE]
Refund ID: RF001
Idempotency key: refund_ORD456

[GATEWAY]
Request timed out

[OBSERVE]
External outcome unknown

[ADAPT]
Checking gateway status instead of retrying refund

[VERIFY]
Gateway transaction GTX9001
Status: SUCCESS

[COMPLETE]
Ticket T123 resolved
Refund RF001 verified
```

---

# 52. Exception classes

Use meaningful custom exceptions.

Keep the list small.

Suggested:

```python
class RefundOperatorError(Exception):
    pass


class ConfigurationError(RefundOperatorError):
    pass


class DatabaseError(RefundOperatorError):
    pass


class RecordNotFoundError(RefundOperatorError):
    pass


class InvalidAgentStateError(RefundOperatorError):
    pass


class InvalidStateTransitionError(RefundOperatorError):
    pass


class PaymentGatewayError(RefundOperatorError):
    pass


class PaymentGatewayTimeoutError(PaymentGatewayError):
    pass


class GatewayUnavailableError(PaymentGatewayError):
    pass


class LLMProviderError(RefundOperatorError):
    pass
```

Do not create dozens of tiny exception types.

---

# 53. Exception handling rules

Database:

```text
catch driver exception
rollback transaction
raise meaningful DatabaseError
```

LLM:

```text
do not change workflow state to next state
if required LLM output was not successfully obtained
```

Gateway timeout:

```text
do not treat as FAILED
mark outcome UNKNOWN
```

Missing ticket/order:

```text
stop safely
show clear error
do not perform refund
```

Invalid workflow state:

```text
fail closed
do not guess next action
```

---

# 54. Transaction boundaries

For important DB updates, use explicit transactions.

Example:

Before refund:

```text
create/update local refund row
persist idempotency key
persist REFUND_EXECUTING
COMMIT
```

Only after commit:

```text
call external/mock gateway
```

This guarantees recovery knows a side effect may have been attempted.

Similarly, after successful verification:

update together where practical:

```text
refund.status = SUCCESS
refund.gateway_transaction_id = ...
order.refund_status = REFUNDED
agent_run.current_state = REFUND_VERIFIED
```

Commit.

Then completion handler marks ticket resolved and run complete.

---

# 55. Database connection handling

Create a reusable connection module.

For example:

```python
@contextmanager
def get_database_connection():
    connection = mysql.connector.connect(...)

    try:
        yield connection
    finally:
        connection.close()
```

For transactions:

```python
with get_database_connection() as connection:
    try:
        ...
        connection.commit()
    except Exception:
        connection.rollback()
        raise
```

Do not scatter raw connection configuration across repository files.

---

# 56. Repository functions

Database modules should have focused functions.

Examples:

`tickets.py`

```python
get_ticket_by_id()
update_ticket_status()
```

`orders.py`

```python
get_order_by_id()
update_order_refund_status()
```

`refund_policy.py`

```python
get_active_refund_policy()
```

`agent_runs.py`

```python
create_agent_run()
get_agent_run_by_id()
find_active_agent_run_for_ticket()
update_agent_run()
update_agent_run_state()
```

`refunds.py`

```python
create_refund()
get_refund_by_id()
find_refund_by_idempotency_key()
update_refund_status()
```

`gateway_transactions.py`

```python
create_gateway_transaction()
find_gateway_transaction_by_idempotency_key()
```

Avoid generic:

```python
repository.save()
repository.update_anything()
```

Prefer semantic operations.

---

# 57. LLM usage

The LLM should primarily be used for:

```text
understanding customer text
structured intent classification
possibly generating the small human-readable plan
final natural-language summary if desired
```

Do not use LLM for:

```text
policy arithmetic
approval threshold
state transitions
idempotency decisions
retry counting
refund verification rules
database consistency
```

---

# 58. No unrestricted DB tools for LLM

Do not give the LLM arbitrary SQL execution.

The LLM should never generate SQL against production-style tables.

Application code controls database reads/writes.

For example:

```text
understand node:
Python loads ticket
→ sends message to LLM
→ receives structured output
→ Python persists result
```

Instead of:

```text
LLM decides which SQL query to execute
```

This keeps the POC easy to reason about.

---

# 59. No inner agent loop required for every step

Do not force:

```text
LLM
→ DB tool
→ LLM
→ DB tool
→ LLM
```

for deterministic workflow states.

Use:

```text
Python DB read
→ LLM when needed
→ Python validation
→ Python DB write
```

The autonomous behavior comes from the overall stateful execution and adaptation, not from maximizing LLM calls.

---

# 60. Checkpoint rule

Every important state transition must be persisted before continuing.

Helper:

```python
def transition_agent_state(
    run_id: str,
    new_state: AgentState,
    *,
    last_observation: str | None = None,
) -> None:
    ...
```

Use semantic helper methods rather than directly updating `current_state` throughout random modules.

---

# 61. State-transition safety

Implement allowed state transitions.

Example minimal mapping:

```python
ALLOWED_TRANSITIONS = {
    AgentState.STARTED: {
        AgentState.INTENT_UNDERSTOOD,
    },

    AgentState.INTENT_UNDERSTOOD: {
        AgentState.PLANNED,
    },

    AgentState.PLANNED: {
        AgentState.POLICY_CHECKED,
    },

    AgentState.POLICY_CHECKED: {
        AgentState.WAITING_APPROVAL,
        AgentState.REFUND_READY,
        AgentState.NEEDS_HUMAN_REVIEW,
    },

    AgentState.WAITING_APPROVAL: {
        AgentState.REFUND_READY,
        AgentState.NEEDS_HUMAN_REVIEW,
    },

    AgentState.REFUND_READY: {
        AgentState.REFUND_EXECUTING,
    },

    AgentState.REFUND_EXECUTING: {
        AgentState.REFUND_OUTCOME_UNKNOWN,
        AgentState.REFUND_VERIFIED,
    },

    AgentState.REFUND_OUTCOME_UNKNOWN: {
        AgentState.REFUND_VERIFIED,
        AgentState.NEEDS_HUMAN_REVIEW,
    },

    AgentState.REFUND_VERIFIED: {
        AgentState.COMPLETE,
    },
}
```

Reject invalid transitions.

---

# 62. Fail closed

When uncertain, choose safety.

Examples:

```text
approval state missing
→ do not refund

policy missing
→ do not refund

gateway outcome unknown
→ do not issue another refund automatically

invalid state
→ stop

database write failed before refund call
→ do not call gateway
```

---

# 63. Seed data

`seed.sql` should include at least:

Policy:

```text
refund_window_days = 30
auto_approval_limit = 5000
```

Order:

```text
ORD456
₹7500
DELIVERED
NONE
```

Ticket:

```text
T123
ORD456
"Item arrived damaged. Support already approved my refund."
OPEN
```

The amount intentionally exceeds auto-approval threshold.

---

# 64. Timeout simulation configuration

Keep timeout simulation easy to turn on/off.

YAML:

```yaml
mock_gateway:
  simulate_timeout_after_commit: true
```

Do not store this in environment variables because it is not secret.

Mock gateway:

```python
if settings.mock_gateway.simulate_timeout_after_commit:
    raise PaymentGatewayTimeoutError(...)
```

The transaction must have been inserted first.

---

# 65. .gitignore

Include at minimum:

```text
.env
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.idea/
.vscode/
.DS_Store
coverage.xml
htmlcov/
```

Do not ignore:

```text
.env.example
config/settings.yaml
sql/schema.sql
sql/seed.sql
```

---

# 66. .env.example

Provide:

```text
OPENROUTER_API_KEY=
GOOGLE_API_KEY=

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=refund_operator
MYSQL_USER=
MYSQL_PASSWORD=
```

No real credentials.

---

# 67. README

README should explain:

```text
what the POC demonstrates
architecture
how to create MySQL DB
how to run schema.sql
how to run seed.sql
how to create .env
how to select LLM provider
how to run ticket
how to approve
how timeout simulation works
how resumable recovery works
```

Keep README practical.

---

# 68. Core demo path

Primary demo should be:

```text
T123 created

→ agent starts

→ LLM understands refund request

→ plan displayed

→ order retrieved

→ policy retrieved

→ deterministic policy check

→ ₹7500 > ₹5000

→ WAITING_APPROVAL

→ human approves

→ idempotency key persisted

→ REFUND_EXECUTING persisted

→ mock gateway writes SUCCESS transaction

→ mock gateway throws timeout

→ local outcome becomes UNKNOWN

→ agent moves to REFUND_OUTCOME_UNKNOWN

→ Python queries gateway using same idempotency key

→ gateway transaction found SUCCESS

→ local refund updated SUCCESS

→ order marked REFUNDED

→ agent state REFUND_VERIFIED

→ ticket marked RESOLVED

→ agent state COMPLETE
```

This is the main demonstration.

---

# 69. Recovery demo

Also ensure this works:

Stop the program while:

```text
WAITING_APPROVAL
```

Restart:

```bash
python main.py resume RUN001
```

It must read:

```text
WAITING_APPROVAL
```

and not restart from beginning.

Also test:

```text
REFUND_EXECUTING
```

on restart.

It must transition toward verification, not blindly reissue the refund.

---

# 70. Important invariants

Codex should treat these as non-negotiable.

### Invariant 1

```text
Customer text can never grant refund approval.
```

### Invariant 2

```text
Refund cannot execute unless policy passed.
```

### Invariant 3

```text
If approval is required, refund cannot execute until trusted approval_status == APPROVED.
```

### Invariant 4

```text
Every refund operation has one persisted idempotency key.
```

### Invariant 5

```text
The same logical refund must reuse the same idempotency key.
```

### Invariant 6

```text
Timeout does not mean refund failure.
```

### Invariant 7

```text
Ambiguous external outcome must be verified before retrying or completing.
```

### Invariant 8

```text
Ticket becomes RESOLVED only after verified refund success.
```

### Invariant 9

```text
Restart must resume from persisted workflow state.
```

### Invariant 10

```text
REFUND_EXECUTING after crash must be treated as potentially already executed.
```

---

# 71. Testing focus

Tests should target behavior, not implementation details.

Minimum useful tests:

```text
intent classification produces REFUND_REQUEST

customer claim does not create APPROVED status

₹7500 with ₹5000 threshold requires approval

refund is blocked while approval is PENDING

approval moves workflow to REFUND_READY

same idempotency key cannot create duplicate gateway transaction

timeout after gateway commit results in UNKNOWN locally

verification finds successful gateway transaction

successful verification marks refund SUCCESS

successful completion marks ticket RESOLVED

three failed verification attempts lead to NEEDS_HUMAN_REVIEW

ticket remains OPEN when outcome is UNKNOWN

restart from WAITING_APPROVAL resumes correctly

restart from REFUND_EXECUTING verifies instead of reissuing refund
```

Mock the LLM in most workflow tests.

Do not call real OpenRouter/Gemini APIs during unit tests.

---

# 72. Coding style

Use:

```text
type hints
small functions
clear docstrings where behavior is non-obvious
Pydantic validation
Enum classes
context managers
parameterized SQL
explicit exceptions
explicit transactions
```

Avoid:

```text
deep inheritance
global mutable state
giant 500-line files
magic strings scattered everywhere
catch Exception and silently continue
nested conditionals where helper functions clarify behavior
```

---

# 73. Error messages

Make CLI errors actionable.

Good:

```text
Cannot execute refund: human approval is still pending.
```

Good:

```text
Refund outcome is unknown. Automatic re-execution is blocked until gateway status is verified.
```

Good:

```text
Cannot resume RUN001: workflow state 'XYZ' is invalid.
```

Avoid:

```text
Something went wrong.
```

---

# 74. Implementation priority

Build in this order:

```text
1. MySQL schema
2. seed data
3. database connection
4. repository functions
5. Pydantic schemas/enums
6. configuration loader
7. LLM factory
8. intent classification
9. raw orchestration loop
10. policy logic
11. CLI approval flow
12. local refund record
13. mock payment gateway
14. timeout simulation
15. verification/recovery
16. completion
17. resume command
18. tests
19. README
```

Do not start by implementing all LLM providers or elaborate abstractions.

Get the workflow working end-to-end first.

---

# 75. Final mental model

There are three separate kinds of state.

### Customer/business state

```text
tickets.status
orders.refund_status
```

Answers:

```text
Has the customer's issue actually been resolved?
```

### Agent workflow state

```text
agent_runs.current_state
```

Answers:

```text
Where is the autonomous operator in its workflow?
```

### External financial state

```text
gateway_transactions
```

Answers:

```text
What actually happened at the payment provider?
```

And local refund state:

```text
refunds
```

is our application's recorded understanding of that financial operation.

These states must not be confused.

---

# 76. Final architecture

```text
                         ┌──────────────┐
                         │ Customer     │
                         │ Ticket T123  │
                         └──────┬───────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Raw Python            │
                    │ Orchestrator          │
                    │ + State Machine       │
                    └──────────┬────────────┘
                               │
              ┌────────────────┼─────────────────┐
              │                │                 │
              ▼                ▼                 ▼
          LLM Layer       MySQL Business     Mock Gateway
        Understand /      + Workflow DB      Python Functions
          Planning              │                 │
                               │                 ▼
                               │        gateway_transactions
                               │
                               ▼
                         agent_runs
                         tickets
                         orders
                         policies
                         refunds
```

Core principle:

```text
LLM understands.

Python decides what is allowed.

MySQL remembers where the workflow is.

Idempotency prevents duplicate side effects.

Gateway verification determines what actually happened.

Only verified outcomes become COMPLETE.
```