output "full_name" {
  description = "owner/name of the repository"
  value       = github_repository.this.full_name
}

output "html_url" {
  description = "Browser URL for the repository"
  value       = github_repository.this.html_url
}
