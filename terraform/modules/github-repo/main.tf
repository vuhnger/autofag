terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

resource "github_repository" "this" {
  name        = var.name
  description = var.description
  visibility  = var.visibility
  topics      = var.topics

  has_issues   = var.has_issues
  has_wiki     = false
  has_projects = false
  is_template  = var.is_template
  auto_init    = false
  archived     = false

  allow_squash_merge     = true
  allow_merge_commit     = false
  allow_rebase_merge     = false
  allow_auto_merge       = true
  delete_branch_on_merge = true

  squash_merge_commit_title   = "PR_TITLE"
  squash_merge_commit_message = "PR_BODY"


  lifecycle {
    prevent_destroy = true
  }
}

resource "github_repository_vulnerability_alerts" "this" {
  repository = github_repository.this.name
  enabled    = true
}

resource "github_branch_protection" "default" {
  repository_id = github_repository.this.node_id
  pattern       = var.default_branch

  required_status_checks {
    strict   = true
    contexts = var.required_status_checks
  }

  required_pull_request_reviews {
    required_approving_review_count = var.required_approvals
    dismiss_stale_reviews           = true
    require_last_push_approval      = false
  }

  require_conversation_resolution = true
  required_linear_history         = true
  allows_force_pushes             = false
  allows_deletions                = false
  enforce_admins                  = false
}
