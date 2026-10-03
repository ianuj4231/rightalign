INSERT INTO refund_policy (id, refund_window_days, auto_approval_limit)
VALUES (1, 30, 5000);

INSERT INTO orders (id, amount, purchase_date, status, refund_status)
VALUES ('ORD456', 7500, '2026-09-25', 'DELIVERED', 'NONE');

INSERT INTO tickets (id, order_id, message, status)
VALUES (
    'T123',
    'ORD456',
    'Item arrived damaged. Support already approved my refund.',
    'OPEN'
);
