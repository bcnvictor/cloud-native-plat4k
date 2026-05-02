job "batch-job" {
  datacenters = ["dc1"]
  type = "batch"

  group "processor" {
    count = 1

    restart {
      attempts = 2
      interval = "5m"
      delay    = "15s"
      mode     = "fail"
    }

    task "process" {
      driver = "docker"

      config {
        image = "python:3.9-slim"
        command = "python"
        args = ["-c", "print('Batch job complete')"]
      }

      resources {
        cpu    = 500
        memory = 256
      }
    }
  }
}
