-- Feature 1: Gestione Frazionata
-- Add supports_fractions flag to assets table
ALTER TABLE assets ADD COLUMN IF NOT EXISTS supports_fractions boolean NOT NULL DEFAULT true;
