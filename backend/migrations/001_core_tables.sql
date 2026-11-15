-- 参考建表语句（运行时由 SQLAlchemy Base.metadata.create_all 建表）。
-- 口径：MySQL 8.0 / utf8mb4；assignments 的自然键保证 seed 幂等。

CREATE TABLE IF NOT EXISTS experiments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(40) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  hypothesis TEXT,
  owner VARCHAR(80) NOT NULL DEFAULT '橙野 App · 增长实验组',
  primary_metric VARCHAR(40) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'running',
  baseline_rate FLOAT NOT NULL DEFAULT 0.1,
  planned_mde FLOAT NOT NULL DEFAULT 0.01,
  alpha FLOAT NOT NULL DEFAULT 0.05,
  power_target FLOAT NOT NULL DEFAULT 0.8,
  traffic_note TEXT NULL,
  started_on DATE NULL,
  ended_on DATE NULL,
  srm_chi2 FLOAT NULL,
  srm_df INT NULL,
  srm_p_value FLOAT NULL,
  srm_status VARCHAR(12) NOT NULL DEFAULT 'unknown',
  srm_checked_at DATETIME NULL,
  required_per_variant INT NULL,
  power_at_current FLOAT NULL,
  mde_at_current FLOAT NULL,
  srm_payload JSON NULL,
  has_srm_alarm TINYINT(1) NOT NULL DEFAULT 0,
  seed_key VARCHAR(120) NULL UNIQUE,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY ix_experiments_status (status),
  KEY ix_experiments_primary_metric (primary_metric),
  KEY ix_experiments_has_srm_alarm (has_srm_alarm)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS variants (
  id INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL,
  code VARCHAR(40) NOT NULL,
  name VARCHAR(120) NOT NULL,
  ratio FLOAT NOT NULL DEFAULT 0.5,
  is_control TINYINT(1) NOT NULL DEFAULT 0,
  note TEXT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  UNIQUE KEY uq_variants_experiment_code (experiment_id, code),
  CONSTRAINT fk_variants_experiment FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS assignments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL,
  variant_id INT NOT NULL,
  channel VARCHAR(20) NOT NULL,
  metric_key VARCHAR(40) NOT NULL,
  stat_date DATE NOT NULL,
  samples INT NOT NULL DEFAULT 0,
  conversions INT NOT NULL DEFAULT 0,
  operator_email VARCHAR(160) NOT NULL DEFAULT 'system',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uq_assignment_cell (experiment_id, variant_id, channel, metric_key, stat_date),
  CONSTRAINT fk_assignment_experiment FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE,
  CONSTRAINT fk_assignment_variant FOREIGN KEY (variant_id) REFERENCES variants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS metric_results (
  id INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL,
  variant_id INT NULL,
  variant_code VARCHAR(40) NOT NULL,
  variant_name VARCHAR(120) NOT NULL DEFAULT '',
  metric_key VARCHAR(40) NOT NULL,
  metric_name VARCHAR(80) NOT NULL DEFAULT '',
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  method VARCHAR(16) NOT NULL DEFAULT 'bh',
  control_n INT, control_conversions INT, variant_n INT, variant_conversions INT,
  control_rate FLOAT, variant_rate FLOAT, diff FLOAT, z FLOAT,
  p_value FLOAT, q_value FLOAT, q_bh FLOAT, q_bonferroni FLOAT,
  ci_low FLOAT, ci_high FLOAT, lift FLOAT, lift_ci_low FLOAT, lift_ci_high FLOAT,
  significant TINYINT(1) NOT NULL DEFAULT 0,
  verdict VARCHAR(16) NOT NULL DEFAULT 'continue',
  required_n INT, power_at_current FLOAT, alpha FLOAT NOT NULL DEFAULT 0.05,
  payload JSON NULL,
  computed_at DATETIME NOT NULL,
  computed_by VARCHAR(160) NOT NULL DEFAULT 'system',
  UNIQUE KEY uq_metric_experiment_variant_metric (experiment_id, variant_code, metric_key),
  CONSTRAINT fk_metric_experiment FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS decisions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL,
  verdict VARCHAR(16) NOT NULL,
  rationale TEXT,
  decided_by VARCHAR(160) NOT NULL DEFAULT '',
  decided_at DATETIME NOT NULL,
  seed_key VARCHAR(120) NULL UNIQUE,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uq_decision_experiment (experiment_id),
  CONSTRAINT fk_decision_experiment FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(160) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(80) NOT NULL,
  role VARCHAR(20) NOT NULL,
  org VARCHAR(120) NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  actor_email VARCHAR(160) NOT NULL,
  actor_role VARCHAR(20) NOT NULL,
  action VARCHAR(64) NOT NULL,
  entity VARCHAR(40) NOT NULL,
  entity_id VARCHAR(64) NULL,
  detail JSON NULL,
  layer VARCHAR(16) NOT NULL DEFAULT 'domain',
  ip VARCHAR(64) NULL,
  seed_key VARCHAR(120) NULL UNIQUE,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
