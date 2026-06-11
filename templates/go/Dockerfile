FROM golang:1.22-alpine AS build

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /app/server .

FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=build /app/server /server

EXPOSE 8000

USER nonroot:nonroot

ENTRYPOINT ["/server"]
