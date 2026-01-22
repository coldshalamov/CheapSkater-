-- Backfill script to fix existing stores with NULL region
-- Run this on the Render database after deploying the ingest.py fix

-- Update stores table to set region based on state
UPDATE stores
SET region = CASE
    WHEN state = 'FL' THEN 'FL'
    WHEN state IN ('WA', 'OR') THEN 'WA_OR'
    ELSE NULL
END
WHERE region IS NULL;

-- Verify the update
SELECT
    region,
    COUNT(*) as store_count,
    GROUP_CONCAT(DISTINCT state) as states
FROM stores
GROUP BY region
ORDER BY region;
