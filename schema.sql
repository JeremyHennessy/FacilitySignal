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

CREATE TABLE IF NOT EXISTS certification_releases (
 registry TEXT PRIMARY KEY, title TEXT NOT NULL, period TEXT NOT NULL,
 version_api TEXT NOT NULL, download_url TEXT NOT NULL, source_sha256 TEXT NOT NULL,
 row_count INTEGER NOT NULL, imported_at TEXT NOT NULL, column_mapping TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS certification_records (
 registry TEXT NOT NULL REFERENCES certification_releases(registry),
 row_number INTEGER NOT NULL, row_sha256 TEXT NOT NULL, provider_id TEXT NOT NULL,
 name TEXT NOT NULL, address TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL,
 zip TEXT NOT NULL, provider_type TEXT NOT NULL, subtype TEXT NOT NULL,
 certification_date TEXT NOT NULL, termination_date TEXT NOT NULL, status TEXT NOT NULL,
 PRIMARY KEY(registry,row_number)
);
CREATE INDEX IF NOT EXISTS certification_id ON certification_records(registry,provider_id);
CREATE INDEX IF NOT EXISTS certification_state ON certification_records(state,registry,name);
CREATE INDEX IF NOT EXISTS certification_name ON certification_records(name COLLATE NOCASE,registry,row_number);

CREATE TABLE IF NOT EXISTS qcor_hospital_releases (
 id INTEGER PRIMARY KEY, source_sha256 TEXT NOT NULL UNIQUE,
 retrieved_at TEXT NOT NULL, download_url TEXT NOT NULL,
 byte_count INTEGER NOT NULL, expected_rows INTEGER NOT NULL, stored_rows INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS qcor_hospital_current (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 release_id INTEGER NOT NULL REFERENCES qcor_hospital_releases(id)
);
CREATE TABLE IF NOT EXISTS qcor_hospital_rows (
 release_id INTEGER NOT NULL REFERENCES qcor_hospital_releases(id),
 row_ordinal INTEGER NOT NULL, projection_sha256 TEXT NOT NULL,
 ccn TEXT NOT NULL, name TEXT NOT NULL, subtype TEXT NOT NULL, address TEXT NOT NULL,
 city TEXT NOT NULL, state TEXT NOT NULL, zip TEXT NOT NULL, region TEXT NOT NULL,
 event_id TEXT NOT NULL, survey_date TEXT NOT NULL, survey_type TEXT NOT NULL,
 tag TEXT NOT NULL, description TEXT NOT NULL, tag_type TEXT NOT NULL,
 row_kind TEXT NOT NULL CHECK(row_kind IN ('tag','memo','no_tag_reported')),
 PRIMARY KEY(release_id,row_ordinal)
);
CREATE INDEX IF NOT EXISTS qcor_hospital_ccn ON qcor_hospital_rows(release_id,ccn,survey_date DESC);
CREATE INDEX IF NOT EXISTS qcor_hospital_state ON qcor_hospital_rows(release_id,state,survey_date DESC);
CREATE INDEX IF NOT EXISTS qcor_hospital_tag ON qcor_hospital_rows(release_id,tag,survey_date DESC);
CREATE INDEX IF NOT EXISTS qcor_hospital_recent ON qcor_hospital_rows(release_id,survey_date DESC,row_ordinal);
