provider "github" {
  owner = var.owner
}

module "autofag" {
  source = "./modules/github-repo"

  name        = "autofag"
  description = "Overvåker emner på UiO Studentweb og melder deg på når en plass blir ledig"
  visibility  = "public"
  topics      = ["uio", "studentweb", "cli", "python", "playwright"]

  required_status_checks = ["test"]
  required_approvals     = 0
}

import {
  to = module.autofag.github_repository.this
  id = "autofag"
}
