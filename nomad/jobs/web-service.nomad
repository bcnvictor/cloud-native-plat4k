job "web-service" {
  datacenters = ["dc1"]
  type = "service"

  # Example constraint to force placement on a specific cloud
  # constraint {
  #   attribute = "${meta.cloud}"
  #   value     = "aws"
  # }

  group "web" {
    count = 1

    network {
      port "http" {
        to = 8080
      }
    }

    service {
      name = "web-service"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "server" {
      driver = "docker"

      config {
        image = "nginx:alpine"
        ports = ["http"]
      }

      env {
        ENV_VAR_EXAMPLE = "value"
      }

      resources {
        cpu    = 200 # 200 MHz
        memory = 128 # 128 MB
      }
    }
  }
}
