terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # After first apply, store state in GCS so it's shared and durable.
  # Run: gsutil mb gs://rodela-trial-project-tfstate before init.
  backend "gcs" {
    bucket = "rodela-trial-project-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── APIs ──────────────────────────────────────────────────────────────────────

resource "google_project_service" "container" {
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudresourcemanager" {
  service            = "cloudresourcemanager.googleapis.com"
  disable_on_destroy = false
}

# ── Artifact Registry ─────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "pi_agent" {
  repository_id = var.registry_name
  location      = var.region
  format        = "DOCKER"
  description   = "Docker images for pi-agent-api"

  depends_on = [google_project_service.artifactregistry]
}

# ── GKE Cluster ───────────────────────────────────────────────────────────────

resource "google_container_cluster" "pi_agent" {
  name     = var.cluster_name
  location = var.zone

  # We manage the node pool separately so we can configure autoscaling.
  remove_default_node_pool = true
  initial_node_count       = 1

  depends_on = [google_project_service.container]

  lifecycle {
    ignore_changes = [
      initial_node_count,
      node_config,
      node_pool,
    ]
  }
}

resource "google_container_node_pool" "pi_agent_nodes" {
  name       = "default-pool"
  cluster    = google_container_cluster.pi_agent.name
  location   = var.zone

  autoscaling {
    min_node_count = 1
    max_node_count = 10
  }

  node_config {
    machine_type = "e2-small"
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    service_account = "default"
  }

  lifecycle {
    ignore_changes = all
  }
}

# Reference to the current GCP project (used for default compute SA email)
data "google_project" "project" {}

# Allow GKE nodes to pull from Artifact Registry
resource "google_project_iam_member" "gke_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Allow GKE nodes to read secrets from Secret Manager
resource "google_project_iam_member" "gke_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# ── Secret Manager secrets (values set manually or via CI) ────────────────────

resource "google_secret_manager_secret" "gke_api_key" {
  secret_id = "gke-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "pi_tunnel_url" {
  secret_id = "pi-tunnel-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "pi_execute_token" {
  secret_id = "pi-execute-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

# Tailscale auth key for GKE sidecar to join the Tailscale network
resource "google_secret_manager_secret" "tailscale_auth_key" {
  secret_id = "tailscale-auth-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

# ── CI/CD — Workload Identity Federation ─────────────────────────────────────

resource "google_project_service" "iam_credentials" {
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

# Service account used by GitHub Actions
resource "google_service_account" "github_actions" {
  account_id   = "github-actions-sa"
  display_name = "GitHub Actions"
}

# Allow GitHub Actions SA to deploy to GKE
resource "google_project_iam_member" "github_actions_container_dev" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Allow GitHub Actions SA to push images to Artifact Registry
resource "google_project_iam_member" "github_actions_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Workload Identity Pool
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  depends_on                = [google_project_service.iam_credentials]
}

# Workload Identity Provider — trusts GitHub OIDC tokens
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.actor"      = "assertion.actor"
  }

  attribute_condition = "assertion.repository=='Asari-AI/rodela-trial-project'"
}

# Allow GitHub Actions (from this repo) to impersonate the SA
resource "google_service_account_iam_member" "github_actions_wi" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/Asari-AI/rodela-trial-project"
}
