job "cron-job" {
  datacenters = ["dc1"]
  type = "batch"

  periodic {
    cron             = "*/15 * * * * *"
    prohibit_overlap = true
  }

  group "periodic-tasks" {
    task "cleanup" {
      driver = "docker"

      config {
        image = "alpine:latest"
        command = "echo"
        args = ["Running periodic cleanup task..."]
      }

      resources {
        cpu    = 100
        memory = 64
      }
    }
  }
}
