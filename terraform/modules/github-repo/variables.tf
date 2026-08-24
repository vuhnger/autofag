variable "name" {
  description = "Repository name"
  type        = string
}

variable "description" {
  description = "One-line repository description"
  type        = string
}

variable "visibility" {
  description = "public or private"
  type        = string
  default     = "public"

  validation {
    condition     = contains(["public", "private"], var.visibility)
    error_message = "visibility must be public or private."
  }
}

variable "topics" {
  description = "Repository topics"
  type        = list(string)
  default     = []
}

variable "default_branch" {
  description = "Branch that pull requests merge into"
  type        = string
  default     = "main"
}

variable "required_status_checks" {
  description = "Check names that must pass before a pull request can merge"
  type        = list(string)
  default     = []
}

variable "required_approvals" {
  description = "Approving reviews required before merge. Zero keeps solo repositories mergeable."
  type        = number
  default     = 0
}

variable "is_template" {
  description = "Whether the repository can be used as a template"
  type        = bool
  default     = false
}

variable "has_issues" {
  description = "Whether the issue tracker is enabled"
  type        = bool
  default     = true
}
