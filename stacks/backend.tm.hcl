generate_hcl "backend.tf" {
  content {
    terraform {
      backend "local" {}
    }
  }
}
