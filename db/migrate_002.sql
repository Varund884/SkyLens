-- Provenance for occurrence categories.
-- CADORS rows carry the category Transport Canada assigned (category_source = 'source').
-- NTSB rows get a category predicted by ai/classify.py (category_source = 'model'),
-- with the model's probability in category_confidence. The website must label
-- model categories as predicted, never as the authority's own classification.
IF COL_LENGTH('fact_occurrence', 'category_source') IS NULL
    ALTER TABLE fact_occurrence ADD category_source NVARCHAR(10) NULL;
IF COL_LENGTH('fact_occurrence', 'category_confidence') IS NULL
    ALTER TABLE fact_occurrence ADD category_confidence FLOAT NULL;
GO
UPDATE fact_occurrence SET category_source = 'source'
WHERE category_key IS NOT NULL AND category_source IS NULL;
GO
CREATE OR ALTER VIEW v_occurrence_analysis AS
SELECT * FROM fact_occurrence WHERE in_analysis_window = 1;
