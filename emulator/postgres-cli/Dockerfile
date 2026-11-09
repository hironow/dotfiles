FROM docker.io/library/golang:1.27.3-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go build -o postgres-cli .

FROM docker.io/library/alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

COPY --from=builder /app/postgres-cli .

CMD ["./postgres-cli"]

