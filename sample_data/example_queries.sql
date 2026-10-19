-- =============================================================================
-- DataVerse Fictional E-Commerce Demo Queries (Aura Retail)
-- =============================================================================
-- These queries demonstrate DataVerse's relational joins, aggregations,
-- grouping, filtering, and outer join edge cases.
-- =============================================================================

-- 1. Customers with their orders (Basic Relational INNER JOIN)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    o.order_id,
    o.order_date,
    p.product_name,
    o.quantity,
    o.total_amount,
    o.status
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
INNER JOIN products p ON o.product_id = p.product_id
ORDER BY o.order_date DESC
LIMIT 50;


-- 2. Total sales and order count by customer (Aggregation & Sorting)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.customer_segment,
    COUNT(o.order_id) AS total_orders,
    ROUND(SUM(o.total_amount), 2) AS total_spend,
    ROUND(AVG(o.total_amount), 2) AS average_order_value
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status NOT IN ('Cancelled', 'Refunded')
GROUP BY c.customer_id, c.first_name, c.last_name, c.customer_segment
ORDER BY total_spend DESC;


-- 3. Revenue and units sold by product (Product Performance)
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.price,
    SUM(o.quantity) AS total_units_sold,
    ROUND(SUM(o.total_amount), 2) AS gross_revenue
FROM products p
LEFT JOIN orders o ON p.product_id = o.product_id AND o.status != 'Cancelled'
GROUP BY p.product_id, p.product_name, p.category, p.price
ORDER BY gross_revenue DESC;


-- 4. Orders and revenue broken down by order status
SELECT
    o.status,
    COUNT(*) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS total_volume,
    ROUND(AVG(o.total_amount), 2) AS avg_order_amount
FROM orders o
GROUP BY o.status
ORDER BY order_count DESC;


-- 5. Inactive customers: Customers with no placed orders (LEFT JOIN / Anti-Join)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    c.customer_segment,
    c.signup_date
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id ASC;


-- 6. Top 5 customers by order count
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.email,
    COUNT(o.order_id) AS order_count
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.email
ORDER BY order_count DESC
LIMIT 5;


-- 7. High-value orders / Outliers (> $1,000 total order value)
SELECT
    o.order_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    p.product_name,
    o.quantity,
    o.total_amount,
    o.order_date
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE o.total_amount >= 1000.00
ORDER BY o.total_amount DESC;
