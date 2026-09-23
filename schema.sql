-- SQLite schema for the Pet Adoption System.
-- Column names match the original MySQL database so old data imports cleanly.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tbl_company (
    company_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_logo    TEXT,
    company_name    TEXT,
    company_address TEXT,
    company_contact TEXT,
    company_website TEXT
);

CREATE TABLE IF NOT EXISTS tbl_user (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password      TEXT NOT NULL,
    complete_name TEXT NOT NULL,
    designation   TEXT NOT NULL DEFAULT '',
    profile_image TEXT NOT NULL DEFAULT '',
    user_type     TEXT NOT NULL DEFAULT 'user' CHECK (user_type IN ('admin', 'user'))
);

CREATE TABLE IF NOT EXISTS tbl_pet_type (
    pet_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_type_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tbl_pet_owner (
    pet_owner_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_owner_name     TEXT NOT NULL,
    pet_owner_contact  TEXT,
    pet_owner_email    TEXT,
    pet_owner_address  TEXT,
    pet_owner_profile  TEXT,
    pet_owner_username TEXT NOT NULL UNIQUE,
    pet_owner_password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tbl_adopter (
    adopter_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    adopter_name     TEXT NOT NULL,
    adopter_contact  TEXT,
    adopter_email    TEXT,
    adopter_address  TEXT,
    adopter_profile  TEXT,
    adopter_username TEXT NOT NULL UNIQUE,
    adopter_password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tbl_pet (
    pet_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_owner_id          INTEGER REFERENCES tbl_pet_owner (pet_owner_id),
    pet_name              TEXT NOT NULL,
    pet_type_id           INTEGER REFERENCES tbl_pet_type (pet_type_id),
    description           TEXT,
    age                   INTEGER,
    gender                TEXT CHECK (gender IN ('Male', 'Female')),
    health_status         TEXT NOT NULL CHECK (health_status IN ('Healthy', 'Needs Treatment')),
    upload_health_history TEXT,
    vaccination_status    TEXT NOT NULL CHECK (vaccination_status IN ('Vaccinated', 'Not Vaccinated')),
    proof_of_vaccination  TEXT,
    adoption_status       TEXT NOT NULL CHECK (adoption_status IN ('Available', 'Pending', 'Adopted')),
    pet_profile_image     TEXT NOT NULL DEFAULT '',
    date_registered       TEXT
);

CREATE TABLE IF NOT EXISTS tbl_pet_media (
    pet_media_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id         INTEGER,
    pet_media_name TEXT,
    pet_media_url  TEXT
);

-- Adoptions recorded by staff, and requests sent by adopters from their account.
CREATE TABLE IF NOT EXISTS tbl_adoption (
    adoption_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id                   INTEGER,
    adopter_id               INTEGER,
    adoption_date            TEXT,
    upload_adoption_document TEXT,
    remarks                  TEXT,
    user_id                  INTEGER
);

CREATE TABLE IF NOT EXISTS tbl_adoption_request (
    adoption_request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id              INTEGER,
    adopter_id          INTEGER,
    request_date        TEXT,
    status              TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Approved', 'Rejected')),
    approval_date       TEXT,
    remarks             TEXT,
    user_id             INTEGER,
    message             TEXT
);

CREATE TABLE IF NOT EXISTS tbl_activity_log (
    log_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    log_type      TEXT,
    details       TEXT,
    date_time     TEXT
);

CREATE TABLE IF NOT EXISTS tbl_inquiry (
    inquiry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id     INTEGER,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL,
    phone      TEXT,
    subject    TEXT NOT NULL,
    message    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'New' CHECK (status IN ('New', 'Replied', 'Closed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_pet_status ON tbl_pet (adoption_status);
CREATE INDEX IF NOT EXISTS idx_pet_type ON tbl_pet (pet_type_id);
CREATE INDEX IF NOT EXISTS idx_log_time ON tbl_activity_log (date_time);
CREATE INDEX IF NOT EXISTS idx_inquiry_status ON tbl_inquiry (status);
CREATE INDEX IF NOT EXISTS idx_request_status ON tbl_adoption_request (status);
CREATE INDEX IF NOT EXISTS idx_adoption_pet ON tbl_adoption (pet_id);
