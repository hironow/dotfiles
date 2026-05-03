# Cloud SQL Postgres data plane for the Coder server (ADR 0010).
#
# Why this exists
# ---------------
# Up to ADR 0009 the Coder server ran with embedded PostgreSQL on the
# VM boot disk. Boot disk has auto_delete=true, so every VM
# replacement (startup-script edit, SPOT preempt, GCE maintenance)
# wiped the entire data plane (templates, users, workspaces, audit
# logs, admin password). This file decomposes the DB to a managed
# Cloud SQL instance per Coder's official guidance.
#
# Connectivity + auth
# -------------------
# The instance has NO public IP. Coder reaches it via a Cloud SQL
# Auth Proxy v2 systemd service running on the same VM (loopback
# :5432). Per Cloud SQL 2026 best practice, CSAP runs with
# `--auto-iam-authn=true` and the only Postgres user is an IAM
# service-account user mapped to the VM's exe-coder@ SA. There is
# NO password anywhere — CSAP requests a short-lived OAuth access
# token from the VM's metadata server and injects it as the password
# at connection time. Nothing for the operator (or tofu) to rotate.
#
# Required IAM on the VM SA:
#   roles/cloudsql.client       — connect through CSAP (TLS cert)
#   roles/cloudsql.instanceUser — authenticate as an IAM DB user
#
# VPC peering to the Service Networking range gives the proxy a
# private path; no firewall rule, no public exposure.

# ----- VPC peering for private IP --------------------------------------
#
# Service Networking requires a CIDR allocated inside the consumer VPC
# from which the managed services pull addresses. /20 = 4096 addresses
# is GCP's recommended floor; one /20 is enough for any number of
# managed services peered to this VPC.

resource "google_compute_global_address" "exe_psa_range" {
  name          = "${local.prefix}-psa-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.exe.id
}

resource "google_service_networking_connection" "exe_psa" {
  network                 = google_compute_network.exe.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.exe_psa_range.name]
}

# ----- Cloud SQL instance ---------------------------------------------

resource "google_sql_database_instance" "coder" {
  name             = "${local.prefix}-coder-pg"
  region           = var.gcp_region
  database_version = var.cloud_sql_postgres_version

  # Mandatory: protects against tofu destroy taking the DB with it.
  # Operator must flip this to false explicitly to delete.
  deletion_protection = true

  settings {
    # ENTERPRISE edition supports the legacy shared-core tiers
    # (db-f1-micro, db-g1-small, db-custom-N-RAMMB). New instances
    # default to ENTERPRISE_PLUS, which only accepts the more
    # expensive db-perf-optimized-N-* tiers and rejects db-f1-micro
    # at create time. Single-operator stack does not need EP
    # features (Read Pools, sub-second failover, etc.); pin to
    # ENTERPRISE so cloud_sql_tier remains a small/cheap value.
    edition           = "ENTERPRISE"
    tier              = var.cloud_sql_tier
    availability_type = "ZONAL" # personal stack; no HA
    disk_type         = "PD_SSD"
    disk_size         = var.cloud_sql_disk_size_gb
    disk_autoresize   = true

    user_labels = local.common_labels

    backup_configuration {
      enabled                        = true
      start_time                     = "18:00" # 18:00 UTC = 03:00 JST (off-hours)
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7 # 1 week of daily backups
        retention_unit   = "COUNT"
      }
    }

    # Private IP only. No public IP, no authorized networks.
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.exe.id
    }

    # Enable IAM database authentication. Required for the
    # cloud_iam_service_account user resource below to be usable.
    # Standard password auth still works for the cloudsqlsuperuser
    # role if Cloud SQL adds it implicitly, but no password user is
    # provisioned here.
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  # Cloud SQL on private IP requires the Service Networking peering to
  # be live before the instance is created.
  depends_on = [google_service_networking_connection.exe_psa]
}

resource "google_sql_database" "coder" {
  name     = "coder"
  instance = google_sql_database_instance.coder.name
}

