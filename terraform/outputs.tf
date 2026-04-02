output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.pi_agent.name
}

output "cluster_zone" {
  description = "GKE cluster zone"
  value       = google_container_cluster.pi_agent.location
}

output "registry_url" {
  description = "Artifact Registry URL for pushing images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.registry_name}"
}

output "gke_node_sa" {
  description = "Service account email used by GKE nodes"
  value       = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}
