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
# Connectivity
# ------------
# The instance has NO public IP. Coder reaches it via a Cloud SQL
# Auth Proxy v2 systemd service running on the same VM
# (loopback :5432). CSAP authenticates to the instance using the
# VM's exe-coder@ service account (roles/cloudsql.client). VPC
# peering to the Service Networking range gives the proxy a private
# path; no firewall rule, no public exposure.
#
# Credentials
# -----------
# tofu generates a random 32-char alphanumeric password (no special
# chars to keep the connection-string URL trivially safe), stores it
# in Secret Manager, and grants the VM SA secretAccessor. The VM
# fetches the value at boot and assembles
# CODER_PG_CONNECTION_URL=postgres://coder:<pwd>@127.0.0.1:5432/coder?sslmode=disable
# (sslmode=disable is correct: CSAP terminates the encrypted leg
# between the proxy and the managed instance).

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

resource "random_password" "coder_pg_password" {
  length  = 32
  special = false # alphanumeric — keeps the postgres:// URL trivially safe
}

resource "google_sql_database_instance" "coder" {
  name             = "${local.prefix}-coder-pg"
  region           = var.gcp_region
  database_version = var.cloud_sql_postgres_version

  # Mandatory: protects against tofu destroy taking the DB with it.
  # Operator must flip this to false explicitly to delete.
  deletion_protection = true

  settings {
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

resource "google_sql_user" "coder" {
  name     = "coder"
  instance = google_sql_database_instance.coder.name
  password = random_password.coder_pg_password.result
}

# ----- Secret Manager: pg password ------------------------------------

resource "google_secret_manager_secret" "coder_pg_password" {
  secret_id = "${local.prefix}-coder-pg-password"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "coder_pg_password" {
  secret      = google_secret_manager_secret.coder_pg_password.id
  secret_data = random_password.coder_pg_password.result
}

resource "google_secret_manager_secret_iam_member" "coder_pg_password_reader" {
  secret_id = google_secret_manager_secret.coder_pg_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- IAM: VM SA can connect to Cloud SQL via CSAP -------------------

resource "google_project_iam_member" "exe_coder_cloudsql_client" {
  project = var.gcp_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- locals exposed to coder.tf --------------------------------------
#
# Connection name is what CSAP takes as -i argument. Format is
# "<project>:<region>:<instance>".

locals {
  cloud_sql_connection_name = google_sql_database_instance.coder.connection_name
  cloud_sql_proxy_url = format(
    "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/%s/cloud-sql-proxy.linux.amd64",
    var.cloud_sql_proxy_version,
  )
}