# Cloud SQL provisions the internal `cloudsqliamserviceaccount`
# Postgres role asynchronously after the instance reports READY,
# while the IAM auth flag is being applied to the running engine.
# Creating an IAM SA user before that role exists fails with:
#   "role \"cloudsqliamserviceaccount\" does not exist"
# A 60s sleep is the documented workaround in the google provider
# tracker; longer than the typical settle time, short enough that
# `tofu apply` users do not notice.
resource "time_sleep" "cloud_sql_iam_role_settle" {
  depends_on      = [google_sql_database_instance.coder]
  create_duration = "60s"
}

# IAM service-account user. Postgres username convention for Cloud
# SQL IAM SA users is "<sa-email-without-.gserviceaccount.com>" —
# tofu has the bare account_id + project, we reconstruct that here.
# Result: "exe-coder@gen-ai-hironow.iam"
resource "google_sql_user" "coder_iam" {
  name     = trimsuffix(google_service_account.exe_coder.email, ".gserviceaccount.com")
  instance = google_sql_database_instance.coder.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"

  # Wait for the asynchronous internal role creation. See the
  # time_sleep above for the why.
  depends_on = [time_sleep.cloud_sql_iam_role_settle]
}

# ----- Postgres admin user (bootstrap-only) ---------------------------
#
# Why this exists: Postgres 15+ locks down the public schema by
# default — newly-created users (including IAM SA users) cannot
# CREATE TABLE in it. Coder server fails its initial schema
# migration with "permission denied for schema public" until a
# privileged role grants USAGE + CREATE on public to the IAM user.
#
# Cloud SQL's `postgres` BUILT_IN user holds `cloudsqlsuperuser`
# and CAN issue those grants. Tofu sets a random password on it,
# stores the password in Secret Manager, and the VM startup_script
# uses it ONCE at first boot to bootstrap the IAM user's grants.
# Coder server then runs entirely under IAM auth at runtime — the
# postgres password is bootstrap-only.
#
# Threat model: the postgres password lives in Secret Manager
# (mode 0600 on the secret resource, IAM-restricted to the VM
# SA only). On the VM it is fetched once at startup, used in a
# subprocess, then unset. Worst case if leaked: ability to
# re-bootstrap the DB; coder.service runtime path remains pure
# IAM auth.

resource "random_password" "postgres_admin" {
  length  = 32
  special = false
}

resource "google_sql_user" "postgres" {
  name     = "postgres"
  instance = google_sql_database_instance.coder.name
  password = random_password.postgres_admin.result
  # Cloud SQL auto-creates the postgres BUILT_IN superuser on
  # every Postgres instance; tofu's google_sql_user reconciles by
  # setting our managed password. type defaults to BUILT_IN.

  depends_on = [time_sleep.cloud_sql_iam_role_settle]
}

resource "google_secret_manager_secret" "postgres_admin" {
  secret_id = "${local.prefix}-postgres-admin-password"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "postgres_admin" {
  secret      = google_secret_manager_secret.postgres_admin.id
  secret_data = random_password.postgres_admin.result
}

resource "google_secret_manager_secret_iam_member" "postgres_admin_reader" {
  secret_id = google_secret_manager_secret.postgres_admin.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- IAM on the VM SA -----------------------------------------------
# Two roles are required for IAM database authentication:
#   roles/cloudsql.client       — TLS cert to dial the instance
#   roles/cloudsql.instanceUser — exchange ADC for a DB access token
# Without instanceUser the proxy connects but every login fails with
# "FATAL: pq: password authentication failed for user".

resource "google_project_iam_member" "exe_coder_cloudsql_client" {
  project = var.gcp_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

resource "google_project_iam_member" "exe_coder_cloudsql_instance_user" {
  project = var.gcp_project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- locals exposed to coder.tf --------------------------------------
#
# Connection name is what CSAP takes as instance argument. Format is
# "<project>:<region>:<instance>". The IAM DB username is exposed as
# a local so coder.tf can build CODER_PG_CONNECTION_URL without
# duplicating the trimsuffix logic.

locals {
  cloud_sql_connection_name = google_sql_database_instance.coder.connection_name
  cloud_sql_iam_db_user     = google_sql_user.coder_iam.name
  cloud_sql_private_ip      = google_sql_database_instance.coder.private_ip_address
  cloud_sql_proxy_url = format(
    "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/%s/cloud-sql-proxy.linux.amd64",
    var.cloud_sql_proxy_version,
  )
}
