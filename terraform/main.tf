provider "github" {
  owner = var.owner
}

module "autofag" {
  source = "git::https://github.com/vuhnger/terraform-github-repo.git?ref=v1.0.1"

  name        = "autofag"
  description = "Overvåker emner på UiO Studentweb og melder deg på når en plass blir ledig"
  visibility  = "public"
  topics      = ["uio", "studentweb", "cli", "python", "playwright"]

  required_status_checks = ["test", "Conventional Commit title"]
  required_approvals     = 0
}

import {
  to = module.autofag.github_repository.this
  id = "autofag"
}
