PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS releases (
 id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, published_on TEXT NOT NULL,
 imported_at TEXT NOT NULL, sha256 TEXT NOT NULL, input_rows INTEGER NOT NULL,
 stored_rows INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL,
 source_url TEXT NOT NULL, UNIQUE(dataset,published_on,sha256)
);
CREATE TABLE IF NOT EXISTS current_release (
 dataset TEXT PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases(id)
);
CREATE TABLE IF NOT EXISTS facilities (
 dataset TEXT NOT NULL, ccn TEXT NOT NULL, name TEXT NOT NULL,
 address TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL, zip TEXT NOT NULL,
 county TEXT NOT NULL, category TEXT NOT NULL, subtype TEXT NOT NULL,
 ownership TEXT NOT NULL, chain TEXT NOT NULL, capacity TEXT NOT NULL,
 release_id INTEGER NOT NULL REFERENCES releases(id),
 PRIMARY KEY(dataset,ccn)
);
CREATE INDEX IF NOT EXISTS facilities_state ON facilities(state,category,name,ccn);
CREATE INDEX IF NOT EXISTS facilities_name ON facilities(name COLLATE NOCASE,dataset,ccn);
CREATE TABLE IF NOT EXISTS findings (
 dataset TEXT NOT NULL, row_hash TEXT NOT NULL, ccn TEXT NOT NULL,
 provider_name TEXT NOT NULL, state TEXT NOT NULL, survey_date TEXT NOT NULL,
 survey_type TEXT NOT NULL, tag TEXT NOT NULL, category TEXT NOT NULL,
 description TEXT NOT NULL, severity TEXT NOT NULL, correction_status TEXT NOT NULL,
 correction_date TEXT NOT NULL, release_id INTEGER NOT NULL REFERENCES releases(id),
 PRIMARY KEY(dataset,row_hash)
);
CREATE INDEX IF NOT EXISTS findings_ccn ON findings(ccn,survey_date);
CREATE INDEX IF NOT EXISTS findings_state ON findings(state,survey_date);
